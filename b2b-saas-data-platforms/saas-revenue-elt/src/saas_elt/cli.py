"""Command line entry point.

    python -m saas_elt.cli simulate --workdir workdir      # 92 daily runs + report
    python -m saas_elt.cli status --workdir workdir        # last runs and open issues
    python -m saas_elt.cli erase --workdir workdir --account ACC-00042 --request-id DSR-001
"""

from __future__ import annotations

import argparse
import logging
import shutil
from pathlib import Path

from . import config
from .minidbt import DbtProject
from .pipeline import run_simulation
from .reporting import write_report
from .warehouse import Warehouse


def cmd_simulate(args: argparse.Namespace) -> None:
    workdir = Path(args.workdir)
    if workdir.exists() and args.fresh:
        shutil.rmtree(workdir)
    settings = config.RunSettings(workdir=workdir)
    res = run_simulation(settings, n_days=args.days, progress=True)
    lineage = DbtProject(config.DBT_DIR, res.warehouse.conn).lineage_mermaid()
    report = write_report(res, Path(args.output), lineage)
    print(f"Report written to {report}")


def cmd_status(args: argparse.Namespace) -> None:
    wh = Warehouse(config.RunSettings(workdir=Path(args.workdir)).warehouse_db)
    for row in wh.query("""SELECT run_date, task, MAX(attempt), status FROM meta_task_runs
                           WHERE status != 'success' GROUP BY run_date, task ORDER BY run_date DESC LIMIT 20"""):
        print(row)
    print("quarantined records by source:", wh.query("SELECT source, COUNT(*) FROM meta_quarantine GROUP BY source"))
    print("schema drift:", wh.query("SELECT source, field, first_seen_batch FROM meta_schema_drift"))


def cmd_erase(args: argparse.Namespace) -> None:
    wh = Warehouse(config.RunSettings(workdir=Path(args.workdir)).warehouse_db)
    n = wh.erase_account(args.account, args.request_id)
    print(f"Request {args.request_id}: deleted {n} rows. The erasure log keeps only a hash of the account id.")


def main() -> None:
    parser = argparse.ArgumentParser(prog="saas_elt")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("simulate")
    p.add_argument("--workdir", default="workdir")
    p.add_argument("--output", default=str(config.OUTPUT_DIR))
    p.add_argument("--days", type=int, default=config.N_DAYS)
    p.add_argument("--fresh", action="store_true", help="delete the workdir first")
    p.set_defaults(fn=cmd_simulate)
    p = sub.add_parser("status")
    p.add_argument("--workdir", default="workdir")
    p.set_defaults(fn=cmd_status)
    p = sub.add_parser("erase")
    p.add_argument("--workdir", default="workdir")
    p.add_argument("--account", required=True)
    p.add_argument("--request-id", required=True)
    p.set_defaults(fn=cmd_erase)
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    args.fn(args)


if __name__ == "__main__":
    main()
