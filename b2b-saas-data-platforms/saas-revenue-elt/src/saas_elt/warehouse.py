"""The warehouse: raw landing tables plus the metadata that makes loads safe.

SQLite stands in for Snowflake/BigQuery here. The raw layer is append-only:
every extracted record is stored with its batch id, load time and source, so
any downstream table can be rebuilt and every number traced to a batch.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .contracts import Contract

META_DDL = """
CREATE TABLE IF NOT EXISTS meta_watermarks (
    source TEXT PRIMARY KEY, watermark TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS meta_batches (
    batch_id TEXT PRIMARY KEY, source TEXT, run_date TEXT, watermark_from TEXT, watermark_to TEXT,
    extracted INTEGER, loaded INTEGER, quarantined INTEGER, duplicates_skipped INTEGER, control_count INTEGER,
    status TEXT, started_at TEXT, finished_at TEXT);
CREATE TABLE IF NOT EXISTS meta_quarantine (
    batch_id TEXT, source TEXT, record_key TEXT, reasons TEXT, payload_json TEXT, run_date TEXT, quarantined_at TEXT);
CREATE TABLE IF NOT EXISTS meta_schema_drift (
    source TEXT, field TEXT, first_seen_batch TEXT, first_seen_at TEXT, PRIMARY KEY (source, field));
CREATE TABLE IF NOT EXISTS meta_files (
    file_name TEXT PRIMARY KEY, checksum TEXT, rows_loaded INTEGER, rows_rejected INTEGER, loaded_at TEXT);
CREATE TABLE IF NOT EXISTS meta_task_runs (
    run_id TEXT, run_date TEXT, task TEXT, attempt INTEGER, status TEXT, started_at TEXT,
    finished_at TEXT, duration_s REAL, message TEXT);
CREATE TABLE IF NOT EXISTS meta_reconciliation (
    run_id TEXT, run_date TEXT, check_name TEXT, expected REAL, actual REAL, difference REAL,
    explained REAL, status TEXT, detail TEXT);
CREATE TABLE IF NOT EXISTS meta_test_results (
    run_id TEXT, run_date TEXT, test_name TEXT, model TEXT, status TEXT, failures INTEGER, severity TEXT);
CREATE TABLE IF NOT EXISTS meta_erasure_log (
    request_id TEXT, subject_type TEXT, subject_hash TEXT, rows_deleted INTEGER, executed_at TEXT);
"""

SQL_TYPES = {"string": "TEXT", "date": "TEXT", "datetime": "TEXT", "integer": "INTEGER", "number": "REAL"}


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Warehouse:
    """Thin wrapper around the warehouse connection."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.conn = sqlite3.connect(path)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(META_DDL)

    # ------------------------------------------------------------ raw layer
    @staticmethod
    def raw_table(source: str) -> str:
        return f"raw_{source}"

    def ensure_raw_table(self, contract: Contract) -> None:
        cols = ", ".join(f"{n} {SQL_TYPES[f.type]}" for n, f in contract.fields.items())
        self.conn.execute(
            f"CREATE TABLE IF NOT EXISTS {self.raw_table(contract.name)} ("
            f"{cols}, _extra_json TEXT, _batch_id TEXT, _source_ref TEXT, _loaded_at TEXT)"
        )
        self.conn.execute(
            f"CREATE INDEX IF NOT EXISTS ix_{contract.name}_pk ON {self.raw_table(contract.name)}({contract.primary_key})"
        )

    def insert_raw(self, contract: Contract, rows: list[dict], batch_id: str, source_ref: str) -> int:
        if not rows:
            return 0
        cols = contract.columns
        loaded_at = now_utc()
        values = []
        for r in rows:
            extra = {k: v for k, v in r.items() if k not in contract.fields}
            values.append([r.get(c) for c in cols] + [json.dumps(extra, sort_keys=True) if extra else None,
                                                     batch_id, source_ref, loaded_at])
        marks = ", ".join("?" for _ in range(len(cols) + 4))
        self.conn.executemany(
            f"INSERT INTO {self.raw_table(contract.name)} ({', '.join(cols)}, _extra_json, _batch_id, _source_ref, _loaded_at) "
            f"VALUES ({marks})",
            values,
        )
        return len(values)

    def quarantine(self, source: str, batch_id: str, run_date: str, key: str | None, reasons: list[str],
                   safe_payload: dict | str) -> None:
        payload = safe_payload if isinstance(safe_payload, str) else json.dumps(safe_payload, sort_keys=True, default=str)
        self.conn.execute(
            "INSERT INTO meta_quarantine VALUES (?, ?, ?, ?, ?, ?, ?)",
            (batch_id, source, key, "; ".join(reasons), payload[:2_000], run_date, now_utc()),
        )

    def record_drift(self, source: str, fields: list[str], batch_id: str) -> list[str]:
        """Store fields seen for the first time. Returns only the new ones."""
        new = []
        for f in fields:
            cur = self.conn.execute("SELECT 1 FROM meta_schema_drift WHERE source=? AND field=?", (source, f))
            if cur.fetchone() is None:
                self.conn.execute("INSERT INTO meta_schema_drift VALUES (?, ?, ?, ?)", (source, f, batch_id, now_utc()))
                new.append(f)
        return new

    # ------------------------------------------------------------ state
    def get_watermark(self, source: str) -> str | None:
        row = self.conn.execute("SELECT watermark FROM meta_watermarks WHERE source=?", (source,)).fetchone()
        return row[0] if row else None

    def set_watermark(self, source: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO meta_watermarks VALUES (?, ?, ?) ON CONFLICT(source) DO UPDATE SET watermark=excluded.watermark, updated_at=excluded.updated_at",
            (source, value, now_utc()),
        )

    def batch_done(self, batch_id: str) -> bool:
        row = self.conn.execute("SELECT status FROM meta_batches WHERE batch_id=?", (batch_id,)).fetchone()
        return bool(row and row[0] == "success")

    def log_batch(self, **kw) -> None:
        cols = ", ".join(kw)
        marks = ", ".join("?" for _ in kw)
        self.conn.execute(f"INSERT OR REPLACE INTO meta_batches ({cols}) VALUES ({marks})", list(kw.values()))

    def file_checksum(self, file_name: str) -> str | None:
        row = self.conn.execute("SELECT checksum FROM meta_files WHERE file_name=?", (file_name,)).fetchone()
        return row[0] if row else None

    def log_file(self, file_name: str, checksum: str, loaded: int, rejected: int) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO meta_files VALUES (?, ?, ?, ?, ?)", (file_name, checksum, loaded, rejected, now_utc())
        )

    def log_task(self, **kw) -> None:
        cols = ", ".join(kw)
        marks = ", ".join("?" for _ in kw)
        self.conn.execute(f"INSERT INTO meta_task_runs ({cols}) VALUES ({marks})", list(kw.values()))
        self.conn.commit()

    # ------------------------------------------------------------ privacy
    def erase_account(self, account_id: str, request_id: str) -> int:
        """Delete every row about one customer account (GDPR Art. 17 request).

        Raw tables, quarantine and every model table with an ``account_id``
        column are cleared. The log keeps only a hash of the account id.
        """
        import hashlib

        deleted = 0
        tables = [r[0] for r in self.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        for t in tables:
            cols = [c[1] for c in self.conn.execute(f"PRAGMA table_info({t})")]
            if "account_id" in cols:
                deleted += self.conn.execute(f"DELETE FROM {t} WHERE account_id=?", (account_id,)).rowcount
        deleted += self.conn.execute(
            "DELETE FROM meta_quarantine WHERE payload_json LIKE ?", (f'%"{account_id}"%',)
        ).rowcount
        self.conn.execute(
            "INSERT INTO meta_erasure_log VALUES (?, 'account', ?, ?, ?)",
            (request_id, hashlib.sha256(account_id.encode()).hexdigest(), deleted, now_utc()),
        )
        self.conn.commit()
        return deleted

    def purge_quarantine(self, older_than_days: int, today: str) -> int:
        """Retention: quarantined payloads are not kept forever."""
        cutoff = (datetime.fromisoformat(today) - timedelta(days=older_than_days)).date().isoformat()
        n = self.conn.execute("DELETE FROM meta_quarantine WHERE run_date < ?", (cutoff,)).rowcount
        self.conn.commit()
        return n

    def query(self, sql: str, params: tuple = ()) -> list[tuple]:
        return self.conn.execute(sql, params).fetchall()

    def commit(self) -> None:
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()
