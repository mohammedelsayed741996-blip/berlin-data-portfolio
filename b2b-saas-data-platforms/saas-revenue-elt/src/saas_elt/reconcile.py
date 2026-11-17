"""Reconciliation: prove that what landed in the warehouse matches the sources.

Every check writes a row to ``meta_reconciliation`` with the expected value,
the actual value, how much of any difference is explained (for example by
quarantined records) and a status. An unexplained difference fails the run.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime

from .contracts import Contract
from .simulator import BillingAPI
from .warehouse import Warehouse

TOLERANCE_EUR = 0.01


@dataclass
class Check:
    name: str
    expected: float
    actual: float
    explained: float = 0.0
    status: str = "pass"
    detail: str = ""

    @property
    def difference(self) -> float:
        return round(self.expected - self.actual, 2)


def _save(wh: Warehouse, run_id: str, run_date: str, checks: list[Check]) -> None:
    wh.conn.executemany(
        "INSERT INTO meta_reconciliation VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [(run_id, run_date, c.name, c.expected, c.actual, c.difference, c.explained, c.status, c.detail) for c in checks],
    )
    wh.commit()


def control_counts(wh: Warehouse, run_date: str) -> list[Check]:
    """Records the source said it had vs records actually received in this run's batches."""
    out = []
    rows = wh.query(
        "SELECT source, control_count, extracted, loaded, quarantined FROM meta_batches "
        "WHERE run_date=? AND control_count IS NOT NULL", (run_date,))
    for source, control, extracted, loaded, quarantined in rows:
        c = Check(f"control_count:{source}", float(control), float(extracted))
        if extracted < control:
            c.status = "fail"
            c.detail = "records missing from extract"
        elif extracted > control:
            c.explained = float(extracted - control)
            c.status = "pass"
            c.detail = f"{extracted - control} duplicate deliveries removed before load"
        out.append(c)
    return out


def raw_vs_staging(wh: Warehouse, contracts: dict[str, Contract]) -> list[Check]:
    """Distinct keys that passed the contract vs rows in the staging model."""
    pairs = {"crm_accounts": "stg_crm__accounts", "crm_subscriptions": "stg_crm__subscriptions",
             "billing_invoices": "stg_billing__invoices", "product_events": "stg_events__product_events"}
    out = []
    for source, model in pairs.items():
        pk = contracts[source].primary_key
        raw_n = wh.query(f"SELECT COUNT(DISTINCT {pk}) FROM {wh.raw_table(source)}")[0][0]
        stg_n = wh.query(f"SELECT COUNT(*) FROM {model}")[0][0]
        out.append(Check(f"raw_vs_staging:{source}", float(raw_n), float(stg_n),
                         status="pass" if raw_n == stg_n else "fail"))
    return out


def invoices_vs_api(wh: Warehouse, api: BillingAPI) -> list[Check]:
    """Invoice totals per month and currency vs the billing API's control totals.

    A gap is acceptable only if quarantined invoices explain it to the cent.
    """
    loaded = {(m, c): (n, s) for m, c, n, s in wh.query(
        "SELECT substr(invoice_date, 1, 7), currency, COUNT(*), ROUND(SUM(amount_net), 2) FROM fct_invoices GROUP BY 1, 2")}
    in_fct = {r[0] for r in wh.query("SELECT invoice_id FROM fct_invoices")}
    # The same bad invoice can be re-delivered (e.g. when its status changes); count its latest version once.
    latest: dict[str, dict] = {}
    for key, payload in wh.query(
            "SELECT record_key, payload_json FROM meta_quarantine WHERE source='billing_invoices' ORDER BY rowid"):
        latest[key] = json.loads(payload)
    quarantined: dict[tuple[str, str], float] = {}
    for key, rec in latest.items():
        if key in in_fct:
            continue
        k = (rec["invoice_date"][:7], rec["currency"])
        quarantined[k] = round(quarantined.get(k, 0.0) + float(rec["amount_net"]), 2)
    out = []
    for key, agg in sorted(api.summary().items()):
        month, cur = key.split("|")
        actual = loaded.get((month, cur), (0, 0.0))[1]
        explained = quarantined.get((month, cur), 0.0)
        c = Check(f"invoice_total:{month}:{cur}", agg["amount_net"], actual, explained)
        unexplained = round(c.difference - explained, 2)
        c.status = "pass" if abs(unexplained) <= TOLERANCE_EUR else "fail"
        if explained:
            c.detail = f"EUR/CHF {explained:,.2f} held in quarantine"
        out.append(c)
    return out


def mrr_vs_truth(wh: Warehouse, run_date: str, truth_mrr: float) -> Check:
    """Simulation-only oracle: warehouse MRR vs the simulator's true MRR."""
    actual = wh.query("SELECT COALESCE(SUM(mrr_eur), 0) FROM fct_mrr_daily WHERE date_day=?", (run_date,))[0][0]
    c = Check("mrr_vs_truth", truth_mrr, round(actual, 2))
    c.status = "pass" if abs(c.difference) <= TOLERANCE_EUR else "fail"
    return c


def freshness(wh: Warehouse, contracts: dict[str, Contract], run_date: str) -> list[Check]:
    """Hours between the end of the run date and the newest record of each source."""
    end = datetime.fromisoformat(f"{run_date}T23:59:59")
    out = []
    for name, ct in contracts.items():
        newest = wh.query(f"SELECT MAX({ct.cursor_field}) FROM {wh.raw_table(name)}")[0][0]
        if newest is None:
            continue
        lag_h = round((end - datetime.fromisoformat(newest)).total_seconds() / 3600, 1)
        out.append(Check(f"freshness_hours:{name}", float(ct.freshness_hours), lag_h,
                         status="pass" if lag_h <= ct.freshness_hours else "warn"))
    return out


def run_all(wh: Warehouse, run_id: str, run_date: str, contracts: dict[str, Contract], api: BillingAPI,
            truth_mrr: float | None = None) -> list[Check]:
    checks = control_counts(wh, run_date) + raw_vs_staging(wh, contracts) + invoices_vs_api(wh, api)
    checks += freshness(wh, contracts, run_date)
    if truth_mrr is not None:
        checks.append(mrr_vs_truth(wh, run_date, truth_mrr))
    _save(wh, run_id, run_date, checks)
    return checks
