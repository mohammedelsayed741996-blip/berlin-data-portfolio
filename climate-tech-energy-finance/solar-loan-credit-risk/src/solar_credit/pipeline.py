"""End-to-end run: data -> PD models -> underwriting -> ECL -> stress -> report.

Usage (from the project folder)::

    python -m solar_credit.pipeline            # uses data/ if present
    python -m solar_credit.pipeline --regenerate
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import pandas as pd

from . import config, reporting
from .data_generator import generate_loan_book, load_loan_book
from .ecl import compute_ecl, current_book, lgd_by_product, roll_to_default_pd
from .features import build_model_data
from .models import GradientBoostingPD, binomial_test_by_grade, calibration_table, evaluate
from .monitoring import PortfolioDB, herfindahl_index
from .scorecard import Scorecard
from .stress import run_stress_tests, sensitivity_analysis
from .underwriting import DecisionEngine, choose_cutoff, strategy_table

logger = logging.getLogger(__name__)


def run(regenerate: bool = False, output_dir: Path = config.OUTPUT_DIR, data_dir: Path = config.DATA_DIR) -> dict:
    """Run every step and write outputs. Returns the key results."""
    fig_dir = output_dir / "figures"
    output_dir.mkdir(parents=True, exist_ok=True)
    if regenerate:
        generate_loan_book().save(data_dir)
    book = load_loan_book(data_dir)

    # 1. PD models
    md = build_model_data(book.loans)
    scorecard = Scorecard().fit(md.X_train, md.y_train)
    gbm = GradientBoostingPD().fit(md.X_train, md.y_train)
    pd_sc = scorecard.predict_pd(md.X_test)
    pd_gb = gbm.predict_pd(md.X_test)
    metrics = {"scorecard": evaluate(md.y_test, pd_sc, "scorecard"), "gbm": evaluate(md.y_test, pd_gb, "gbm")}
    calib = {"Scorecard": calibration_table(md.y_test, pd_sc), "Gradient boosting": calibration_table(md.y_test, pd_gb)}
    scorecard.iv_table().to_csv(output_dir / "information_value.csv", index=False)
    scorecard.points_table().to_csv(output_dir / "scorecard_points.csv", index=False)
    binomial_test_by_grade(md.y_test, pd_sc).to_csv(output_dir / "calibration_binomial_test.csv", index=False)
    reporting.plot_calibration(calib, fig_dir / "calibration.png")

    # 2. Underwriting strategy and sample decisions
    strategy = strategy_table(md.y_test, scorecard.score(md.X_test))
    cutoff = choose_cutoff(strategy, max_bad_rate=0.02)
    strategy.to_csv(output_dir / "cutoff_strategy.csv", index=False)
    reporting.plot_strategy(strategy, cutoff, fig_dir / "cutoff_strategy.png")
    engine = DecisionEngine(scorecard, cutoff)
    sample = md.test.sample(25, random_state=3)
    decisions = DecisionEngine.to_frame(engine.decide(sample))
    decisions.to_csv(output_dir / "sample_decisions.csv", index=False)

    # 3. Monitoring SQL
    with PortfolioDB(book) as db:
        snapshot_tbl = db.run("01_portfolio_snapshot")
        trend = db.run("02_delinquency_trend")
        vintages = db.run("03_vintage_curves")
        rolls = db.run("04_roll_rates")
        installers = db.run("05_installer_concentration")
        segments = db.run("06_segment_mix")
    for name, frame in {"portfolio_snapshot": snapshot_tbl, "delinquency_trend": trend, "vintage_curves": vintages,
                        "roll_rates": rolls, "installer_concentration": installers, "segment_mix": segments}.items():
        frame.to_csv(output_dir / f"{name}.csv", index=False)
    reporting.plot_vintage_curves(vintages, fig_dir / "vintage_curves.png")
    reporting.plot_delinquency_trend(trend, fig_dir / "delinquency_trend.png")
    reporting.plot_installer_concentration(installers, fig_dir / "installer_concentration.png")

    # 4. ECL and stress tests on the live book
    live = current_book(book.loans, book.performance)
    lgd_table = lgd_by_product(book.loans)
    roll_pd = roll_to_default_pd(book.performance)
    pd_now = scorecard.predict_pd(live)
    ecl = compute_ecl(live, pd_now, pd_now, lgd_table, roll_pd)
    stress = run_stress_tests(live, scorecard.predict_pd, lgd_table, roll_pd)
    sens = sensitivity_analysis(live, scorecard.predict_pd, lgd_table, roll_pd)
    lgd_table.to_csv(output_dir / "lgd_by_product.csv", index=False)
    ecl.by_stage.to_csv(output_dir / "ecl_by_stage.csv", index=False)
    stress.to_csv(output_dir / "stress_results.csv", index=False)
    sens.to_csv(output_dir / "sensitivity.csv", index=False)
    reporting.plot_stress(stress, fig_dir / "stress_scenarios.png")
    reporting.plot_sensitivity(sens, fig_dir / "sensitivity_tornado.png")

    # 5. Investor report
    open_mask = live["status"] != "Defaulted"
    snapshot = {
        "open_loans": int(open_mask.sum()),
        "exposure_eur": float(live.loc[open_mask, "outstanding_balance_eur"].sum()),
        "dpd30_share": float(live.loc[open_mask & (live["days_past_due"] >= 30), "outstanding_balance_eur"].sum()
                             / live.loc[open_mask, "outstanding_balance_eur"].sum()),
        "open_workouts": int((~open_mask).sum()),
        "defaults_to_date": int(book.loans["default_flag"].sum()),
        "default_rate_to_date": float(book.loans["default_flag"].mean()),
        "top_installer_share": float(installers["share_of_book"].max()),
        "hhi": herfindahl_index(installers["share_of_book"]),
    }
    cutoff_row = strategy.loc[strategy["cutoff"] == cutoff].iloc[0].to_dict()
    ctx = {
        "as_of": config.OBSERVATION_DATE, "snapshot": snapshot, "stress": stress, "sensitivity": sens,
        "ecl_by_stage": ecl.by_stage, "ecl_total": ecl.total_ecl, "ecl_coverage": ecl.coverage,
        "metrics": metrics, "cutoff": cutoff, "cutoff_row": cutoff_row, "installers": installers,
    }
    reporting.investor_report(ctx, output_dir / "investor_report.md")

    summary = {
        "model_metrics": metrics,
        "cutoff": cutoff,
        "cutoff_approval_rate": cutoff_row["approval_rate"],
        "cutoff_bad_rate": cutoff_row["approved_bad_rate"],
        "snapshot": snapshot,
        "ecl_total_eur": round(ecl.total_ecl, 0),
        "ecl_coverage": round(ecl.coverage, 4),
        "stress": stress[["scenario", "ecl_eur", "ecl_coverage", "ecl_vs_baseline"]].to_dict("records"),
        "roll_to_default_pd": roll_pd,
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2, default=float), encoding="utf-8")
    logger.info("Pipeline finished. ECL %.0f EUR (%.2f%% coverage)", ecl.total_ecl, ecl.coverage * 100)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Solar loan credit-risk pipeline")
    parser.add_argument("--regenerate", action="store_true", help="rebuild the synthetic data first")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    pd.set_option("display.width", 160)
    summary = run(regenerate=args.regenerate)
    print(json.dumps(summary, indent=2, default=float))


if __name__ == "__main__":
    main()
