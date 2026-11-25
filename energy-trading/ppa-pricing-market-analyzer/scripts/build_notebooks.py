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
BASE = "https://colab.research.google.com/github/mohammedelsayed741996-blip/berlin-data-portfolio/blob/main/energy-trading/ppa-pricing-market-analyzer/notebooks"

SETUP = """import os, sys, subprocess, warnings
from pathlib import Path

REPO = "https://github.com/mohammedelsayed741996-blip/berlin-data-portfolio.git"
PROJECT = "energy-trading/ppa-pricing-market-analyzer"

if "google.colab" in sys.modules:
    if not Path("/content/berlin-data-portfolio").exists():
        subprocess.run(["git", "clone", "--depth", "1", REPO, "/content/berlin-data-portfolio"], check=True)
    os.chdir(f"/content/berlin-data-portfolio/{PROJECT}")
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "xlsxwriter"], check=True)
else:
    here = Path.cwd()
    while not (here / "src" / "ppalab").exists() and here != here.parent:
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


LOAD = """from ppalab import market as M, trends as T, pricing as P, bess as B, crm as C
d = M.load()
h = T.enrich(d["hourly"])
print(len(h), "hours from", h.timestamp.min().date(), "to", h.timestamp.max().date())"""

NB1 = [
    md(f"""# 1. Power market trends and volatility

{badge("01_market_trends_and_volatility.ipynb")}

Hourly day-ahead prices for a German-style market from 2019 to October 2026. The data is simulated with a simple merit-order model (gas, carbon, demand, growing solar and wind), so the patterns are realistic but the numbers are not exchange data."""),
    code(SETUP),
    code(LOAD),
    code("""T.yearly(h)[["year", "base", "peak", "peak_base_spread", "daily_vol", "intraday_spread", "negative_hours", "solar_capture_rate", "wind_capture_rate"]].round(2)"""),
    md("Three things stand out: the 2022 crisis, the peak-base spread collapsing as solar covers the working-day peak hours, and solar earning less and less of the base price. Negative hours climb from a handful to several hundred a year."),
    code("""display(Image("outputs/figures/market_trends.png"))"""),
    code("""display(Image("outputs/figures/price_heatmap.png"))"""),
    md("## Forward market volatility\n\nThe Cal-27 baseload contract's annualised volatility over rolling 60-day windows. This number drives the price-level uncertainty in the PPA Monte Carlo."),
    code("""v = T.forward_volatility(d["cal27"])
print(d["curve"])
v.annualised_vol.describe().round(3)"""),
]

NB2 = [
    md(f"""# 2. PPA pricing and structure comparison

{badge("02_ppa_pricing_and_structures.ipynb")}

How an originator prices a pay-as-produced PPA for a 10 MW solar or wind plant, delivery 2027 to 2029, and how the producer's revenue compares across structures."""),
    code(SETUP),
    code(LOAD),
    md("## Hourly price forward curve\n\nShape factors from the last 24 months, scaled so the curve averages exactly to the traded Cal-27 base and peak."),
    code("""c27 = d["curve"].query("year == 2027").iloc[0]
hp = P.hpfc(d["hourly"], 2027, c27.base_eur_mwh, c27.peak_eur_mwh)
print("base", round(hp.price.mean(), 2), "peak", round(hp[hp.is_peak].price.mean(), 2))
hp.pivot_table(index=hp.timestamp.dt.month, columns=hp.timestamp.dt.hour, values="price").iloc[[0, 5], ::3].round(1)"""),
    md("## Fundamental Monte Carlo\n\nEach scenario simulates the delivery years with that year's installed capacity and new weather, then rescales the price level to the forward times a shock whose spread grows with time to delivery. 40 scenarios here to keep the notebook quick; the pipeline uses 100."),
    code("""scen = P.scenarios([2027, 2028, 2029], 40, d["curve"], float(T.forward_volatility(d["cal27"]).annualised_vol.iloc[-1]))
stats = {t: P.asset_stats(scen, t, 10.0) for t in ("solar", "wind")}
stats["solar"].describe().loc[["mean", "std", "min", "max"]].round(2)"""),
    code("""offers = {t: P.offer(stats[t], t, 3, "BBB") for t in stats}
pd.DataFrame(offers).round(2)"""),
    code("""display(Image("outputs/figures/offer_waterfall.png"))"""),
    md("## Who carries which risk\n\nThe same scenarios, seen from the producer. Pay-as-produced removes all uncertainty for a lower expected price; a baseload PPA keeps the shape and volume risk with the producer; merchant keeps everything."),
    code("""base_price = d["curve"].query("year in [2027, 2028, 2029]").base_eur_mwh.mean() - 1.5
for t in ("solar", "wind"):
    print(t)
    print(P.summarise_structures(P.structures(scen, t, 10.0, offers[t]["offer_price"], base_price)), "\\n")"""),
    code("""display(Image("outputs/figures/structures.png"))"""),
    md("The offer calculator in `outputs/ppa_offer_calculator.xlsx` reproduces the walk with live Excel formulas, so an originator can change capacity, tenor, rating or margin in front of a client."),
]

NB3 = [
    md(f"""# 3. Batteries, the origination pipeline and the weekly report

{badge("03_bess_pipeline_and_automation.ipynb")}

Battery arbitrage value by year, the value of adding storage to a solar park, a Salesforce-style pipeline report and the automated weekly market report."""),
    code(SETUP),
    code(LOAD),
    code("""daily = B.run(d["hourly"])
B.yearly(daily).round(0)"""),
    code("""display(Image("outputs/figures/bess_value.png"))"""),
    code("""B.solar_plus_storage(d["hourly"]).round(2)"""),
    md("## Pipeline report\n\nThe checks run before any number is reported, because a forecast built on stale opportunities is wrong before it starts."),
    code("""opp = C.load()
C.checks(opp)"""),
    code("""(C.pipeline(opp) / 1e3).round(0)"""),
    code("""C.forecast(opp).round(2)"""),
    code("""display(Image("outputs/figures/pipeline.png"))"""),
    md("## Weekly market report\n\n`python -m ppalab.run` refreshes everything and writes this report in German:"),
    code("""print(Path("outputs/weekly_market_report_de.md").read_text())"""),
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
        "01_market_trends_and_volatility.ipynb": NB1,
        "02_ppa_pricing_and_structures.ipynb": NB2,
        "03_bess_pipeline_and_automation.ipynb": NB3,
    }
    for name, cells in books.items():
        _execute(cells, NB_DIR)
        _write(cells, NB_DIR / name)
        print(f"built and executed {name}: {sum(c['cell_type'] == 'code' for c in cells)} code cells")


if __name__ == "__main__":
    main()
