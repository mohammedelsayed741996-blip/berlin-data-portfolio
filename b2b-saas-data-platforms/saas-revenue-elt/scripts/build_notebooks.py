"""Build and execute the project notebooks without Jupyter.

Notebook cells are defined here; each code cell runs in one shared namespace
(like a kernel) and its printed output, last expression and images are saved
as real notebook outputs, so the files open with results in Jupyter, GitHub
and Google Colab.

Run from the project folder:  python scripts/build_notebooks.py
"""

from __future__ import annotations

import ast
import base64
import contextlib
import io
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("MPLBACKEND", "Agg")
PROJECT = Path(__file__).resolve().parents[1]
NB_DIR = PROJECT / "notebooks"
BASE = "https://colab.research.google.com/github/mohammedelsayed741996-blip/berlin-data-portfolio/blob/main/b2b-saas-data-platforms/saas-revenue-elt/notebooks"

SETUP = '''import os, sys, subprocess, warnings
from pathlib import Path

REPO = "https://github.com/mohammedelsayed741996-blip/berlin-data-portfolio.git"
PROJECT = "b2b-saas-data-platforms/saas-revenue-elt"

if "google.colab" in sys.modules:
    if not Path("/content/berlin-data-portfolio").exists():
        subprocess.run(["git", "clone", "--depth", "1", REPO, "/content/berlin-data-portfolio"], check=True)
    os.chdir(f"/content/berlin-data-portfolio/{PROJECT}")
else:
    here = Path.cwd()
    while not (here / "src" / "saas_elt").exists() and here != here.parent:
        here = here.parent
    os.chdir(here)

sys.path.insert(0, str(Path.cwd() / "src"))
warnings.filterwarnings("ignore")
import logging, shutil
logging.basicConfig(level=logging.ERROR)
import pandas as pd
pd.set_option("display.max_columns", 30)
pd.set_option("display.width", 160)
pd.set_option("display.max_colwidth", 90)
from IPython.display import Image, display
print("Project folder:", Path.cwd().name)'''

RUN_SIM = '''from saas_elt import config
from saas_elt.pipeline import run_simulation
from saas_elt import reporting

workdir = Path("workdir/notebook_run")
if workdir.exists():
    shutil.rmtree(workdir)
sim = run_simulation(config.RunSettings(workdir=workdir), progress=True)
wh = sim.warehouse
q = lambda sql: pd.read_sql_query(sql, wh.conn)
print(f"{len(sim.runs)} daily runs, {sum(r.status == 'success' for r in sim.runs)} successful")'''


def md(text: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": text.strip("\n")}


def code(text: str) -> dict:
    return {"cell_type": "code", "metadata": {}, "source": text.strip("\n"), "execution_count": None, "outputs": []}


def badge(name: str) -> str:
    return f"[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)]({BASE}/{name})"


NB1 = [
    md(f"""
# 01 · Daily runs and incidents

{badge("01_daily_runs_and_incidents.ipynb")}

A client runs a B2B SaaS product. Revenue data sits in three places: a CRM database (accounts, subscriptions), a billing REST API (invoices) and daily NDJSON files from the product team (usage events). This notebook runs the full pipeline once a day for a simulated quarter, from an initial load on 30 June 2026 to 30 September, and shows what happened on the days something went wrong.

Six incidents are planted on purpose: a paging bug in the API, a new field nobody announced, an invalid value in the CRM, a negative invoice, broken lines in an event file and a warehouse outage. Late and duplicated events happen every day.
"""),
    code(SETUP),
    md("## Run 93 days\n\nEach day the simulator changes the source systems, then the DAG extracts, validates, loads, transforms, tests and reconciles. Takes about half a minute."),
    code(RUN_SIM),
    code('''status = reporting.run_status(sim)
status[status["status"] != "success"]'''),
    md("""
## What went wrong, and what the pipeline did

Each row pairs a planted incident with the evidence it left in the metadata tables. None of them stopped the business numbers from being right: the outage day failed loudly and the next run caught up.
"""),
    code('''reporting.incident_log(sim)'''),
    md("## Daily loads\n\nRed dots mark days with quarantined records."),
    code('''display(Image(filename=str(reporting.plot_daily_loads(sim, Path("outputs/figures/daily_loads.png")))))
reporting.daily_loads(sim).query("run_date == '2026-07-20'")'''),
    md("""
## The quarantine

Records that break their contract never reach the raw tables. They wait here with the reasons. Personal data would be masked before landing here, and broken event lines are stored by file and line number only, because their content could be anything.
"""),
    code('''q("SELECT run_date, source, record_key, reasons, substr(payload_json, 1, 80) AS payload FROM meta_quarantine")'''),
    code('''q("SELECT * FROM meta_schema_drift")'''),
    md("## The outage day\n\nThe transform task failed three times (one try plus two retries). Tests, reconciliation and publishing were skipped instead of running on stale tables. The next morning's run rebuilt everything from the raw layer."),
    code('''q("SELECT run_date, task, attempt, status, message FROM meta_task_runs WHERE run_date IN ('2026-09-13', '2026-09-14') AND task IN ('transform', 'publish', 'reconcile')")'''),
]

NB2 = [
    md(f"""
# 02 · Reconciliation, idempotency and privacy

{badge("02_reconciliation_and_privacy.ipynb")}

Tests check that tables are internally sound. Reconciliation checks that they agree with the systems they came from. This notebook goes through the checks, proves that re-running a day changes nothing, and walks through the GDPR controls.
"""),
    code(SETUP),
    code(RUN_SIM),
    md("## Reconciliation results\n\nFive checks run after every transform: control counts per batch, raw keys vs staging rows, invoice totals vs the billing API, freshness, and (only possible in a simulation) MRR against the true value."),
    code('''q("SELECT substr(check_name, 1, instr(check_name || ':', ':') - 1) AS check_type, status, COUNT(*) AS checks FROM meta_reconciliation GROUP BY 1, 2")'''),
    md("The billing API reports its own totals. In August the warehouse is EUR 295 *above* the API, because one invoice with a negative amount was quarantined. The check passes only because the quarantine explains the gap to the cent."),
    code('''q("SELECT check_name, expected, actual, difference, explained, status, detail FROM meta_reconciliation WHERE run_date = '2026-09-30' AND check_name LIKE 'invoice_total%'")'''),
    md("## Known answers\n\nThe simulator keeps the true MRR for every day. The warehouse rebuilds it from the history of subscription versions (SCD type 2), so it has to get every expansion, downgrade, churn and win-back right."),
    code('''mrr = reporting.mrr_vs_truth(sim)
display(Image(filename=str(reporting.plot_mrr_vs_truth(sim, Path("outputs/figures/mrr_vs_truth.png")))))
print("days with a difference above 1 cent:", int((mrr["difference"].abs() > 0.01).sum()), "of", len(mrr))
usage = reporting.usage_vs_truth(sim)
print("days where usage events differ from delivered events:", int((usage["difference"] != 0).sum()), "of", len(usage))'''),
    code('''q("SELECT status, severity, COUNT(*) AS tests FROM meta_test_results GROUP BY 1, 2")'''),
    md("## Re-running a day\n\nEach source batch is keyed by run date, so a repeated run skips batches that already succeeded. Row counts and MRR stay the same."),
    code('''from saas_elt.pipeline import build_dag, load_contracts
before = q("SELECT 'events' AS t, COUNT(*) AS n FROM raw_product_events UNION ALL SELECT 'invoices', COUNT(*) FROM raw_billing_invoices")
dag = build_dag(sim.settings, sim.world, wh, load_contracts(), "2026-06-30")
rerun = dag.run(wh, "2026-09-30", {})
after = q("SELECT 'events' AS t, COUNT(*) AS n FROM raw_product_events UNION ALL SELECT 'invoices', COUNT(*) FROM raw_billing_invoices")
print("rerun status:", rerun.status)
before.merge(after, on="t", suffixes=("_before", "_after"))'''),
    md("""
## Privacy controls (GDPR and BDSG)

- Data minimisation: contracts list exactly which fields may land. Unknown fields fail the contract, except where a contract explicitly allows drift.
- Pseudonymisation: users only exist as salted SHA-256 hashes. The salt comes from an environment variable and never sits in the code.
- A PII guard rejects any record with an e-mail address, phone number or IBAN, and masks the value before quarantining it.
- Retention: quarantined records are purged after 90 days.
- Right to erasure (Art. 17): one command deletes a customer from every table and logs only a hash of the ID. Shown below on a copy of the warehouse.
"""),
    code('''from saas_elt.contracts import load_contract, validate
leaky = {"account_id": "ACC-00001", "company_name": "Nordwerk GmbH", "country": "DE", "industry": "Retail",
         "segment": "SMB", "created_at": "2026-01-01T09:00:00", "updated_at": "2026-01-02T09:00:00",
         "contact_email": "anna.schmidt@example.de"}
res = validate(leaky, load_contract("crm_accounts"))
print(res.ok, res.reasons)
print("stored in quarantine as:", res.safe_record["contact_email"])'''),
    code('''from saas_elt.warehouse import Warehouse
copy = Path("workdir/erasure_demo.db")
shutil.copy(sim.settings.warehouse_db, copy)
demo = Warehouse(copy)
print("rows deleted:", demo.erase_account("ACC-00042", "DSR-2026-001"))
print("left for ACC-00042 in fct_mrr_daily:", demo.query("SELECT COUNT(*) FROM fct_mrr_daily WHERE account_id='ACC-00042'")[0][0])
pd.read_sql_query("SELECT * FROM meta_erasure_log", demo.conn)'''),
]

NB3 = [
    md(f"""
# 03 · The dbt models and the revenue they produce

{badge("03_dbt_models_and_revenue.ipynb")}

Transformations live in `dbt_project/` as a standard dbt project: sources, staging views, intermediate tables, marts, schema tests and singular tests. Locally they run on a small built-in runner over SQLite. CI also runs the same project with real dbt on DuckDB, with date logic kept in cross-database macros.
"""),
    code(SETUP),
    code(RUN_SIM),
    code('''from saas_elt.minidbt import DbtProject
project = DbtProject(config.DBT_DIR, wh.conn, vars={"start_date": "2026-06-30", "run_date": "2026-09-30"})
pd.DataFrame([{"model": n.name, "kind": n.kind, "materialized": n.config.get("materialized", "seed"),
               "depends_on": ", ".join(sorted(n.refs) + [f"source:{s[1]}" for s in sorted(n.sources)])}
              for n in project.nodes.values()]).sort_values(["kind", "model"])'''),
    md("## Incremental models\n\n`fct_product_usage_daily` re-aggregates the last three days on every run, because events can arrive up to two days late. The same file compiles to two different queries:"),
    code('''node = project.nodes["fct_product_usage_daily"]
for label, inc in [("first build", False), ("incremental build", True)]:
    sql = project.render(node, incremental=inc)
    print(f"--- {label}: everything after FROM ---")
    print(sql.split("from stg_events__product_events")[1].strip(), "\\n")'''),
    md("## SCD type 2 from an append-only raw layer\n\nEvery subscription change lands as a new raw row. `int_subscription_versions` turns them into validity ranges, and `fct_mrr_daily` reads the version that was valid at the end of each day."),
    code('''q("SELECT subscription_id, plan, seats, mrr_eur, valid_from_date, valid_to_date FROM int_subscription_versions WHERE subscription_id IN (SELECT subscription_id FROM int_subscription_versions GROUP BY 1 HAVING COUNT(*) >= 3 LIMIT 2) ORDER BY 1, valid_from_date")'''),
    md("## Revenue bridge\n\nThe quarter closes at about EUR 250k MRR, or EUR 3.0M ARR. Net revenue retention is above 100% in July and August and dips to 99.5% in September, when churn picks up."),
    code('''display(Image(filename=str(reporting.plot_revenue_bridge(sim, Path("outputs/figures/revenue_bridge.png")))))
q("SELECT * FROM rpt_revenue_monthly")'''),
    code('''q("SELECT segment, COUNT(*) AS customers, ROUND(SUM(current_mrr_eur)) AS mrr_eur FROM dim_accounts WHERE customer_status = 'active' GROUP BY 1 ORDER BY 3 DESC")'''),
]


class _CapturedImage:
    def __init__(self, filename: str) -> None:
        self.data = Path(filename).read_bytes()


def _execute(cells: list[dict], workdir: Path) -> None:
    """Run code cells in a shared namespace and store their outputs."""
    shown: list = []
    # Stand-ins for IPython.display; the import line is skipped when executing here.
    ns: dict = {"__name__": "__main__", "Image": lambda filename: _CapturedImage(filename),
                "display": lambda obj: shown.append(obj)}
    old_cwd = os.getcwd()
    os.chdir(workdir)
    count = 0
    try:
        for cell in cells:
            if cell["cell_type"] != "code":
                continue
            count += 1
            shown.clear()
            src = cell["source"].replace("from IPython.display import Image, display", "pass")
            tree = ast.parse(src)
            last_expr = None
            if tree.body and isinstance(tree.body[-1], ast.Expr):
                last_expr = ast.Expression(tree.body.pop().value)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                exec(compile(tree, f"<cell {count}>", "exec"), ns)
                result = eval(compile(last_expr, f"<cell {count}>", "eval"), ns) if last_expr else None
            outputs = []
            printed = buf.getvalue()
            for obj in list(shown):
                outputs.append(_display_output(obj))
            if printed:
                # Keep print output ahead of images, like a real kernel would for this code.
                outputs.insert(0, {"name": "stdout", "output_type": "stream", "text": printed})
            if result is not None:
                out = _display_output(result)
                out["output_type"] = "execute_result"
                out["execution_count"] = count
                outputs.append(out)
            cell["outputs"] = outputs
            cell["execution_count"] = count
    finally:
        os.chdir(old_cwd)


def _display_output(obj) -> dict:
    if isinstance(obj, _CapturedImage):
        return {"output_type": "display_data", "metadata": {},
                "data": {"image/png": base64.b64encode(obj.data).decode(), "text/plain": "<IPython.core.display.Image object>"}}
    data = {"text/plain": repr(obj)}
    if hasattr(obj, "_repr_html_"):
        html = obj._repr_html_()
        if html:
            data["text/html"] = html
    return {"output_type": "display_data", "metadata": {}, "data": data}


def _write(cells: list[dict], path: Path) -> None:
    for c in cells:
        lines = c["source"].splitlines(keepends=True)
        c["source"] = lines
        for o in c.get("outputs", []):
            if "text" in o:
                o["text"] = o["text"].splitlines(keepends=True)
            for k in ("text/plain", "text/html"):
                if k in o.get("data", {}):
                    o["data"][k] = o["data"][k].splitlines(keepends=True)
    nb = {
        "cells": cells,
        "metadata": {
            "colab": {"provenance": []},
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "version": "3.11"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    for i, c in enumerate(cells):
        c["id"] = f"cell-{i:02d}"
    path.write_text(json.dumps(nb, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    NB_DIR.mkdir(exist_ok=True)
    books = {
        "01_daily_runs_and_incidents.ipynb": NB1,
        "02_reconciliation_and_privacy.ipynb": NB2,
        "03_dbt_models_and_revenue.ipynb": NB3,
    }
    for name, cells in books.items():
        _execute(cells, NB_DIR)
        _write(cells, NB_DIR / name)
        print(f"built and executed {name}: {sum(c['cell_type'] == 'code' for c in cells)} code cells")


if __name__ == "__main__":
    main()
