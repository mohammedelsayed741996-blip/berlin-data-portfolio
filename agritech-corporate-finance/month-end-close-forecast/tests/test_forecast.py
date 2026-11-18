import pandas as pd
import pytest

from close_forecast import config as C, forecast
from close_forecast.fiscal import fiscal_months


def test_backtest_beats_naive_run_rate(run):
    avg = run.backtest.groupby("method")["wape"].mean()
    assert avg["run_rate"] == avg.max()
    assert set(run.choice["chosen_method"]) <= set(forecast.METHODS)
    assert (run.choice["chosen_wape"] <= run.choice["budget_wape"]).all()


def test_forecast_covers_remaining_months_for_every_line(run):
    fc = run.cost_forecast
    f = fc[fc["kind"] == "forecast"]
    assert sorted(f["month"].unique()) == fiscal_months("2026/27")[3:]
    keys_f = f.groupby(forecast.KEY).size()
    assert (keys_f == 9).all()
    assert (f["method"] != "").all()


def test_forecast_starts_from_corrected_actuals(run):
    fc = run.cost_forecast
    a = fc[(fc["kind"] == "actual") & (fc["month"] == C.CLOSE_PERIOD)]
    camp = C.PLANTED_CLOSE_ISSUES["misallocated_journal"]
    rnd = a[(a["cost_center"] == camp["booked_on"]) & (a["gl_account"] == "6500")]["amount_eur"].sum()
    bud = fc[(fc["kind"] == "budget") & (fc["month"] == C.CLOSE_PERIOD) & (fc["cost_center"] == camp["booked_on"])
             & (fc["gl_account"] == "6500")]["amount_eur"].sum()
    assert rnd < bud * 1.5           # the 250k campaign no longer sits on breeding
    dep = a[(a["company_code"] == "AT10") & (a["gl_account"] == "6200")]["amount_eur"].sum()
    assert dep > 0                   # missing depreciation run filled in


def test_driver_method_keeps_the_november_bonus(run):
    fc = run.cost_forecast
    f = fc[(fc["kind"] == "forecast") & (fc["gl_account"] == "6000")].groupby("month")["amount_eur"].sum()
    assert f["2026-11"] > 1.4 * f["2026-10"]


def test_rnd_hiring_delay_shows_up_as_underspend(run):
    land = run.landing.set_index("line")
    assert land.loc["Research and development", "var_vs_budget_eur"] > 0      # costs negative, so positive = below budget


def test_landing_adds_up(run):
    land = run.landing.set_index("line")
    body = land.drop(index="EBIT")
    assert land.loc["EBIT", "outlook_fy"] == pytest.approx(body["outlook_fy"].sum(), abs=5)
    assert (land["outlook_fy"] - land["actual_ytd"] - land["forecast_rest"]).abs().max() <= 1


def test_revenue_forecast_carries_the_cereal_shortfall_but_not_into_corn(run):
    rv = run.revenue_forecast
    f = rv[rv["kind"] == "forecast"].groupby("crop")[["volume_ratio", "price_ratio"]].first()
    assert f.loc["cereals", "volume_ratio"] < 0.9
    assert f.loc["corn", "volume_ratio"] == 1.0          # corn season has barely started


def test_capex_eac_flags_only_the_greenhouse(run):
    cap = run.capex.set_index("wbs")
    over = cap[cap["eac_vs_budget_pct"] > C.CAPEX_OVERRUN_LIMIT - 1].index.tolist()
    assert over == [C.PLANTED_CLOSE_ISSUES["capex_overrun"]["wbs"]]
