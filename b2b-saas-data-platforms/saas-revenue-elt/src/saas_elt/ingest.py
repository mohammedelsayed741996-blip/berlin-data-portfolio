"""Extract and load: database, REST API and file sources into the raw layer.

All three loaders follow the same steps:

1. read the watermark (or file manifest) left by the last successful batch;
2. extract only what changed since then;
3. validate every record against its contract; quarantine failures;
4. append the good records to the raw table with batch metadata;
5. move the watermark only after the batch has been written.

A batch that already succeeded for a run date is skipped, so re-running a
day never loads the same data twice.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from .contracts import Contract, validate
from .simulator import BillingAPI, TransientAPIError
from .warehouse import Warehouse, now_utc

logger = logging.getLogger(__name__)

API_OVERLAP = timedelta(hours=1)  # re-read the last hour to catch late commits at the source


@dataclass
class BatchStats:
    source: str
    batch_id: str
    extracted: int = 0
    loaded: int = 0
    quarantined: int = 0
    duplicates_skipped: int = 0
    control_count: int | None = None
    new_drift_fields: list[str] = field(default_factory=list)
    skipped: bool = False
    note: str = ""


def _split(records: list[dict], contract: Contract, wh: Warehouse, batch_id: str, run_date: str,
           stats: BatchStats) -> list[dict]:
    good = []
    extra_seen: set[str] = set()
    for rec in records:
        res = validate(rec, contract)
        if res.ok:
            good.append(rec)
            extra_seen.update(res.extra_fields)
        else:
            wh.quarantine(contract.name, batch_id, run_date, str(rec.get(contract.primary_key)), res.reasons, res.safe_record)
            stats.quarantined += 1
    if extra_seen:
        stats.new_drift_fields = wh.record_drift(contract.name, sorted(extra_seen), batch_id)
        for f in stats.new_drift_fields:
            logger.warning("Schema drift on %s: new field %r", contract.name, f)
    return good


def _drop_already_loaded(wh: Warehouse, contract: Contract, rows: list[dict]) -> tuple[list[dict], int]:
    """Skip records whose (key, cursor) version is already in raw."""
    if not rows:
        return rows, 0
    pk, cur = contract.primary_key, contract.cursor_field
    keys = list({r[pk] for r in rows})
    existing: set[tuple] = set()
    for i in range(0, len(keys), 500):
        chunk = keys[i:i + 500]
        marks = ", ".join("?" for _ in chunk)
        existing.update(wh.query(f"SELECT {pk}, {cur} FROM {wh.raw_table(contract.name)} WHERE {pk} IN ({marks})", tuple(chunk)))
    seen: set[tuple] = set()
    out = []
    for r in rows:
        k = (r[pk], r[cur])
        if k in existing or k in seen:
            continue
        seen.add(k)
        out.append(r)
    return out, len(rows) - len(out)


def load_database_table(wh: Warehouse, crm_db: Path, table: str, contract: Contract, run_date: str) -> BatchStats:
    """Incremental extract from an operational database using the contract's cursor field."""
    batch_id = f"{contract.name}:{run_date}"
    stats = BatchStats(contract.name, batch_id)
    if wh.batch_done(batch_id):
        stats.skipped = True
        return stats
    wh.ensure_raw_table(contract)
    wm = wh.get_watermark(contract.name)
    started = now_utc()
    src = sqlite3.connect(f"file:{crm_db}?mode=ro", uri=True)
    src.row_factory = sqlite3.Row
    try:
        cur = contract.cursor_field
        where, params = (f"WHERE {cur} > ?", (wm,)) if wm else ("", ())
        stats.control_count = src.execute(f"SELECT COUNT(*) FROM {table} {where}", params).fetchone()[0]
        rows = [dict(r) for r in src.execute(f"SELECT * FROM {table} {where} ORDER BY {cur}", params)]
    finally:
        src.close()
    stats.extracted = len(rows)
    good = _split(rows, contract, wh, batch_id, run_date, stats)
    good, stats.duplicates_skipped = _drop_already_loaded(wh, contract, good)
    stats.loaded = wh.insert_raw(contract, good, batch_id, f"db:{table}")
    new_wm = max((r[contract.cursor_field] for r in rows), default=wm)
    if new_wm:
        wh.set_watermark(contract.name, new_wm)
    wh.log_batch(batch_id=batch_id, source=contract.name, run_date=run_date, watermark_from=wm, watermark_to=new_wm,
                 extracted=stats.extracted, loaded=stats.loaded, quarantined=stats.quarantined,
                 duplicates_skipped=stats.duplicates_skipped,
                 control_count=stats.control_count, status="success", started_at=started, finished_at=now_utc())
    wh.commit()
    return stats


def _call_with_retry(fn, *args, retries: int = 5, backoff_s: float = 0.0, **kwargs):
    for attempt in range(1, retries + 1):
        try:
            return fn(*args, **kwargs)
        except TransientAPIError:
            if attempt == retries:
                raise
            time.sleep(backoff_s * 2 ** (attempt - 1))
    raise RuntimeError("unreachable")


def load_api(wh: Warehouse, api: BillingAPI, contract: Contract, run_date: str, page_size: int = 100,
             backoff_s: float = 0.0) -> BatchStats:
    """Paginated extract with retries, an overlap window and in-batch de-duplication."""
    batch_id = f"{contract.name}:{run_date}"
    stats = BatchStats(contract.name, batch_id)
    if wh.batch_done(batch_id):
        stats.skipped = True
        return stats
    wh.ensure_raw_table(contract)
    wm = wh.get_watermark(contract.name)
    since = (datetime.fromisoformat(wm) - API_OVERLAP).isoformat(timespec="seconds") if wm else None
    started = now_utc()
    rows: list[dict] = []
    page = 1
    while True:
        resp = _call_with_retry(api.list_invoices, since, page=page, page_size=page_size, backoff_s=backoff_s)
        if page == 1:
            stats.control_count = resp["total_count"]
        rows.extend(resp["data"])
        if not resp["has_more"]:
            break
        page += 1
    stats.extracted = len(rows)
    good = _split(rows, contract, wh, batch_id, run_date, stats)
    good, stats.duplicates_skipped = _drop_already_loaded(wh, contract, good)
    unique_versions = len({(r[contract.primary_key], r[contract.cursor_field]) for r in rows})
    if stats.control_count is not None and unique_versions != stats.control_count:
        stats.note = f"control mismatch: API reported {stats.control_count}, received {unique_versions} unique"
        logger.error(stats.note)
    stats.loaded = wh.insert_raw(contract, good, batch_id, "api:/invoices")
    new_wm = max((r[contract.cursor_field] for r in rows), default=wm)
    if new_wm:
        wh.set_watermark(contract.name, new_wm)
    wh.log_batch(batch_id=batch_id, source=contract.name, run_date=run_date, watermark_from=wm, watermark_to=new_wm,
                 extracted=stats.extracted, loaded=stats.loaded, quarantined=stats.quarantined,
                 duplicates_skipped=stats.duplicates_skipped,
                 control_count=stats.control_count, status="success", started_at=started, finished_at=now_utc())
    wh.commit()
    return stats


def load_event_files(wh: Warehouse, drop_dir: Path, contract: Contract, run_date: str) -> BatchStats:
    """Load new or changed NDJSON files. Events are de-duplicated on event_id at load."""
    batch_id = f"{contract.name}:{run_date}"
    stats = BatchStats(contract.name, batch_id)
    if wh.batch_done(batch_id):
        stats.skipped = True
        return stats
    wh.ensure_raw_table(contract)
    started = now_utc()
    files = sorted(p for p in drop_dir.glob("events_*.ndjson") if p.stem.split("_")[1] <= run_date)
    for path in files:
        data = path.read_bytes()
        checksum = hashlib.sha256(data).hexdigest()
        previous = wh.file_checksum(path.name)
        if previous == checksum:
            continue
        if previous is not None:  # same file delivered again with different content: replace it
            wh.conn.execute(f"DELETE FROM {wh.raw_table(contract.name)} WHERE _source_ref=?", (f"file:{path.name}",))
            stats.note += f"reloaded {path.name}; "
        records = []
        rejected = 0
        for n, line in enumerate(data.decode("utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                # Only the position is kept: a broken line could hold anything, so its content is not stored.
                wh.quarantine(contract.name, batch_id, run_date, None,
                              [f"malformed_json: {path.name} line {n}"], {"file": path.name, "line": n, "length": len(line)})
                stats.quarantined += 1
                rejected += 1
        stats.extracted += len(records)
        good = _split(records, contract, wh, batch_id, run_date, stats)
        # Cross-file duplicates: keep the first delivery of each event_id.
        ids = list({r["event_id"] for r in good})
        existing: set[str] = set()
        for i in range(0, len(ids), 500):
            chunk = ids[i:i + 500]
            marks = ", ".join("?" for _ in chunk)
            existing.update(x[0] for x in wh.query(
                f"SELECT event_id FROM {wh.raw_table(contract.name)} WHERE event_id IN ({marks})", tuple(chunk)))
        fresh, seen = [], set()
        for r in good:
            if r["event_id"] in existing or r["event_id"] in seen:
                stats.duplicates_skipped += 1
                continue
            seen.add(r["event_id"])
            fresh.append(r)
        stats.loaded += wh.insert_raw(contract, fresh, batch_id, f"file:{path.name}")
        wh.log_file(path.name, checksum, len(fresh), rejected + (len(records) - len(good)))
    wh.log_batch(batch_id=batch_id, source=contract.name, run_date=run_date, watermark_from=None, watermark_to=None,
                 extracted=stats.extracted, loaded=stats.loaded, quarantined=stats.quarantined,
                 duplicates_skipped=stats.duplicates_skipped,
                 control_count=None, status="success", started_at=started, finished_at=now_utc())
    wh.commit()
    return stats
