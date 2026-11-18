import pytest

from close_forecast import config as C, db, variance


def test_price_volume_effects_add_up(run):
    pvm = run.pvm
    assert (pvm["volume_effect_eur"] + pvm["price_effect_eur"]).sum() == pytest.approx(pvm["total_variance_eur"].sum(), abs=5)


def test_cereal_volume_shortfall_is_the_biggest_revenue_driver(run):
    pvm = run.pvm.set_index("crop")
    assert pvm["volume_effect_eur"].idxmin() == "cereals"
    assert pvm.loc["cereals", "units_vs_budget_pct"] == pytest.approx(C.ACTUAL_DRIFT_FY27["volume"]["cereals"] - 1, abs=0.03)


def test_misallocated_journal_is_traced_to_the_budgeted_cost_center(tables):
    mis = variance.find_misallocations(tables)
    assert len(mis) == 1
    row = mis.iloc[0]
    assert row["booked_cost_center"].startswith("3110") and row["proposed_cost_center"].startswith("2110")
    assert row["amount_eur"] == C.PLANTED_CLOSE_ISSUES["misallocated_journal"]["amount"]


def test_flags_respect_both_thresholds(tables):
    d = variance.bva(tables, by=["cost_center", "gl_account"])
    flagged = d[d["flag"]]
    assert (flagged["var_ytd_eur"].abs() > C.VARIANCE_THRESHOLD_EUR).all()
    assert (flagged["var_ytd_pct"].abs() > C.VARIANCE_THRESHOLD_PCT).all()


def test_planted_causes_are_explained_and_the_rest_goes_to_owners(run):
    c = run.comments
    explained = c[~c["explanation"].str.contains("To be explained")]
    for cc, account in [("3110", "External services"), ("2110", "External services"), ("4120", "External services"),
                        ("1200", "Depreciation"), ("2300", "Rent and facilities")]:
        assert ((explained["cost_center"] == cc) & (explained["account"] == account)).any(), (cc, account)
    assert c[c["account"] == "Energy"]["direction"].eq("over").all()
    open_items = c[c["explanation"].str.contains("To be explained")]
    assert (open_items["action"] == "Ask the owner").all()


def test_income_statement_ebit_is_the_sum_of_lines(run):
    is_ = run.income_statement.set_index("line")
    body = is_.drop(index=["Gross profit", "EBIT"])
    assert is_.loc["EBIT", "actual_ytd"] == pytest.approx(body["actual_ytd"].sum(), abs=2)


def test_sql_bva_matches_python(tables, run):
    sql = db.run_sql(db.connect(tables), "06_budget_vs_actual.sql").set_index("functional_area")
    py = run.bva_fa.set_index("functional_area")
    for fa in ["COS", "SEL", "RND", "GNA"]:
        assert sql.loc[fa, "actual_ytd"] == pytest.approx(py.loc[fa, "actual_ytd"], abs=0.05)
        assert sql.loc[fa, "budget_ytd"] == pytest.approx(py.loc[fa, "budget_ytd"], abs=0.05)
