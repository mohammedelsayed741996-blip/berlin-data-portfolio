"""Build and execute the project notebooks without Jupyter.

Each code cell runs in one shared namespace, like a kernel, and its printed
output, last expression and images are saved as real notebook outputs. The
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
BASE = "https://colab.research.google.com/github/mohammedelsayed741996-blip/berlin-data-portfolio/blob/main/agritech-corporate-finance/month-end-close-forecast/notebooks"

SETUP = '''import os, sys, subprocess, warnings
from pathlib import Path

REPO = "https://github.com/mohammedelsayed741996-blip/berlin-data-portfolio.git"
PROJECT = "agritech-corporate-finance/month-end-close-forecast"

if "google.colab" in sys.modules:
    if not Path("/content/berlin-data-portfolio").exists():
        subprocess.run(["git", "clone", "--depth", "1", REPO, "/content/berlin-data-portfolio"], check=True)
    os.chdir(f"/content/berlin-data-portfolio/{PROJECT}")
else:
    here = Path.cwd()
    while not (here / "src" / "close_forecast").exists() and here != here.parent:
        here = here.parent
    os.chdir(here)

sys.path.insert(0, str(Path.cwd() / "src"))
warnings.filterwarnings("ignore")
import pandas as pd
pd.set_option("display.max_columns", 30)
pd.set_option("display.width", 160)
pd.set_option("display.max_colwidth", 110)
pd.set_option("display.float_format", lambda x: f"{x:,.2f}")
from IPython.display import Image, display
print("Project folder:", Path.cwd().name)'''

LOAD = '''from close_forecast import config as C, pipeline, close_checks, variance, forecast, reporting, db

tables = pipeline.load_tables()          # reads data/, or generates it if missing
run = pipeline.run(tables)
gl = tables["gl_items"]
print(f"{len(gl):,} ledger lines from {gl['month'].min()} to {gl['month'].max()}, closing {C.CLOSE_PERIOD}")'''


def md(text: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": text.strip("\n")}


def code(text: str) -> dict:
    return {"cell_type": "code", "metadata": {}, "source": text.strip("\n"), "execution_count": None, "outputs": []}


def badge(name: str) -> str:
    return f"[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)]({BASE}/{name})"


NB1 = [
    md(f"""
# 01 · Month-end close checks

{badge("01_month_end_close.ipynb")}

Feldkern Group is a made-up seed breeding company with three entities (Germany, France, Austria) and a fiscal year from July to June. This notebook closes September 2026, period 3 of FY 2026/27, from a ledger extract shaped like an SAP line item table: company code, document, account, cost center, WBS element, partner company, vendor and amount.

Twelve checks run on the extract. Before the close, eleven errors were planted in September on purpose: a document that does not balance, a blocked cost center, a duplicate invoice, a missing depreciation run, a missing rent posting, an intercompany charge the partner never booked, and so on. The checks have to find all of them, and the earlier months have to come out clean.
"""),
    code(SETUP),
    code(LOAD),
    md("## The checklist\n\nFAIL means the close cannot be signed off. WARN means someone has to look at it and decide."),
    code('''run.checklist[["check_id", "check", "owner", "status", "exceptions", "amount_eur"]]'''),
    md("A month that nobody tampered with passes every check. That matters as much as finding the errors: a check that fires every month gets ignored."),
    code('''close_checks.checklist(close_checks.run_close_checks(tables, "2025-12"))[["check_id", "status", "exceptions"]].T'''),
    md("## What the checks found\n\nThe document that does not balance came in through an upload from a feeder system. SAP would reject it at entry, but uploads and interfaces are where this happens in practice."),
    code('''checks = {c.check_id: c for c in run.checks}
for cid in ["C01", "C02", "C03", "C04", "C05"]:
    print(cid, checks[cid].name)
    display(checks[cid].exceptions)'''),
    md("""
## Missing recurring postings

The close keeps a register of what must be posted every month: payroll and the depreciation run for each company, rent for each cost center with a lease, and the intercompany charges. In September three of them are missing. The amount shown is last month's, as an estimate of what is missing.
"""),
    code('''checks["C07"].exceptions'''),
    md("The intercompany check finds the same gap from the other side. DE10 billed Austria for IT services, Austria did not book the invoice, and the receivable and payable now differ by exactly that amount."),
    code('''close_checks.intercompany_matrix(tables, C.CLOSE_PERIOD)'''),
    md("## Cut-off, GR/IR and suspense\n\nSix invoices were entered on 7 October, after the cut-off on working day 3. Four goods receipts from May and June still have no invoice, which usually means either an invoice is stuck somewhere or the receipt was booked twice."),
    code('''display(checks["C06"].exceptions)
display(close_checks.grir_open_items(tables, C.CLOSE_PERIOD).head(8))
display(checks["C10"].exceptions)'''),
    md("""
## Proposed corrections

The checks do not post anything. They propose entries, and an accountant approves them. Reclasses net to zero, so only the missing postings and the reversed duplicate change profit. The forecast in notebook 03 is built on actuals after these corrections, so known errors do not leak into the full-year outlook.
"""),
    code('''adj = run.adjustments
display(adj[["check_id", "company_code", "cost_center", "gl_account", "amount_eur", "description"]])
print(f"Net P&L effect: EUR {adj['amount_eur'].sum():,.2f}")'''),
    md("## The same checks in SQL\n\nThe `sql/` folder has the core checks as plain SQL, run here on SQLite. The tests make sure SQL and Python give the same answer."),
    code('''conn = db.connect(tables)
display(db.run_sql(conn, "03_intercompany_reconciliation.sql"))
display(db.run_sql(conn, "04_grir_aging.sql").groupby("bucket")["open_eur"].agg(["count", "sum"]))'''),
    code('''tb = close_checks.trial_balance(tables)
tb.groupby("company_code")["amount_eur"].sum().round(2)'''),
    md("The trial balance nets to zero in Austria and France. Germany is off by EUR 1,250, the unbalanced upload from check C01."),
]

NB2 = [
    md(f"""
# 02 · Budget vs actual and revenue bridge

{badge("02_budget_vs_actual.ipynb")}

Q1 of a seed company always shows a loss: costs run all year, while sugarbeet and corn seed sell in spring. So the question for September is not whether the result is negative but how far it is from plan, and why. This notebook compares actuals with budget and prior year by function, splits the revenue gap into volume and price, and explains every flagged cost line.
"""),
    code(SETUP),
    code(LOAD),
    md("## Income statement by function, July to September\n\nCost of sales method, group view, intercompany eliminated. Numbers are before the proposed corrections."),
    code('''run.income_statement'''),
    code('''display(Image(filename=str(reporting.plot_ebit_bridge(reporting.ebit_bridge(run.pvm, run.income_statement), Path("outputs/figures/ebit_bridge.png")))))'''),
    md("""
## Revenue: volume and price

Volume effect is the change in units at budget price. Price effect is the change in price at actual units. Together they equal the total variance. There is no mix effect across crops, because the crops are sold in different units (seed units, decitonnes, kilograms) and a blended price per unit would mean nothing.

A dry autumn cut cereal seed volume by about 16%. The price was 4% above plan, which recovers only part of it.
"""),
    code('''display(run.pvm[["crop", "units_vs_budget_pct", "price_vs_budget_pct", "volume_effect_eur", "price_effect_eur", "total_variance_eur"]])
display(Image(filename=str(reporting.plot_pvm(run.pvm, Path("outputs/figures/revenue_pvm.png")))))'''),
    md("## Costs by function"),
    code('''run.bva_fa[["functional_area", "actual_ytd", "budget_ytd", "var_ytd_eur", "var_ytd_pct", "prior_year_ytd", "vs_prior_year_pct"]]'''),
    md(f"""
At function level nothing crosses the threshold. That is the problem with function-level reporting: errors in both directions cancel out. One level down, at cost center and account, a line is flagged when the year-to-date gap is both above {{0}} and above EUR 25,000.
""".replace("{0}", "10%")),
    code('''variance.flagged_lines(tables)[["cost_center", "cost_center_name", "account_group", "actual_ytd", "budget_ytd", "var_ytd_eur", "var_ytd_pct"]]'''),
    md("""
## Finding a booking on the wrong cost center

Corn breeding is EUR 230k over budget on external services, and corn sales is EUR 217k under on the same account. That pattern is typical: someone booked an invoice on the wrong cost center. The function below looks for single postings that push their cost center far over its monthly budget while another cost center in the same company has the same amount unspent on the same account.
"""),
    code('''mis = variance.find_misallocations(tables)
display(mis.T)
variance.top_documents(tables, "3110", "6500").head(3)'''),
    md("## Variance comments\n\nEach flagged line gets a cause and an action, tied back to the close checks where they explain it. Two lines are left for the cost center owners, because the data alone does not explain them. A controller should say so instead of guessing."),
    code('''run.comments[["cost_center", "cost_center_name", "account", "var_ytd_eur", "explanation", "action"]]'''),
]

NB3 = [
    md(f"""
# 03 · Rolling forecast and capex

{badge("03_rolling_forecast_and_capex.ipynb")}

After the September close the forecast rolls forward: three months of actuals plus nine months of forecast (3+9). The method is not picked by habit. Four methods are tested on last year, FY 2025/26, by forecasting the rest of the year from three cut-offs (after periods 3, 6 and 9) and comparing with what actually happened. The method with the lowest error wins, separately for each function and for personnel versus other costs.
"""),
    code(SETUP),
    code(LOAD),
    md("""
## The four methods

- **Budget**: the remaining months are taken from the budget.
- **Run rate**: the average of the last three months, carried flat.
- **Prior year seasonal**: last year's actuals for the same months, scaled by this year's ratio to last year.
- **Driver based**: personnel is planned FTE times the actual hiring gap times actual cost per FTE, with the 13th salary in November. Other costs are the remaining budget scaled by the year-to-date ratio to budget. Rent and depreciation stay at last month's level.
"""),
    code('''display(run.backtest.groupby(["functional_area", "cost_type", "method"])["wape"].mean().unstack().round(4))
display(Image(filename=str(reporting.plot_backtest(run.backtest, Path("outputs/figures/forecast_backtest.png")))))'''),
    md("Run rate is the worst everywhere, because it ignores the harvest peak and the November salary. The driver method wins six of the eight cells. The chosen method is never worse than the plain budget, and for selling and production costs it cuts the error by a third or more."),
    code('''run.choice'''),
    md("## The 3+9 forecast\n\nBuilt on September actuals after the proposed corrections from notebook 01."),
    code('''display(Image(filename=str(reporting.plot_cost_forecast(tables, run.cost_forecast, Path("outputs/figures/cost_forecast.png")))))'''),
    md("""
## Full-year outlook

Revenue: crops whose season is at least 15% complete carry their year-to-date volume ratio forward; the rest stay at budget volume. Price ratios carry forward for every crop that has sold. For cereals that means the autumn shortfall stays in the outlook. Corn has hardly started, so its volume stays at plan.
"""),
    code('''run.landing'''),
    code('''land = run.landing.set_index("line")
print(f"EBIT outlook EUR {land.loc['EBIT', 'outlook_fy']/1e6:,.1f}m vs budget EUR {land.loc['EBIT', 'budget_fy']/1e6:,.1f}m "
      f"({land.loc['EBIT', 'var_vs_budget_pct']:+.1%}); margin {land.loc['EBIT', 'outlook_fy']/land.loc['Revenue', 'outlook_fy']:.1%} "
      f"vs {land.loc['EBIT', 'budget_fy']/land.loc['Revenue', 'budget_fy']:.1%} planned")'''),
    md("""
## Capital projects

For each project, the estimate at completion (EAC) is spend to date plus the larger of the remaining plan and the orders already placed. The greenhouse in France has spent and ordered 116% of its approved budget, and its EAC is 23% over. That needs a budget supplement request before any further orders.
"""),
    code('''display(run.capex[["wbs", "description", "approved_budget_eur", "actual_to_date_eur", "open_commitments_eur", "eac_eur", "eac_vs_budget_pct", "outlook_fy_eur"]])
display(Image(filename=str(reporting.plot_capex(run.capex, Path("outputs/figures/capex_eac.png")))))'''),
    md("## Outputs for finance\n\nThe pipeline writes an Excel controlling pack with live formulas, a close memo in Markdown, and a star schema with DAX measures for Power BI."),
    code('''out = pipeline.write_outputs(run)
from openpyxl import load_workbook
wb = load_workbook(out["excel"])
print("Excel sheets:", wb.sheetnames)
print("Formula examples:", wb["BvA by function"]["G2"].value, "|", wb["Outlook"]["D2"].value, "|", wb["Revenue PVM"]["H2"].value)
print("Power BI files:", [p.name for p in out["powerbi"]])'''),
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
        "01_month_end_close.ipynb": NB1,
        "02_budget_vs_actual.ipynb": NB2,
        "03_rolling_forecast_and_capex.ipynb": NB3,
    }
    for name, cells in books.items():
        _execute(cells, NB_DIR)
        _write(cells, NB_DIR / name)
        print(f"built and executed {name}: {sum(c['cell_type'] == 'code' for c in cells)} code cells")


if __name__ == "__main__":
    main()
