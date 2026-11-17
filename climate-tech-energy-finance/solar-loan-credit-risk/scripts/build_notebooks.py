"""Build and execute the project notebooks without Jupyter.

The notebooks are defined here as lists of markdown and code cells. Each code
cell is executed in one shared namespace (like a kernel), and its printed
output, last expression and images are stored as real notebook outputs. The
result is a standard nbformat 4 file that opens in Jupyter, VS Code, GitHub
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
import types
from pathlib import Path

os.environ.setdefault("MPLBACKEND", "Agg")
PROJECT = Path(__file__).resolve().parents[1]
NB_DIR = PROJECT / "notebooks"

SETUP = '''import os, sys, subprocess
from pathlib import Path

REPO = "https://github.com/mohammedelsayed741996-blip/berlin-data-portfolio.git"
PROJECT = "climate-tech-energy-finance/solar-loan-credit-risk"

if "google.colab" in sys.modules:
    if not Path("/content/berlin-data-portfolio").exists():
        subprocess.run(["git", "clone", "--depth", "1", REPO, "/content/berlin-data-portfolio"], check=True)
    os.chdir(f"/content/berlin-data-portfolio/{PROJECT}")
else:
    here = Path.cwd()
    while not (here / "src" / "solar_credit").exists() and here != here.parent:
        here = here.parent
    os.chdir(here)

sys.path.insert(0, str(Path.cwd() / "src"))
import pandas as pd
pd.set_option("display.max_columns", 30)
pd.set_option("display.width", 160)
from IPython.display import Image, display
print("Project folder:", Path.cwd().name)'''


def md(text: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": text.strip("\n")}


def code(text: str) -> dict:
    return {"cell_type": "code", "metadata": {}, "source": text.strip("\n"), "execution_count": None, "outputs": []}


# ---------------------------------------------------------------- notebook 1
NB1 = [
    md("""
# 01 · Portfolio monitoring with SQL

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/mohammedelsayed741996-blip/berlin-data-portfolio/blob/main/climate-tech-energy-finance/solar-loan-credit-risk/notebooks/01_portfolio_monitoring.ipynb)

A lender that finances solar panels, batteries and heat pumps through installer partners has to answer the same questions every month: how big is the book, how much of it is late, how are the older vintages ageing, and how much depends on a few installers.

This notebook answers them with the six queries in `sql/`, run against an in-memory SQLite copy of a synthetic loan book (10,000 loans, Germany and Austria, originated 2023 to 2025, observed on 31 Oct 2026).
"""),
    code(SETUP),
    md("## Load the loan book\n\nThe data is generated on first run if `data/` is empty. Borrowers and installers only appear as pseudonymous IDs."),
    code('''from solar_credit.data_generator import load_loan_book
from solar_credit.monitoring import PortfolioDB, herfindahl_index, roll_rate_matrix
from solar_credit import reporting

book = load_loan_book()
print(f"{len(book.loans):,} loans, {len(book.performance):,} monthly performance rows, {len(book.installers)} installers")
book.loans.head(3)'''),
    code('''db = PortfolioDB(book)
print(open("sql/01_portfolio_snapshot.sql").read())
db.run("01_portfolio_snapshot")'''),
    md("""
## Delinquency trend

Arrears are a small share of balance, which is what you'd expect from a book where most of the volume is less than two years old. The trend line matters more than the level: a rising 30+ share usually shows up three months before the defaults do.
"""),
    code('''trend = db.run("02_delinquency_trend")
display(Image(filename=str(reporting.plot_delinquency_trend(trend, Path("outputs/figures/delinquency_trend.png")))))
trend.tail(6)'''),
    md("""
## Vintage curves

Each line is a cohort of loans, tracked by months on book. The query cuts every vintage at the age its youngest open loan has reached, so a new vintage cannot look better just because it has had less time to go wrong.

The Q1 2023 cohort reached 4.0% cumulative defaults after 12 months, 9.4% after 24 and 12.5% after 36. Most defaults land in the first two years and the curve flattens in year three. The ECL model's lifetime PD assumes the same fading pattern. Later vintages are running below the 2023 ones at the same age.
"""),
    code('''vintages = db.run("03_vintage_curves")
display(Image(filename=str(reporting.plot_vintage_curves(vintages, Path("outputs/figures/vintage_curves.png")))))
vintages.groupby("vintage")["cumulative_default_rate"].max().to_frame("cumulative_default_rate_to_date")'''),
    md("""
## Roll rates

A borrower who misses one payment cures about four times in ten. Once they reach 60 days past due, roughly three in four go on to default. That is why the ECL model moves every 30+ loan into stage 2 and uses observed roll-to-default rates for it, not the scorecard PD.
"""),
    code('''rolls = db.run("04_roll_rates")
roll_rate_matrix(rolls)'''),
    md("""
## Installer concentration

Installer partners are a credit risk of their own. If a large installer goes bust, customers lose their warranty and service contact, and recoveries on repossessed systems fall. The biggest partner here holds about 16% of open exposure, above a 10% single-name limit, even though the overall HHI looks unconcentrated. That gap is the point: HHI alone would not have raised the flag.
"""),
    code('''inst = db.run("05_installer_concentration")
print("Installer HHI:", herfindahl_index(inst["share_of_book"]))
display(Image(filename=str(reporting.plot_installer_concentration(inst, Path("outputs/figures/installer_concentration.png")))))
inst.head(10)'''),
    md("## Region and product mix\n\nAt book level, 1.3% of heat pump balance is 30+ days late, against 0.3% to 0.6% for the PV products. The median heat pump customer saves energy worth about 17% of the instalment; for PV with a battery it is above 100%."),
    code('''seg = db.run("06_segment_mix")
seg["late_eur"] = seg["dpd30_plus_share"] * seg["exposure_eur"]
by_product = seg.groupby("product_type")[["exposure_eur", "late_eur"]].sum()
by_product["dpd30_plus_share"] = (by_product["late_eur"] / by_product["exposure_eur"]).round(4)
by_product.drop(columns="late_eur").sort_values("exposure_eur", ascending=False)'''),
    code("db.close()"),
]

# ---------------------------------------------------------------- notebook 2
NB2 = [
    md("""
# 02 · PD scorecard, challenger model and underwriting cut-off

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/mohammedelsayed741996-blip/berlin-data-portfolio/blob/main/climate-tech-energy-finance/solar-loan-credit-risk/notebooks/02_pd_scorecard_and_underwriting.ipynb)

Goal: a 12-month probability of default (PD) that an underwriter can defend line by line, and a score cut-off that keeps the approved book under a 2% bad rate.

* Target: default (90+ days past due) within 12 months of origination. Loans younger than 12 months are left out, so a loan that hasn't had time to default never counts as "good".
* Split: out of time. Loans from Jan 2023 to Jun 2024 train the model; Jul 2024 to Oct 2025 test it.
"""),
    code(SETUP),
    code('''from solar_credit.data_generator import load_loan_book
from solar_credit.features import build_model_data
from solar_credit.scorecard import Scorecard
from solar_credit.models import GradientBoostingPD, evaluate, calibration_table, binomial_test_by_grade
from solar_credit.underwriting import DecisionEngine, strategy_table, choose_cutoff
from solar_credit import reporting

book = load_loan_book()
md = build_model_data(book.loans)
print(f"train: {len(md.train):,} loans, {md.y_train.sum()} defaults ({md.y_train.mean():.2%})")
print(f"test:  {len(md.test):,} loans, {md.y_test.sum()} defaults ({md.y_test.mean():.2%})")'''),
    md("""
## Feature screening with information value

Bureau score is the strongest single driver. Second is the savings coverage ratio: the customer's expected monthly energy savings divided by the loan instalment. When the panels pay most of the instalment, the loan rarely goes bad. Regional unemployment and income fall below the 0.02 IV threshold and are dropped.
"""),
    code('''sc = Scorecard().fit(md.X_train, md.y_train)
sc.iv_table()'''),
    code('''pts = sc.points_table()
pts.loc[pts["feature"].isin(["bureau_score", "savings_coverage_ratio"]), ["feature", "bin", "n", "bad_rate", "woe", "points"]]'''),
    md("## Champion vs challenger\n\nThe gradient-boosting challenger fits the training years far better (its train AUC is near 0.97) but loses on the later test vintages. The scorecard wins on AUC, KS and calibration, and it explains itself, so it stays the champion."),
    code('''gbm = GradientBoostingPD().fit(md.X_train, md.y_train)
pd_sc, pd_gb = sc.predict_pd(md.X_test), gbm.predict_pd(md.X_test)
pd.DataFrame([
    evaluate(md.y_test, pd_sc, "Scorecard (test)"),
    evaluate(md.y_test, pd_gb, "Gradient boosting (test)"),
    evaluate(md.y_train, gbm.predict_pd(md.X_train), "Gradient boosting (train)"),
])'''),
    code('''calib = {"Scorecard": calibration_table(md.y_test, pd_sc), "Gradient boosting": calibration_table(md.y_test, pd_gb)}
display(Image(filename=str(reporting.plot_calibration(calib, Path("outputs/figures/calibration.png")))))
binomial_test_by_grade(md.y_test, pd_sc)'''),
    md("One of five grades shows more defaults than predicted at the 5% level. With five tests one false alarm is not unusual, but in production it would go on the watch list for the next quarterly review."),
    md("## Choosing the cut-off\n\nEach point is a score cut-off. Moving from 560 to 580 gives up about 10 points of approval rate and cuts the approved bad rate from 2.0% to 1.3%. The engine picks the lowest cut-off that stays under 2%."),
    code('''strategy = strategy_table(md.y_test, sc.score(md.X_test))
cutoff = choose_cutoff(strategy, max_bad_rate=0.02)
print("Chosen cut-off:", cutoff)
display(Image(filename=str(reporting.plot_strategy(strategy, cutoff, Path("outputs/figures/cutoff_strategy.png")))))
strategy'''),
    md("## Decisions with reason codes\n\nPolicy rules run first: debt-to-income above 45%, bureau score under 400, or PV savings covering less than 35% of the instalment are declines whatever the score. Below the cut-off there is a 20-point refer band for manual review. Every decline lists where the applicant lost the most points."),
    code('''engine = DecisionEngine(sc, cutoff)
decisions = DecisionEngine.to_frame(engine.decide(md.test.sample(12, random_state=3)))
decisions'''),
    code('''DecisionEngine.to_frame(engine.decide(md.test))["decision"].value_counts(normalize=True).round(3)'''),
]

# ---------------------------------------------------------------- notebook 3
NB3 = [
    md("""
# 03 · Expected credit loss and stress testing

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/mohammedelsayed741996-blip/berlin-data-portfolio/blob/main/climate-tech-energy-finance/solar-loan-credit-risk/notebooks/03_ecl_and_stress_testing.ipynb)

This notebook takes the open book on 31 Oct 2026 and asks two questions an investor or warehouse lender will ask: how much do we expect to lose, and how bad does it get if power prices fall or a recession hits?

ECL follows the IFRS 9 staging logic: stage 1 gets a 12-month loss, stage 2 (30+ days late, or PD more than doubled since origination) a lifetime loss, stage 3 (defaulted, workout still open) LGD times exposure.
"""),
    code(SETUP),
    code('''from solar_credit.data_generator import load_loan_book
from solar_credit.features import build_model_data
from solar_credit.scorecard import Scorecard
from solar_credit.ecl import current_book, lgd_by_product, roll_to_default_pd, compute_ecl
from solar_credit.stress import run_stress_tests, sensitivity_analysis
from solar_credit import config, reporting

book = load_loan_book()
md = build_model_data(book.loans)
sc = Scorecard().fit(md.X_train, md.y_train)
live = current_book(book.loans, book.performance)
print(f"Open loans incl. open workouts: {len(live):,}, exposure EUR {live['outstanding_balance_eur'].sum()/1e6:,.1f}m")'''),
    md("## Inputs: LGD and roll-to-default\n\nLGD comes from closed workouts, blended with a product prior through a credibility weight (n / (n + 30)). Heat pumps have the worst recoveries: once installed they are hard to take back and resell."),
    code('''lgd = lgd_by_product(book.loans)
rolls = roll_to_default_pd(book.performance)
print("12m roll-to-default from 30 DPD: {:.1%}, from 60 DPD: {:.1%}".format(rolls[30], rolls[60]))
lgd'''),
    code('''pd_now = sc.predict_pd(live)
ecl = compute_ecl(live, pd_now, pd_now, lgd, rolls)
print(f"Total ECL EUR {ecl.total_ecl/1e6:,.2f}m, coverage {ecl.coverage:.2%}")
ecl.by_stage'''),
    md("Most of the provision sits in stage 3: 314 defaulted loans whose recoveries are still being worked out. Stage 1 loans need about 1.4% coverage."),
    md("""
## Scenarios

Shocks reach the PD through the model itself. Lower power prices shrink PV savings, which lowers the savings coverage ratio, which the scorecard re-scores. Unemployment is an overlay on the log-odds (+0.12 per percentage point), an expert assumption, because regional unemployment barely moved in the training data.
"""),
    code('''pd.DataFrame([vars(s) for s in config.SCENARIOS])'''),
    code('''stress = run_stress_tests(live, sc.predict_pd, lgd, rolls)
display(Image(filename=str(reporting.plot_stress(stress, Path("outputs/figures/stress_scenarios.png")))))
stress.drop(columns="description")'''),
    md("""
The severe recession costs about 3.4 times the baseline ECL. Most of the jump is not higher 12-month PDs: it is loans crossing the stage 2 line, where a 12-month loss becomes a lifetime loss on 10 to 20 year terms. Investors should see this cliff effect before it happens, not after.
"""),
    md("## Sensitivity: one driver at a time"),
    code('''sens = sensitivity_analysis(live, sc.predict_pd, lgd, rolls)
display(Image(filename=str(reporting.plot_sensitivity(sens, Path("outputs/figures/sensitivity_tornado.png")))))
sens'''),
    md("""
A 20% drop in power prices moves ECL more than a 30-point fall in every borrower's bureau score. For a green-energy lender, the electricity price is a credit risk factor, not just a sales argument. Two follow-ups would make sense: a covenant or pricing trigger tied to the savings coverage ratio, and monitoring of the forward power curve next to the delinquency report.
"""),
    md("## Investor report\n\nThe full pipeline writes the report to `outputs/investor_report.md`."),
    code('''from solar_credit.pipeline import run
summary = run()
print(open("outputs/investor_report.md").read()[:1500])'''),
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
        "01_portfolio_monitoring.ipynb": NB1,
        "02_pd_scorecard_and_underwriting.ipynb": NB2,
        "03_ecl_and_stress_testing.ipynb": NB3,
    }
    for name, cells in books.items():
        _execute(cells, NB_DIR)
        _write(cells, NB_DIR / name)
        print(f"built and executed {name}: {sum(c['cell_type'] == 'code' for c in cells)} code cells")


if __name__ == "__main__":
    main()
