import numpy as np
import pandas as pd
import pytest

from solar_credit import config
from solar_credit.ecl import compute_ecl, current_book, lgd_by_product, lifetime_pd, roll_to_default_pd
from solar_credit.monitoring import PortfolioDB, herfindahl_index
from solar_credit.stress import apply_macro_overlay, run_stress_tests, shock_features
from solar_credit.underwriting import DecisionEngine, choose_cutoff, strategy_table


@pytest.fixture(scope="module")
def live(book):
    return current_book(book.loans, book.performance)


def test_lifetime_pd_bounds():
    life = lifetime_pd(np.array([0.02, 0.02]), np.array([12, 120]))
    assert life[0] == pytest.approx(0.02)
    assert 0.02 < life[1] < 1 - (1 - 0.02) ** 10


def test_stage_three_ecl_is_lgd_times_ead(book, live, scorecard):
    lgd = lgd_by_product(book.loans)
    rolls = roll_to_default_pd(book.performance)
    p = scorecard.predict_pd(live)
    res = compute_ecl(live, p, p, lgd, rolls)
    s3 = res.loans.loc[res.loans["stage"] == 3]
    assert len(s3) > 0
    np.testing.assert_allclose(s3["ecl_eur"], (s3["lgd"] * s3["ead_eur"]).round(2), atol=0.02)
    assert set(res.loans["stage"]) <= {1, 2, 3}
    assert 0 < res.coverage < 0.5


def test_delinquent_loans_are_stage_two(book, live, scorecard):
    lgd = lgd_by_product(book.loans)
    p = scorecard.predict_pd(live)
    res = compute_ecl(live, p, p, lgd, roll_to_default_pd(book.performance))
    late = res.loans.loc[(res.loans["days_past_due"] >= 30) & (res.loans["status"] != "Defaulted")]
    assert (late["stage"] == 2).all()


def test_severe_scenario_costs_more_than_baseline(book, live, scorecard):
    lgd = lgd_by_product(book.loans)
    out = run_stress_tests(live, scorecard.predict_pd, lgd, roll_to_default_pd(book.performance))
    ecl = dict(zip(out["scenario"], out["ecl_eur"]))
    assert ecl["Severe recession"] > ecl["Mild downturn"] > ecl["Baseline"]
    assert ecl["Installer default wave"] > ecl["Baseline"]


def test_power_price_shock_only_moves_pv_coverage(live):
    sc = config.Scenario("t", electricity_price_change=-0.2)
    shocked = shock_features(live, sc)
    hp = live["product_type"] == "HeatPump"
    pd.testing.assert_series_equal(shocked.loc[hp, "savings_coverage_ratio"], live.loc[hp, "savings_coverage_ratio"])
    assert (shocked.loc[~hp, "savings_coverage_ratio"] < live.loc[~hp, "savings_coverage_ratio"]).all()


def test_macro_overlay_increases_pd():
    base = np.array([0.01, 0.05, 0.2])
    assert (apply_macro_overlay(base, 2.0) > base).all()
    np.testing.assert_allclose(apply_macro_overlay(base, 0.0), base)


def test_policy_rules_override_score(scorecard, model_data):
    app = model_data.X_test.head(1).copy()
    app["loan_id"] = "APP-1"
    app["dti_ratio"] = 0.60
    decision = DecisionEngine(scorecard, cutoff=0).decide(app)[0]
    assert decision.decision == "Decline"
    assert any("DTI" in r for r in decision.reasons)


def test_cutoff_choice_respects_target(scorecard, model_data):
    tab = strategy_table(model_data.y_test, scorecard.score(model_data.X_test))
    c = choose_cutoff(tab, max_bad_rate=0.02)
    row = tab.loc[tab["cutoff"] == c].iloc[0]
    assert row["approved_bad_rate"] <= 0.02 or c == tab["cutoff"].max()


def test_sql_queries_agree_with_pandas(book):
    with PortfolioDB(book) as db:
        snap = db.run("01_portfolio_snapshot")
        inst = db.run("05_installer_concentration")
        rolls = db.run("04_roll_rates")
        vint = db.run("03_vintage_curves")
    last = book.performance.loc[
        (book.performance["as_of_date"] == book.performance["as_of_date"].max())
        & book.performance["status"].isin(["Performing", "Delinquent"])
    ]
    assert snap["loans"].sum() == len(last)
    assert snap["outstanding_eur"].sum() == pytest.approx(last["outstanding_balance_eur"].sum(), rel=1e-6)
    assert inst["share_of_book"].sum() == pytest.approx(1.0, abs=1e-3)
    assert rolls.groupby("from_bucket")["roll_rate"].sum().round(3).eq(1.0).all()
    assert vint["cumulative_default_rate"].between(0, 1).all()
    assert 0 < herfindahl_index(inst["share_of_book"]) <= 10_000


def test_unknown_query_raises(book):
    with PortfolioDB(book) as db, pytest.raises(FileNotFoundError):
        db.run("does_not_exist")
