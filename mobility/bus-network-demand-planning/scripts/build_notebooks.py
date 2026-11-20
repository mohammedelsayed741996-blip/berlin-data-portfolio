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
BASE = "https://colab.research.google.com/github/mohammedelsayed741996-blip/berlin-data-portfolio/blob/main/mobility/bus-network-demand-planning/notebooks"

SETUP = '''import os, sys, subprocess, warnings
from pathlib import Path

REPO = "https://github.com/mohammedelsayed741996-blip/berlin-data-portfolio.git"
PROJECT = "mobility/bus-network-demand-planning"

if "google.colab" in sys.modules:
    if not Path("/content/berlin-data-portfolio").exists():
        subprocess.run(["git", "clone", "--depth", "1", REPO, "/content/berlin-data-portfolio"], check=True)
    os.chdir(f"/content/berlin-data-portfolio/{PROJECT}")
else:
    here = Path.cwd()
    while not (here / "src" / "bus_network").exists() and here != here.parent:
        here = here.parent
    os.chdir(here)

sys.path.insert(0, str(Path.cwd() / "src"))
warnings.filterwarnings("ignore")
import pandas as pd
pd.set_option("display.max_columns", 30)
pd.set_option("display.width", 160)
pd.set_option("display.max_colwidth", 80)
from IPython.display import Image, display
print("Project folder:", Path.cwd().name)'''

LOAD = '''from bus_network import config as C, data, validation as V, analysis as A, planning as P, reporting as R, db

if not any(Path("data").glob("*.csv*")):
    data.save(data.generate(), Path("data"))
tables = data.load(Path("data"))
LAST_12M = ("2025-10-01", "2026-09-30")
print({name: len(df) for name, df in tables.items()})'''


def md(text: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": text.strip("\n")}


def code(text: str) -> dict:
    return {"cell_type": "code", "metadata": {}, "source": text.strip("\n"), "execution_count": None, "outputs": []}


def badge(name: str) -> str:
    return f"[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)]({BASE}/{name})"


NB1 = [
    md(f"""
# 01 · Data validation across four systems

{badge("01_data_validation.ipynb")}

A fictional intercity bus operator plans 22 lines between 32 cities in Germany and its neighbours.
Planning draws on four systems that are maintained by different people: the planning tool
(stops, lines, timetable), the partner CRM (bus partners and contracts), the operations log
(what actually ran, with which bus) and ticketing (bookings per trip).

All data is synthetic. City coordinates are public geography; partners are invented and marked
"(fictional)". Six problems were planted on purpose, and the checks below have to find all of them
before any KPI is trusted.
"""),
    code(SETUP),
    code(LOAD),
    md("""
## The tables

Every trip has an id such as `L010A-20260301-0800`: line, direction, date and departure time.
That id is the only key shared by ticketing and the operations log.
"""),
    code('''display(tables["timetable"].head(6))
display(tables["partners"])'''),
    code('''display(tables["operations"].head(3))
display(tables["bookings"].head(3))'''),
    md("""
## Eight checks, run before anything else

Each check returns the rows that fail it, plus an owner and an action, so the result can go straight
into an issue log rather than an email thread.
"""),
    code('''checks = V.run_all(tables)
issues = V.issue_log(checks)
issues[["check_id", "check", "status", "issues", "owner"]]'''),
    md("""
## What each failure means

The coordinates of one stop have latitude and longitude swapped, which puts Regensburg in the
Gulf of Aden on any map. Munich exists twice under two names 0.3 km apart, so its passengers are
split across two stop records. 140 trips sold tickets but are missing from the operations log, and
partner payments are based on that log.
"""),
    code('''for c in checks[:4]:
    print(c.check_id, c.name)
    display(c.rows.head(3))'''),
    md("""
The most expensive finding: since April 2026 the partner on line L017 has run single-deckers
(49 seats) while ticketing still sells a double-decker (79 seats). Most of those trips sold more
seats than the bus had. The SQL version of the check gives the same answer from the raw tables.
"""),
    code('''con = db.connect(tables)
display(db.run(con, Path("sql/02_capacity_mismatch.sql")))
display(db.run(con, Path("sql/03_expired_contracts.sql")))'''),
    md("""
## The clean trip table

Cancelled trips and bookings for departures that are not in the timetable are removed. Trips that
are missing from the log are kept, because the passengers did travel. Every later notebook works on
this table.
"""),
    code('''trips = V.clean_trips(tables)
print(f"{len(trips):,} trips from {trips['date'].min()} to {trips['date'].max()}")
trips.head(3)'''),
]

NB2 = [
    md(f"""
# 02 · Network and line performance

{badge("02_network_and_line_performance.ipynb")}

Which lines carry people efficiently, which run with too many seats and which turn customers away?
The main KPI is load factor: passenger-km divided by seat-km over the whole line. Average peak
load would hide a line that is full for 40 km and empty for the next 200.
"""),
    code(SETUP),
    code(LOAD + '''
trips = V.clean_trips(tables)'''),
    code('''k = A.line_kpis(trips, LAST_12M)
k["route"] = k["line"].map(A.route_label)
k[["line", "route", "pax", "load_factor", "peak_load_factor", "sold_out_share", "contribution_margin"]].sort_values("load_factor")'''),
    md("""
Two kinds of problem show up. L023 and L031 are short of passengers on every segment and lose money
after bus costs. L040 Cologne to Amsterdam is different: its busiest segment is 72% full on average,
but over the whole route the load factor is 24%. Most passengers ride the short Cologne to
Duesseldorf stretch and the buses run nearly empty to Amsterdam. At the other end, L016 Berlin to
Warsaw sells out on about half its departures.
"""),
    code('''R.plot_line_matrix(k, Path("outputs/figures/line_matrix.png"))
display(Image("outputs/figures/line_matrix.png"))'''),
    md("""
## The network as a graph

Cities are nodes and segments are edges, weighted by average passengers on board. Betweenness
centrality shows which cities hold the network together: a disruption there affects the most
journeys.
"""),
    code('''G = A.network_graph(trips, LAST_12M)
A.hub_table(G).head(8)'''),
    md("""
## Where demand has no direct line

A gravity model (passengers rise with both cities' populations and fall with distance) is fitted on
the city pairs that already have a direct connection. It is then applied to pairs that do not, to
rank candidates for new lines.
"""),
    code('''grav = A.fit_gravity(tables["od_monthly"], LAST_12M)
print("R² on served pairs:", round(grav["r2"], 3), "| population elasticity:", round(grav["beta"][1], 2),
      "| distance elasticity:", round(grav["beta"][2], 2))
gaps = A.demand_gaps(grav, G)
gaps.head(8)'''),
    code('''R.plot_network_map(G, gaps, Path("outputs/figures/network_map.png"))
display(Image("outputs/figures/network_map.png"))'''),
    md("""
The same network is exported as `outputs/network.geojson`, which GitHub draws as an interactive map,
and as `outputs/network_map.html` with Leaflet and OpenStreetMap tiles.
"""),
    code('''geo = R.geojson(G, gaps, Path("outputs/network.geojson"))
R.html_map(geo, Path("outputs/network_map.html"))
print(geo.stat().st_size // 1024, "KB GeoJSON written")'''),
]

NB3 = [
    md(f"""
# 03 · Demand forecast and the winter 2026/27 offer

{badge("03_forecast_and_winter_plan.ipynb")}

Bookings are not demand. When a bus sells out, the people who wanted a seat and did not get one
leave no trace in the data. A forecast trained on raw bookings would therefore plan too few seats
exactly where more are needed.
"""),
    code(SETUP),
    code(LOAD + '''
trips = V.clean_trips(tables)'''),
    md("""
## Forecast

The model is a log-linear regression per departure with month, weekday, holiday and a trend per
line. Sold-out trips are treated as censored: their demand is set to at least the bookings and
re-estimated from the model, repeated until it settles.

The backtest trains on data before 14 December 2025 and forecasts the 2025/26 winter timetable. The
synthetic data keeps the true demand, so the forecast can be scored against what people actually
wanted, not only against what they managed to book.
"""),
    code('''bt, weekly = P.backtest(trips, tables["truth_demand"], tables["timetable"])
pd.Series(bt).round(3)'''),
    code('''R.plot_backtest(weekly, Path("outputs/figures/forecast_backtest.png"))
display(Image("outputs/figures/forecast_backtest.png"))'''),
    md("""
## Offer options

For every line and direction there are 16 options: 1 to 8 departures a day, single or double-decker.
Each option is simulated 200 times with demand noise, which gives passengers carried, sold-out share,
revenue, bus cost and bus-hours for the whole winter season. More departures also attract some
extra demand (elasticity 0.35).
"""),
    code('''model = P.DemandModel().fit(trips)
opts = P.options(model, trips, tables["timetable"], C.PLAN_SEASON)
opts[opts["line"] == "L016"].query("direction == 'A' and departures <= 3")[
    ["departures", "bus", "served_pax", "sold_out_share", "contribution_eur", "bus_hours", "is_current"]].round(2)'''),
    md("""
## Choosing the plan

A mixed-integer program picks one option per line and direction. It maximises contribution with
these rules: total bus-hours at most 3% above today, at least as many passengers as today, both
directions of a line get the same offer, partners cannot run more double-deckers than they own,
and no new option may sell out on more than a quarter of departures.
"""),
    code('''opts = P.optimise(opts, tables["partners"])
plan = P.plan_table(opts)
plan[(plan["direction"] == "A") & (plan["change"] == "change")][
    ["line", "current", "proposed", "sold_out_now", "sold_out_plan", "contribution_delta"]]'''),
    code('''tot = plan[["served_now", "served_plan", "contribution_now", "contribution_plan", "bus_hours_now", "bus_hours_plan"]].sum()
print(f"Passengers  {tot.served_now:,.0f} -> {tot.served_plan:,.0f}")
print(f"Contribution {tot.contribution_now:,.0f} -> {tot.contribution_plan:,.0f} EUR ({tot.contribution_plan / tot.contribution_now - 1:+.1%})")
print(f"Bus-hours   {tot.bus_hours_now:,.0f} -> {tot.bus_hours_plan:,.0f} ({tot.bus_hours_plan / tot.bus_hours_now - 1:+.1%})")
print(f"Average sold-out share {plan.sold_out_now.mean():.1%} -> {plan.sold_out_plan.mean():.1%}")'''),
    md("""
Most changes swap three single-deckers for two double-deckers: the same seats with fewer buses and
drivers. L016 Berlin to Warsaw moves to a double-decker. L020 goes the other way and gets more,
smaller departures, because the plan has to carry at least as many passengers as today and L020 is
the cheapest place to add capacity. That is a choice for the planner to confirm, not an automatic
decision.
"""),
    code('''R.plot_plan(plan, Path("outputs/figures/winter_plan.png"))
display(Image("outputs/figures/winter_plan.png"))'''),
    md("""
## The Excel report

One workbook for the planning team: the issue log with an open-issue counter, line KPIs with formulas
for load factor and contribution, the winter plan, demand gaps and monthly passengers per line.
"""),
    code('''from openpyxl import load_workbook
xlsx = R.write_excel(Path("outputs/network_planning_report.xlsx"), issues=V.issue_log(V.run_all(tables)),
                     kpis=A.line_kpis(trips, LAST_12M), plan=plan,
                     gaps=A.demand_gaps(A.fit_gravity(tables["od_monthly"], LAST_12M), A.network_graph(trips, LAST_12M)),
                     monthly=trips.groupby(["line", "month"])["pax"].sum().reset_index())
wb = load_workbook(xlsx)
print("Sheets:", wb.sheetnames)
print("Example formulas:", wb["Line KPIs"]["I2"].value, "|", wb["Winter plan"]["L2"].value, "|", wb["Issue log"]["C11"].value)'''),
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
        "01_data_validation.ipynb": NB1,
        "02_network_and_line_performance.ipynb": NB2,
        "03_forecast_and_winter_plan.ipynb": NB3,
    }
    for name, cells in books.items():
        _execute(cells, NB_DIR)
        _write(cells, NB_DIR / name)
        print(f"built and executed {name}: {sum(c['cell_type'] == 'code' for c in cells)} code cells")


if __name__ == "__main__":
    main()
