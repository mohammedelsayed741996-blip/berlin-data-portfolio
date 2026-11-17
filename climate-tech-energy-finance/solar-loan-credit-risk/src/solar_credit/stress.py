"""Scenario stress tests and one-factor sensitivity analysis.

Shocks reach the loss estimate through three channels:

1. Electricity prices change the savings a PV system produces, which moves
   the savings coverage ratio, which the scorecard re-scores.
2. A bureau score drift is re-scored the same way.
3. Unemployment is applied as a macro overlay on the log-odds of default.
   Regional unemployment barely varies inside the training window, so the
   scorecard cannot learn its effect; the overlay elasticity is an expert
   assumption and is listed as such in the README.

LGD shocks are added directly to the product LGD.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

import numpy as np
import pandas as pd

from . import config
from .ecl import ECLResult, compute_ecl

UNEMPLOYMENT_LOGIT_BETA = 0.12  # log-odds increase per +1pp unemployment
PV_PRICE_PASS_THROUGH = 0.85  # share of PV savings that moves with the power price


def shock_features(book: pd.DataFrame, scenario: config.Scenario) -> pd.DataFrame:
    """Return a copy of the book with scenario shocks applied to model inputs."""
    shocked = book.copy()
    has_pv = shocked["product_type"].str.contains("PV").to_numpy()
    factor = 1 + scenario.electricity_price_change * PV_PRICE_PASS_THROUGH
    shocked["savings_coverage_ratio"] = np.where(
        has_pv, shocked["savings_coverage_ratio"] * factor, shocked["savings_coverage_ratio"]
    )
    shocked["bureau_score"] = np.clip(shocked["bureau_score"] + scenario.bureau_score_shift, 100, 999)
    shocked["region_unemployment_pct"] = shocked["region_unemployment_pct"] + scenario.unemployment_shift_pp
    return shocked


def apply_macro_overlay(pd_values: np.ndarray, unemployment_shift_pp: float) -> np.ndarray:
    """Shift PDs on the log-odds scale for an unemployment shock."""
    p = np.clip(pd_values, 1e-6, 1 - 1e-6)
    logit = np.log(p / (1 - p)) + UNEMPLOYMENT_LOGIT_BETA * unemployment_shift_pp
    return 1 / (1 + np.exp(-logit))


def run_scenario(
    book: pd.DataFrame,
    scenario: config.Scenario,
    predict_pd: Callable[[pd.DataFrame], np.ndarray],
    pd_origination: np.ndarray,
    lgd_table: pd.DataFrame,
    roll_rates: dict[int, float],
) -> ECLResult:
    """ECL for one scenario."""
    shocked = shock_features(book, scenario)
    pd12 = apply_macro_overlay(predict_pd(shocked), scenario.unemployment_shift_pp)
    return compute_ecl(book, pd12, pd_origination, lgd_table, roll_rates, lgd_add_on=scenario.lgd_add_on)


def run_stress_tests(
    book: pd.DataFrame,
    predict_pd: Callable[[pd.DataFrame], np.ndarray],
    lgd_table: pd.DataFrame,
    roll_rates: dict[int, float],
    scenarios: tuple[config.Scenario, ...] = config.SCENARIOS,
) -> pd.DataFrame:
    """Summary table: one row per scenario."""
    pd_orig = predict_pd(book)
    base_ecl = None
    rows = []
    for sc in scenarios:
        res = run_scenario(book, sc, predict_pd, pd_orig, lgd_table, roll_rates)
        if base_ecl is None:
            base_ecl = res.total_ecl
        stage2 = res.loans.loc[res.loans["stage"] == 2, "ead_eur"].sum() / res.total_exposure
        rows.append(
            {
                "scenario": sc.name,
                "avg_pd_12m": round(float(res.loans.loc[res.loans["stage"] < 3, "pd_12m"].mean()), 4),
                "stage2_share_of_exposure": round(float(stage2), 4),
                "exposure_eur": round(res.total_exposure, 0),
                "ecl_eur": round(res.total_ecl, 0),
                "ecl_coverage": round(res.coverage, 4),
                "ecl_vs_baseline": round(res.total_ecl / base_ecl, 3),
                "description": sc.description,
            }
        )
    return pd.DataFrame(rows)


def sensitivity_analysis(
    book: pd.DataFrame,
    predict_pd: Callable[[pd.DataFrame], np.ndarray],
    lgd_table: pd.DataFrame,
    roll_rates: dict[int, float],
) -> pd.DataFrame:
    """Move one driver at a time and record the change in total ECL."""
    pd_orig = predict_pd(book)
    base = run_scenario(book, config.Scenario("Base"), predict_pd, pd_orig, lgd_table, roll_rates).total_ecl
    shocks = {
        "Power price -20%": config.Scenario("s", electricity_price_change=-0.20),
        "Power price +20%": config.Scenario("s", electricity_price_change=0.20),
        "Unemployment +2pp": config.Scenario("s", unemployment_shift_pp=2.0),
        "Bureau score -30": config.Scenario("s", bureau_score_shift=-30),
        "LGD +10pp": config.Scenario("s", lgd_add_on=0.10),
        "LGD -10pp": config.Scenario("s", lgd_add_on=-0.10),
    }
    rows = []
    for label, sc in shocks.items():
        ecl = run_scenario(book, replace(sc, name=label), predict_pd, pd_orig, lgd_table, roll_rates).total_ecl
        rows.append({"shock": label, "ecl_eur": round(ecl, 0), "change_eur": round(ecl - base, 0),
                     "change_pct": round(ecl / base - 1, 4)})
    return pd.DataFrame(rows).sort_values("change_eur", key=np.abs, ascending=False).reset_index(drop=True)
