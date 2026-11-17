"""Simulated source systems of a B2B SaaS company.

Three systems change day by day, the way a client's real stack would:

* a CRM database (SQLite file) with ``accounts`` and ``subscriptions`` tables;
* a paginated billing REST API for invoices, with control totals and
  occasional transient errors;
* a drop zone where the product team delivers daily NDJSON event files,
  with late and duplicated events.

The simulator also records the true state (MRR per day, events per day), so
the warehouse can be checked against known answers. Planted incidents
(``config.INCIDENTS``) make sure every safeguard in the pipeline gets used.

No personal data is generated: companies get invented names, users only
appear as salted hashes.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np

from . import config

_NAME_A = ("Nord", "Spree", "Alpen", "Rhein", "Elb", "Isar", "Havel", "Main", "Ruhr", "Ost", "West", "Sued")
_NAME_B = ("licht", "werk", "data", "logistik", "handel", "systeme", "energie", "bau", "netz", "tech")
_LEGAL = ("GmbH", "AG", "GmbH & Co. KG", "SE", "B.V.", "SAS", "sp. z o.o.")


def pseudonymise(value: str) -> str:
    """Salted SHA-256. The salt comes from the environment and is never committed.

    In a real deployment the product system hashes user IDs before export, so
    the warehouse never sees the raw ID (GDPR Art. 25, data protection by design).
    """
    salt = os.environ.get("EVENT_HASH_SALT", "local-simulation-only")
    return hashlib.sha256(f"{salt}|{value}".encode()).hexdigest()


class TransientAPIError(RuntimeError):
    """Raised by the fake billing API to imitate a 503 / timeout."""


def _ts(day: date, rng: np.random.Generator, start_hour: int = 7, end_hour: int = 21) -> str:
    seconds = int(rng.integers(start_hour * 3600, end_hour * 3600))
    return (datetime.combine(day, datetime.min.time()) + timedelta(seconds=seconds)).isoformat(timespec="seconds")


class CRMDatabase:
    """The client's operational CRM, stored as a SQLite file."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.conn = sqlite3.connect(path)
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS accounts (
                account_id TEXT PRIMARY KEY, company_name TEXT, country TEXT, industry TEXT,
                segment TEXT, created_at TEXT, updated_at TEXT);
            CREATE TABLE IF NOT EXISTS subscriptions (
                subscription_id TEXT PRIMARY KEY, account_id TEXT, plan TEXT, seats INTEGER,
                unit_price_eur REAL, status TEXT, start_date TEXT, end_date TEXT, updated_at TEXT);
            CREATE INDEX IF NOT EXISTS ix_acc_upd ON accounts(updated_at);
            CREATE INDEX IF NOT EXISTS ix_sub_upd ON subscriptions(updated_at);
            """
        )

    def upsert(self, table: str, row: dict) -> None:
        cols = ", ".join(row)
        marks = ", ".join("?" for _ in row)
        self.conn.execute(f"INSERT OR REPLACE INTO {table} ({cols}) VALUES ({marks})", list(row.values()))

    def commit(self) -> None:
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()


class BillingAPI:
    """In-memory stand-in for a paginated invoices endpoint.

    ``GET /invoices?updated_since=...&page=...`` returns records ordered by
    ``(updated_at, invoice_id)``. ``GET /invoices/summary`` returns control
    totals the warehouse can reconcile against.
    """

    def __init__(self, seed: int) -> None:
        self.invoices: dict[str, dict] = {}
        self.page_overlap_bug = False
        self._rng = np.random.default_rng(seed + 1_000)
        self.error_rate = 0.08
        self.calls = 0

    def list_invoices(self, updated_since: str | None, page: int = 1, page_size: int = 100) -> dict:
        self.calls += 1
        if self._rng.random() < self.error_rate:
            raise TransientAPIError("503 Service Unavailable")
        rows = sorted(
            (r for r in self.invoices.values() if updated_since is None or r["updated_at"] > updated_since),
            key=lambda r: (r["updated_at"], r["invoice_id"]),
        )
        start = (page - 1) * page_size
        if self.page_overlap_bug and page > 1:
            start -= 1  # the bug: last record of the previous page is served again
        chunk = rows[start:start + page_size]
        has_more = (page * page_size) < len(rows)
        return {"data": [dict(r) for r in chunk], "page": page, "has_more": has_more, "total_count": len(rows)}

    def summary(self) -> dict:
        """Control totals over all invoices, by invoice month and currency."""
        out: dict[str, dict] = {}
        for r in self.invoices.values():
            key = f"{r['invoice_date'][:7]}|{r['currency']}"
            agg = out.setdefault(key, {"count": 0, "amount_net": 0.0})
            agg["count"] += 1
            agg["amount_net"] = round(agg["amount_net"] + r["amount_net"], 2)
        return out


@dataclass
class Truth:
    """What really happened, kept for reconciliation and tests."""

    mrr_by_day: dict[str, float] = field(default_factory=dict)
    mrr_by_account_day: dict[tuple[str, str], float] = field(default_factory=dict)
    delivered_events_by_day: dict[str, int] = field(default_factory=dict)
    planted: list[dict] = field(default_factory=list)


class SaaSWorld:
    """Evolves accounts, subscriptions, invoices and product usage day by day."""

    def __init__(self, settings: config.RunSettings) -> None:
        self.s = settings
        self.rng = np.random.default_rng(settings.seed)
        self.start = date.fromisoformat(settings.start_date)
        self.crm = CRMDatabase(settings.crm_db)
        self.api = BillingAPI(settings.seed)
        settings.event_drop_dir.mkdir(parents=True, exist_ok=True)
        self.truth = Truth()
        self.accounts: dict[str, dict] = {}
        self.subs: dict[str, dict] = {}
        self.active_sub_of: dict[str, str] = {}
        self._next_acc = 1
        self._next_sub = 1
        self._next_inv = 1
        self._next_evt = 1
        self._pending_events: dict[str, list[dict]] = {}  # delivery date -> events
        self._open_invoices: dict[str, date] = {}  # invoice_id -> day it gets paid
        self._bootstrap()

    # ------------------------------------------------------------ setup
    def _new_account(self, created: date, ts: str) -> dict:
        aid = f"ACC-{self._next_acc:05d}"
        self._next_acc += 1
        countries = list(config.COUNTRIES)
        weights = np.array(list(config.COUNTRIES.values()))
        acc = {
            "account_id": aid,
            "company_name": f"{self.rng.choice(_NAME_A)}{self.rng.choice(_NAME_B)} {self.rng.choice(_LEGAL)}",
            "country": str(self.rng.choice(countries, p=weights / weights.sum())),
            "industry": str(self.rng.choice(config.INDUSTRIES)),
            "segment": str(self.rng.choice(config.SEGMENTS, p=[0.6, 0.3, 0.1])),
            "created_at": f"{created.isoformat()}T09:00:00",
            "updated_at": ts,
        }
        self.accounts[aid] = acc
        self.crm.upsert("accounts", acc)
        return acc

    def _new_subscription(self, acc: dict, start: date, ts: str) -> dict:
        sid = f"SUB-{self._next_sub:05d}"
        self._next_sub += 1
        plan = str(self.rng.choice(list(config.PLANS), p=[0.5, 0.35, 0.15]))
        seat_scale = {"SMB": 4, "MidMarket": 15, "Enterprise": 45}[acc["segment"]]
        sub = {
            "subscription_id": sid,
            "account_id": acc["account_id"],
            "plan": plan,
            "seats": int(max(1, self.rng.poisson(seat_scale))),
            "unit_price_eur": config.PLANS[plan],
            "status": "active",
            "start_date": start.isoformat(),
            "end_date": None,
            "updated_at": ts,
        }
        self.subs[sid] = sub
        self.active_sub_of[acc["account_id"]] = sid
        self.crm.upsert("subscriptions", sub)
        return sub

    def _bootstrap(self) -> None:
        """Accounts that already existed before the warehouse goes live."""
        for _ in range(self.s.initial_accounts):
            created = self.start - timedelta(days=int(self.rng.integers(30, 900)))
            ts = f"{(self.start - timedelta(days=1)).isoformat()}T12:00:00"
            acc = self._new_account(created, ts)
            sub_start = created + timedelta(days=int(self.rng.integers(0, 20)))
            self._new_subscription(acc, sub_start, ts)
        self.crm.commit()

    # ------------------------------------------------------------ helpers
    def day(self, i: int) -> date:
        return self.start + timedelta(days=i)

    def _billing_day(self, sub: dict) -> int:
        return min(date.fromisoformat(sub["start_date"]).day, 28)

    def _issue_invoice(self, sub: dict, d: date, ts: str) -> None:
        acc = self.accounts[sub["account_id"]]
        net_eur = round(sub["seats"] * sub["unit_price_eur"], 2)
        currency = "CHF" if acc["country"] == "CH" else "EUR"
        net = round(net_eur * config.CHF_PER_EUR, 2) if currency == "CHF" else net_eur
        tax = config.TAX_RATES[acc["country"]]
        iid = f"INV-{self._next_inv:06d}"
        self._next_inv += 1
        period_end = (d + timedelta(days=31)).replace(day=min(d.day, 28)) - timedelta(days=1)
        inv = {
            "invoice_id": iid,
            "account_id": acc["account_id"],
            "subscription_id": sub["subscription_id"],
            "invoice_date": d.isoformat(),
            "period_start": d.isoformat(),
            "period_end": period_end.isoformat(),
            "currency": currency,
            "amount_net": net,
            "tax_rate": tax,
            "amount_gross": round(net * (1 + tax), 2),
            "status": "open",
            "updated_at": ts,
        }
        self.api.invoices[iid] = inv
        self._open_invoices[iid] = d + timedelta(days=int(self.rng.integers(3, 21)))

    def _emit_events(self, d: date, i: int) -> None:
        for aid, sid in self.active_sub_of.items():
            seats = self.subs[sid]["seats"]
            n = int(min(self.rng.poisson(0.12 * seats + 0.5), 60))
            for _ in range(n):
                eid = f"EVT-{self._next_evt:08d}"
                self._next_evt += 1
                user = int(self.rng.integers(1, seats + 1))
                evt = {
                    "event_id": eid,
                    "account_id": aid,
                    "user_hash": pseudonymise(f"{aid}|{user}"),
                    "event_type": str(self.rng.choice(config.EVENT_TYPES, p=[0.35, 0.15, 0.3, 0.1, 0.1])),
                    "event_ts": _ts(d, self.rng, 0, 24),
                }
                r = self.rng.random()
                lag = 0 if r < 0.96 else (1 if r < 0.99 else 2)
                deliver = (d + timedelta(days=lag)).isoformat()
                self._pending_events.setdefault(deliver, []).append(evt)
                if self.rng.random() < 0.005:  # duplicate delivery, sometimes a day later
                    dup_day = (d + timedelta(days=int(self.rng.integers(0, 2)))).isoformat()
                    self._pending_events.setdefault(dup_day, []).append(dict(evt))

    def _write_event_file(self, d: date, malformed: bool) -> None:
        events = self._pending_events.pop(d.isoformat(), [])
        path = self.s.event_drop_dir / f"events_{d.isoformat()}.ndjson"
        lines = [json.dumps(e, sort_keys=True) for e in events]
        if malformed and lines:
            for k in range(5):
                pos = int(self.rng.integers(0, len(lines)))
                lines[pos] = lines[pos][: len(lines[pos]) // 2]  # truncated line, broken JSON
                self.truth.planted.append({"day": d.isoformat(), "incident": "malformed_event_line", "line": pos})
        path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        seen: set[str] = set()
        for line in lines:
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            if e["event_id"] in seen:
                continue
            seen.add(e["event_id"])
        # Count delivered unique events per event date (duplicates across files handled below).
        self._delivered_ids = getattr(self, "_delivered_ids", {})
        for line in lines:
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            if e["event_id"] not in self._delivered_ids:
                self._delivered_ids[e["event_id"]] = e["event_ts"][:10]

    # ------------------------------------------------------------ one day
    def step(self, i: int) -> date:
        """Advance the world by one day and publish the day's data."""
        d = self.day(i)
        incident = self.s.incidents.get(i)
        self.api.page_overlap_bug = incident == "api_page_overlap"
        changed_today: set[str] = set()

        # New customers.
        for _ in range(int(self.rng.poisson(1.2))):
            ts = _ts(d, self.rng)
            acc = self._new_account(d, ts)
            self._new_subscription(acc, d, ts)
            changed_today.add(self.active_sub_of[acc["account_id"]])

        # Changes to existing subscriptions (at most one per subscription per day).
        for aid, sid in list(self.active_sub_of.items()):
            if sid in changed_today:
                continue
            sub = self.subs[sid]
            r = self.rng.random()
            ts = _ts(d, self.rng)
            if r < 0.0009:  # churn
                sub.update(status="cancelled", end_date=d.isoformat(), updated_at=ts)
                del self.active_sub_of[aid]
            elif r < 0.0049:  # expansion
                sub.update(seats=sub["seats"] + int(self.rng.integers(1, 4)), updated_at=ts)
            elif r < 0.0069:  # contraction
                if sub["seats"] > 1:
                    sub.update(seats=max(1, sub["seats"] - int(self.rng.integers(1, 4))), updated_at=ts)
            elif r < 0.0079:  # plan change
                new_plan = str(self.rng.choice([p for p in config.PLANS if p != sub["plan"]]))
                sub.update(plan=new_plan, unit_price_eur=config.PLANS[new_plan], updated_at=ts)
            else:
                continue
            self.crm.upsert("subscriptions", sub)
            changed_today.add(sid)

        # Win-backs: a churned account starts a new subscription.
        churned = [a for a in self.accounts if a not in self.active_sub_of]
        for aid in churned:
            if self.rng.random() < 0.01:
                ts = _ts(d, self.rng)
                acc = self.accounts[aid]
                acc["updated_at"] = ts
                self.crm.upsert("accounts", acc)
                sub = self._new_subscription(acc, d, ts)
                changed_today.add(sub["subscription_id"])

        # Account attribute changes (segment moves, industry fixes).
        for aid, acc in self.accounts.items():
            if self.rng.random() < 0.002:
                acc.update(segment=str(self.rng.choice(config.SEGMENTS)), updated_at=_ts(d, self.rng))
                self.crm.upsert("accounts", acc)
        if incident == "bad_segment_value":
            aid = sorted(self.accounts)[17]
            bad = dict(self.accounts[aid], segment="Mid-Market", updated_at=_ts(d, self.rng, 21, 22))
            self.crm.upsert("accounts", bad)
            self.truth.planted.append({"day": d.isoformat(), "incident": "bad_segment_value", "account_id": aid})
            self._fix_segment = aid
        elif getattr(self, "_fix_segment", None):
            # The CRM team corrects the value the next morning.
            aid = self._fix_segment
            self.accounts[aid].update(segment="MidMarket", updated_at=_ts(d, self.rng, 8, 9))
            self.crm.upsert("accounts", self.accounts[aid])
            self._fix_segment = None
        self.crm.commit()

        # Billing: invoices on each subscription's billing day, then payments.
        for sid in self.active_sub_of.values():
            sub = self.subs[sid]
            if self._billing_day(sub) == d.day or sub["start_date"] == d.isoformat():
                if sub["start_date"] == d.isoformat() or date.fromisoformat(sub["start_date"]) < d:
                    self._issue_invoice(sub, d, _ts(d, self.rng, 22, 23))
        for iid, pay_day in list(self._open_invoices.items()):
            if pay_day == d:
                inv = self.api.invoices[iid]
                inv.update(status="void" if self.rng.random() < 0.02 else "paid", updated_at=_ts(d, self.rng))
                del self._open_invoices[iid]
        if incident == "schema_drift" or (i > 34 and "schema_drift" in self.s.incidents.values()):
            for inv in self.api.invoices.values():
                if inv["updated_at"][:10] == d.isoformat():
                    inv.setdefault("discount_eur", round(float(self.rng.choice([0.0, 0.0, 5.0, 10.0])), 2))
        if incident == "negative_invoice":
            sid = sorted(self.active_sub_of.values())[3]
            self._issue_invoice(self.subs[sid], d, _ts(d, self.rng, 22, 23))
            bad = self.api.invoices[f"INV-{self._next_inv - 1:06d}"]
            bad["amount_net"] = -abs(bad["amount_net"])
            bad["amount_gross"] = round(bad["amount_net"] * (1 + bad["tax_rate"]), 2)
            self.truth.planted.append({"day": d.isoformat(), "incident": "negative_invoice", "invoice_id": bad["invoice_id"]})

        # Product usage.
        self._emit_events(d, i)
        self._write_event_file(d, malformed=incident == "malformed_event_lines")

        # Truth at end of day.
        total = 0.0
        for aid, sid in self.active_sub_of.items():
            mrr = round(self.subs[sid]["seats"] * self.subs[sid]["unit_price_eur"], 2)
            self.truth.mrr_by_account_day[(aid, d.isoformat())] = mrr
            total += mrr
        self.truth.mrr_by_day[d.isoformat()] = round(total, 2)
        if incident:
            self.truth.planted.append({"day": d.isoformat(), "incident": incident})
        return d

    def delivered_events_by_day(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for evt_day in getattr(self, "_delivered_ids", {}).values():
            counts[evt_day] = counts.get(evt_day, 0) + 1
        return counts

    def close(self) -> None:
        self.crm.close()
