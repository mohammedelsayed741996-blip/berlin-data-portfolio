"""Build and execute the project notebooks without Jupyter.

Each code cell runs in one shared namespace, like a kernel, and its printed
output, last expression and images are saved as real notebook outputs, so the
files open with results in Jupyter, on GitHub and in Google Colab.

Run from the project folder:  python scripts/build_notebooks.py
"""

from __future__ import annotations

import ast
import base64
import contextlib
import io
import json
import os
from pathlib import Path

os.environ.setdefault("MPLBACKEND", "Agg")
PROJECT = Path(__file__).resolve().parents[1]
NB_DIR = PROJECT / "notebooks"
BASE = "https://colab.research.google.com/github/mohammedelsayed741996-blip/berlin-data-portfolio/blob/main/fintech-brokerage/aml-monitoring-oversight/notebooks"

SETUP = '''import os, sys, subprocess, warnings
from pathlib import Path

REPO = "https://github.com/mohammedelsayed741996-blip/berlin-data-portfolio.git"
PROJECT = "fintech-brokerage/aml-monitoring-oversight"

if "google.colab" in sys.modules:
    if not Path("/content/berlin-data-portfolio").exists():
        subprocess.run(["git", "clone", "--depth", "1", REPO, "/content/berlin-data-portfolio"], check=True)
    os.chdir(f"/content/berlin-data-portfolio/{PROJECT}")
else:
    here = Path.cwd()
    while not (here / "src" / "aml_oversight").exists() and here != here.parent:
        here = here.parent
    os.chdir(here)

sys.path.insert(0, str(Path.cwd() / "src"))
warnings.filterwarnings("ignore")
import pandas as pd
pd.set_option("display.max_columns", 30)
pd.set_option("display.width", 160)
pd.set_option("display.max_colwidth", 120)
from IPython.display import Image, display
print("Project folder:", Path.cwd().name)'''

LOAD = '''from aml_oversight import config as C, pipeline, oversight as O, reporting, db

tables = pipeline.load_tables()      # reads data/, or generates it if missing
run = pipeline.run(tables)
print(f"{len(tables['clients']):,} clients, {len(tables['transactions']):,} transactions, "
      f"{len(tables['alerts']):,} alerts, {len(tables['screening_hits']):,} screening hits")'''


def md(text: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": text.strip("\n")}


def code(text: str) -> dict:
    return {"cell_type": "code", "metadata": {}, "source": text.strip("\n"), "execution_count": None, "outputs": []}


def badge(name: str) -> str:
    return f"[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)]({BASE}/{name})"


NB1 = [
    md(f"""
# 01 · The broker and its monitoring programme

{badge("01_programme_and_data.ipynb")}

A fictional mobile broker in Germany with 15,000 clients, a year of deposits, trades and withdrawals (October 2025 to September 2026), six transaction monitoring rules, name screening against a sanctions and PEP list, and a team of eight first-line analysts.

The oversight team (the second line) does not run the monitoring. It checks that the monitoring works and reports to the MLRO, senior management and the board. This notebook shows what there is to check. Notebooks 02 and 03 do the checking.

Everything is synthetic. Names are random syllables, accounts are random hashes, analysts are codes, and HR1 to HR4 stand in for high-risk jurisdictions.
"""),
    code(SETUP),
    code(LOAD),
    md("## Clients and activity"),
    code('''cl = tables["clients"]
display(cl[["client_id", "residence", "occupation", "expected_monthly_deposit_eur", "risk_rating", "pep"]].head())
display(cl["risk_rating"].value_counts().to_frame().T)
tx = tables["transactions"]
display(tx.groupby("type")["amount_eur"].agg(["count", "sum"]).round(0))'''),
    md("""
## Planted behaviour

Six typologies sit inside the normal activity: structuring just under EUR 10,000, pass-through (money in and straight out), funding from many third parties, mule rings, money from high-risk jurisdictions, and activity far above the client's declared income. Some legitimate clients look unusual too: an inheritance, a monthly saving of EUR 9,000, a parent paying in.

The mule rings are built to slip past transaction rules: small card deposits from the client's own card, a quick buy and sell so the money looks invested, then a payout to an account shared by the whole ring.
"""),
    code('''display(tables["typology_truth"]["typology"].value_counts().to_frame().T)
mule = tables["typology_truth"].query("typology == 'T4 mule ring'")["client_id"].iloc[0]
tx[tx["client_id"] == mule].head(8)'''),
    md("## The rules and their alerts"),
    code('''a = tables["alerts"]
display(pd.DataFrame({"rule": list(C.RULES), "description": list(C.RULES.values())}))
display(a.groupby("rule").size().rename("alerts").to_frame().T)
a[["alert_id", "client_id", "rule", "alert_date", "analyst", "l1_decision", "l1_rationale", "l2_decision"]].head(8)'''),
    md("""
## What the case system records

Each alert has a level 1 decision (closed with no concern, or escalated), a date and a written rationale. Escalated alerts get a level 2 decision and, where suspicion is confirmed, a SAR to the FIU. These are the fields the oversight KPIs are built from. The ground-truth column `true_suspicious` exists only because the data is synthetic; the oversight code uses it solely for sampled QA re-reviews.
"""),
    code('''display(a["l1_decision"].value_counts().to_frame().T)
display(a["l2_decision"].replace("", "not escalated").value_counts().to_frame().T)'''),
    md("## Screening"),
    code('''h = tables["screening_hits"]
display(h.groupby(["list", "decision"]).size().unstack(fill_value=0))
h.sort_values("match_score", ascending=False)[["client_id", "entry_id", "list", "match_score", "birth_year_match", "decision"]].head(6)'''),
]

NB2 = [
    md(f"""
# 02 · Oversight checks

{badge("02_oversight_checks.ipynb")}

The checks an AML oversight team runs, one per question: did the monitoring get all the data, do the rules still work as approved, do they cover the risks, are the decisions right, are cases handled in time, are clients screened, are reviews up to date. Each result here ends up as a KRI or a finding in notebook 03.
"""),
    code(SETUP),
    code(LOAD),
    md("## 1. Did monitoring receive every transaction?\n\nReconcile the core ledger with the monitoring feed by month and source. This is the first check because every other one assumes it passes."),
    code('''display(run.completeness[run.completeness["missing_count"] > 0])
display(Image(filename=str(reporting.plot_feed_gap(tables["transactions"], tables["tm_feed_ids"], Path("outputs/figures/feed_gap.png")))))'''),
    md("For almost four weeks, card deposits through one payment provider never reached the rules. Nobody in the first line noticed, because a missing transaction does not raise an alert."),
    md("## 2. Do the rules still work as approved?\n\nAlert volumes per rule should only move for a reason. R02 dropped sharply in April."),
    code('''display(Image(filename=str(reporting.plot_rule_volume(tables["alerts"], "R02", Path("outputs/figures/r02_volume.png")))))
run.volume_change'''),
    md("The vendor raised the R02 deposit count from 3 to 5 without a change request. A below-the-line test re-runs the rule on the period since April at lower counts:"),
    code('''run.below_the_line'''),
    md("At the approved setting of 3, the rule would have alerted on twice as many structuring clients since April. It would also bring more false positives, which may be why someone changed it, but that trade-off has to be decided and documented, not made quietly in a vendor console."),
    md("## 3. Do the rules cover the risks?"),
    code('''display(run.rules)
display(Image(filename=str(reporting.plot_coverage(run.coverage, Path("outputs/figures/typology_coverage.png")))))'''),
    md("Five typologies are covered, most by two rules. Mule rings are not: their money looks like the client's own and gets traded before it leaves. What gives them away is shared infrastructure, so the next check looks for clients linked by a payout account or a device."),
    code('''display(run.networks.drop(columns="client_ids"))
display(Image(filename=str(reporting.plot_networks(tables["clients"], run.networks, Path("outputs/figures/mule_networks.png")))))
display(db.run_sql(db.connect(tables), "04_shared_payout_accounts.sql").head())'''),
    md("""
## 4. Are the decisions right?

Each quarter, a random sample of alerts closed with no concern is re-reviewed. With 59 cases and no errors, you can say with 95% confidence that the error rate is below 5%. The sample is spread across analysts so that each one gets looked at. Error rates come with Clopper-Pearson intervals, because 30 cases per analyst is not much.
"""),
    code('''print("Sample size per quarter:", O.zero_failure_sample_size())
display(run.qa_by_analyst.query("error_type == 'decision_error'"))
display(Image(filename=str(reporting.plot_qa(run.qa_by_analyst, Path("outputs/figures/qa_by_analyst.png")))))'''),
    md("Analyst A06 is the only one whose whole interval sits above the tolerable 5%. That justifies a full lookback of the analyst's closures:"),
    code('''print(len(run.lookback), "cases A06 closed that should have been escalated")
run.lookback.head()'''),
    md("## 5. Timeliness, documentation, screening, reviews"),
    code('''display(run.kpis[["month", "alerts_created", "backlog_month_end", "backlog_over_sla", "closed_over_sla_pct", "missing_rationale_pct", "sars_filed", "median_days_alert_to_sar"]])
print(run.screening)
display(run.screening_qa[["client_id", "entry_id", "match_score", "birth_year_match", "decision", "reviewer_finding"]])
display(run.reviews)'''),
    md("One sanctions hit with a matching year of birth and a name score of 0.93 was closed as a false positive. The reviewer judges it to be the same person with a spelling variant. That is the most serious finding of the year."),
]

NB3 = [
    md(f"""
# 03 · MI, findings and the report

{badge("03_mi_and_reporting.ipynb")}

Oversight work only matters if it reaches the people who can act on it. This notebook turns the checks into monthly KRIs against risk appetite, a findings register with owners and dates, an Excel MI pack and a short report for senior management, with a German summary.
"""),
    code(SETUP),
    code(LOAD),
    md("## KRIs against risk appetite\n\nEach KRI has an amber and a red limit. The heat map shows the year at a glance; the summer backlog and the June feed gap stand out."),
    code('''display(Image(filename=str(reporting.plot_kri_heatmap(run.kri, Path("outputs/figures/kri_heatmap.png")))))
run.kri[run.kri["month"] == C.MONTHS[-1]][["kri", "value", "amber_limit", "red_limit", "status"]]'''),
    md("## Findings register"),
    code('''run.findings[["finding_id", "severity", "area", "observation", "owner", "due"]]'''),
    md("## Excel MI pack and report\n\nThe Excel file keeps inputs (blue) apart from formulas: rates, RAG status and totals recalculate if a number is corrected. The report is one page for the Risk & Compliance Committee."),
    code('''out = pipeline.write_outputs(run)
from openpyxl import load_workbook
wb = load_workbook(out["excel"])
print("Sheets:", wb.sheetnames)
print("Example formulas:", wb["Rules"]["G2"].value, "|", wb["QA"]["D2"].value, "|", wb["KRI dashboard"]["P2"].value[:60], "...")
print(Path("outputs/oversight_report.md").read_text()[:2500])'''),
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
        "01_programme_and_data.ipynb": NB1,
        "02_oversight_checks.ipynb": NB2,
        "03_mi_and_reporting.ipynb": NB3,
    }
    for name, cells in books.items():
        _execute(cells, NB_DIR)
        _write(cells, NB_DIR / name)
        print(f"built and executed {name}: {sum(c['cell_type'] == 'code' for c in cells)} code cells")


if __name__ == "__main__":
    main()
