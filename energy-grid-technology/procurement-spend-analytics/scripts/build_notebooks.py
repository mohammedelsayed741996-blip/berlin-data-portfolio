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
BASE = "https://colab.research.google.com/github/mohammedelsayed741996-blip/berlin-data-portfolio/blob/main/energy-grid-technology/procurement-spend-analytics/notebooks"

SETUP = """import os, sys, subprocess, warnings
from pathlib import Path

REPO = "https://github.com/mohammedelsayed741996-blip/berlin-data-portfolio.git"
PROJECT = "energy-grid-technology/procurement-spend-analytics"

if "google.colab" in sys.modules:
    if not Path("/content/berlin-data-portfolio").exists():
        subprocess.run(["git", "clone", "--depth", "1", REPO, "/content/berlin-data-portfolio"], check=True)
    os.chdir(f"/content/berlin-data-portfolio/{PROJECT}")
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "xlsxwriter", "python-pptx"], check=True)
else:
    here = Path.cwd()
    while not (here / "src" / "spendcube").exists() and here != here.parent:
        here = here.parent
    os.chdir(here)

sys.path.insert(0, str(Path.cwd() / "src"))
warnings.filterwarnings("ignore")
import pandas as pd
pd.set_option("display.max_columns", 20)
pd.set_option("display.width", 160)
pd.set_option("display.max_colwidth", 80)
from IPython.display import Image, display
print("Project folder:", Path.cwd().name)"""


def md(text: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": text.strip("\n")}


def code(text: str) -> dict:
    return {"cell_type": "code", "metadata": {}, "source": text.strip("\n"), "execution_count": None, "outputs": []}


def badge(name: str) -> str:
    return f"[![Open in Colab](https://colab.research.google.com/assets/colab-badge.svg)]({BASE}/{name})"


LOAD = """import json
from spendcube import sources as S, suppliers as SU, quality as Q, cube as C, analytics as A, forecast as F, profiling
from spendcube.pipeline import load_indices
raw = S.read_raw()
key = json.loads(Path("data/raw/_answer_key.json").read_text())
recs, merges, review = SU.match(SU.stack_masters(raw))
harmonised = S.harmonise(raw)
lines, clean_log = C.clean(harmonised, recs, raw)
tables = C.build(lines, SU.golden_records(recs))
con = C.to_sqlite(tables)
print({k: len(v) for k, v in raw.items()})"""

NB1 = [
    md(f"""# 1. Data sources and data quality

{badge("01_data_sources_and_quality.ipynb")}

Havelwerk Grid Components is a fictional maker of power transformers with plants in Berlin, Erfurt and Gdansk. Its purchasing data comes from two ERP systems with different formats, a contracts spreadsheet and market price indices. Everything here is synthetic, and the generator plants known data problems so the checks can be scored.

This notebook profiles each source, runs the 12 data quality rules and merges duplicate suppliers into golden records."""),
    code(SETUP),
    code(LOAD),
    md("## What each source looks like"),
    code("""p = profiling.profile(raw)
p[p.source.isin(["erp_a_ekpo", "erp_b_orders"])][["source", "column", "filled", "distinct", "format", "example"]]"""),
    md("ERP_A writes German number formats and dates, and quotes cheap items per 100 units; ERP_B writes ISO dates and prices in PLN, and leaves the category empty on many lines. Harmonising turns both into EUR per unit:"),
    code("""harmonised[["source", "order_no", "order_date", "supplier_ref", "description", "category", "quantity", "uom", "unit_price_eur"]].sample(6, random_state=1)"""),
    md("## Data quality rules"),
    code("""dq = Q.run(raw, harmonised, recs, review)
dq[["id", "dataset", "dimension", "rule", "severity", "owner", "checked", "failing"]]"""),
    code("""Q.score_against_key(dq, key, SU.evaluate(recs, key))"""),
    code("""Q.scorecard(dq)"""),
    md("## Supplier matching\n\nSame VAT ID merges automatically. Otherwise the normalised names must match, and a pair that conflicts on VAT ID, legal form or country is left for a person to review."),
    code("""print(SU.evaluate(recs, key))
merges.groupby("rule").size()"""),
    code("""review[["name_a", "name_b", "score", "not_merged_because"]].head(8)"""),
    code("""display(Image("outputs/figures/dq_findings.png"))"""),
]

NB2 = [
    md(f"""# 2. Spend cube and supplier analytics

{badge("02_spend_cube_and_suppliers.ipynb")}

The cleaned lines become a star schema (fact_po_line plus supplier, material, category, plant and month dimensions). The analysis below runs as SQL views on SQLite; the same tables load into Power BI (see `powerbi/`)."""),
    code(SETUP),
    code(LOAD),
    code("""print(clean_log)
h = A.headline(con)
{k: round(v, 3) if isinstance(v, float) else v for k, v in h.items()}"""),
    code("""A.q(con, "SELECT * FROM v_spend_by_category ORDER BY spend_eur DESC")"""),
    code("""display(Image("outputs/figures/spend_by_category.png"))"""),
    md("Almost a third of spend runs outside an active agreement. Part of it is with suppliers whose agreement expired at the end of 2025, which is the quickest thing to fix."),
    code("""A.q(con, "SELECT * FROM v_category_concentration ORDER BY hhi DESC")"""),
    code("""display(Image("outputs/figures/supplier_pareto.png"))"""),
    md("## Supplier scorecard and Kraljic matrix"),
    code("""sc = A.supplier_scorecard(con)
sc.head(10)[["supplier_name", "country", "spend_eur", "on_time_rate", "defect_rate", "score", "grade"]]"""),
    code("""vol = F.volatility(load_indices(raw))
A.kraljic(con, vol)[["category_name", "share_pct", "suppliers", "hhi", "supply_risk", "quadrant"]]"""),
    code("""display(Image("outputs/figures/kraljic.png"))"""),
]

NB3 = [
    md(f"""# 3. Commodity prices and the budget

{badge("03_commodity_prices_and_budget.ipynb")}

Two questions: where are copper, electrical steel, hot-rolled steel, aluminium and transformer oil heading, and how much of a move reaches Havelwerk's purchase prices?"""),
    code(SETUP),
    code(LOAD),
    code("""ind = load_indices(raw)
bt = F.backtest(ind)
s = F.summarise(bt)
s.filter(like="_mape")"""),
    md("Mean absolute percentage error over all horizons, refitting every month from October 2023. Skill is the improvement over the naive forecast:"),
    code("""s.filter(like="_skill").join(s.chosen)"""),
    md("No model beats the naive forecast by more than 5% for any index, so the outlook keeps the last value and the useful part is the band. The backtest checks that the 80% band holds about 80% of outcomes:"),
    code("""print("coverage:", round(F.coverage(bt, ind, s.chosen.to_dict()), 3))
bt.groupby(["model", "h"]).ape.mean().unstack().round(3)"""),
    code("""display(Image("outputs/figures/commodity_forecast.png"))"""),
    md("## Pass-through to purchase prices\n\nRegressing each category's relative price on the relative index at lags 0 to 3 recovers how the supply contracts work: the share of the price that follows the index and the delay."),
    code("""pt = F.pass_through(tables["fact_po_line"], ind)
pt"""),
    code("""fc = F.forecast(ind, s.chosen.to_dict())
F.budget_impact(tables["fact_po_line"], ind, fc, pt).round(0)"""),
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
        "01_data_sources_and_quality.ipynb": NB1,
        "02_spend_cube_and_suppliers.ipynb": NB2,
        "03_commodity_prices_and_budget.ipynb": NB3,
    }
    for name, cells in books.items():
        _execute(cells, NB_DIR)
        _write(cells, NB_DIR / name)
        print(f"built and executed {name}: {sum(c['cell_type'] == 'code' for c in cells)} code cells")


if __name__ == "__main__":
    main()
