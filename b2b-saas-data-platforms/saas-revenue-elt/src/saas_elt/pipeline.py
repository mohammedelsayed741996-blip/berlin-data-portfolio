"""The daily ELT DAG and a simulation that runs it for every day of a quarter.

Daily DAG::

    extract_crm_accounts ─┐
    extract_crm_subscriptions ─┤
    extract_billing_invoices ──┼─> transform ─┬─> test ───────┬─> housekeeping
    load_product_events ───────┘              └─> reconcile ──┴─> publish
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta

from . import config, ingest, reconcile
from .contracts import Contract, load_contract
from .minidbt import DbtProject
from .orchestrator import DAG, DagRun, Task
from .simulator import SaaSWorld
from .warehouse import Warehouse

logger = logging.getLogger(__name__)

SOURCES = ("crm_accounts", "crm_subscriptions", "billing_invoices", "product_events")
QUARANTINE_RETENTION_DAYS = 90


class DataTestFailure(RuntimeError):
    """Raised when a data test with severity 'error' fails."""


class ReconciliationFailure(RuntimeError):
    """Raised when a reconciliation check finds an unexplained difference."""


def load_contracts() -> dict[str, Contract]:
    return {name: load_contract(name) for name in SOURCES}


def build_dag(settings: config.RunSettings, world: SaaSWorld, wh: Warehouse, contracts: dict[str, Contract],
              opening_date: str) -> DAG:
    """Wire the daily tasks. ``ctx`` carries run_date, run_id and flags per run."""

    def extract_accounts(ctx):
        return ingest.load_database_table(wh, settings.crm_db, "accounts", contracts["crm_accounts"], ctx["run_date"])

    def extract_subs(ctx):
        return ingest.load_database_table(wh, settings.crm_db, "subscriptions", contracts["crm_subscriptions"], ctx["run_date"])

    def extract_invoices(ctx):
        return ingest.load_api(wh, world.api, contracts["billing_invoices"], ctx["run_date"],
                               page_size=25, backoff_s=settings.retry_backoff_s)

    def load_events(ctx):
        return ingest.load_event_files(wh, settings.event_drop_dir, contracts["product_events"], ctx["run_date"])

    def transform(ctx):
        project = DbtProject(config.DBT_DIR, wh.conn, vars={"start_date": opening_date, "run_date": ctx["run_date"]})
        fail_on = {"fct_mrr_daily"} if ctx.get("simulate_outage") else None
        return project.run(fail_on=fail_on)

    def test(ctx):
        project = DbtProject(config.DBT_DIR, wh.conn, vars={"start_date": opening_date, "run_date": ctx["run_date"]})
        results = project.test()
        wh.conn.executemany(
            "INSERT INTO meta_test_results VALUES (?, ?, ?, ?, ?, ?, ?)",
            [(ctx["run_id"], ctx["run_date"], r.name, r.model, r.status, r.failures, r.severity) for r in results],
        )
        wh.commit()
        bad = [r for r in results if r.status in ("fail", "error")]
        if bad:
            raise DataTestFailure(", ".join(f"{r.name} ({r.failures})" for r in bad))
        return results

    def recon(ctx):
        truth = world.truth.mrr_by_day.get(ctx["run_date"])
        checks = reconcile.run_all(wh, ctx["run_id"], ctx["run_date"], contracts, world.api, truth)
        bad = [c for c in checks if c.status == "fail"]
        if bad:
            raise ReconciliationFailure(", ".join(c.name for c in bad))
        return checks

    def housekeeping(ctx):
        return wh.purge_quarantine(QUARANTINE_RETENTION_DAYS, ctx["run_date"])

    def publish(ctx):
        # In production this would refresh the BI semantic layer; here it records the day's headline numbers.
        mrr = wh.query("SELECT COALESCE(SUM(mrr_eur), 0) FROM fct_mrr_daily WHERE date_day=?", (ctx["run_date"],))[0][0]
        return {"run_date": ctx["run_date"], "mrr_eur": round(mrr, 2)}

    return DAG("saas_revenue_daily", [
        Task("extract_crm_accounts", extract_accounts),
        Task("extract_crm_subscriptions", extract_subs),
        Task("extract_billing_invoices", extract_invoices),
        Task("load_product_events", load_events),
        Task("transform", transform, ["extract_crm_accounts", "extract_crm_subscriptions",
                                      "extract_billing_invoices", "load_product_events"]),
        Task("test", test, ["transform"], retries=0),
        Task("reconcile", recon, ["transform"], retries=0),
        Task("housekeeping", housekeeping, ["test"]),
        Task("publish", publish, ["test", "reconcile"], retries=0),
    ])


@dataclass
class SimulationResult:
    settings: config.RunSettings
    world: SaaSWorld
    warehouse: Warehouse
    runs: list[DagRun] = field(default_factory=list)


def run_simulation(settings: config.RunSettings, n_days: int | None = None, progress: bool = False) -> SimulationResult:
    """Initial load on the opening date, then one DAG run per simulated day."""
    n_days = settings.n_days if n_days is None else n_days
    world = SaaSWorld(settings)
    wh = Warehouse(settings.warehouse_db)
    contracts = load_contracts()
    opening = (date.fromisoformat(settings.start_date) - timedelta(days=1)).isoformat()
    dag = build_dag(settings, world, wh, contracts, opening)
    result = SimulationResult(settings, world, wh)

    world.truth.mrr_by_day[opening] = round(sum(
        world.subs[s]["seats"] * world.subs[s]["unit_price_eur"] for s in world.active_sub_of.values()), 2)
    result.runs.append(dag.run(wh, opening, {}, settings.retry_backoff_s))
    for i in range(n_days):
        d = world.step(i).isoformat()
        flags = {"simulate_outage": settings.incidents.get(i) == "transform_outage"}
        run = dag.run(wh, d, flags, settings.retry_backoff_s)
        result.runs.append(run)
        if progress and (i % 15 == 0 or run.status != "success"):
            print(f"{d}: {run.status}" + (f" ({', '.join(run.failed_tasks())})" if run.status != "success" else ""))
    return result
