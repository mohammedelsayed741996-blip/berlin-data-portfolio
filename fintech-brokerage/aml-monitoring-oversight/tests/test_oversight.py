import pytest

from aml_oversight import config as C, db, oversight as O


def test_zero_failure_sample_size():
    assert O.zero_failure_sample_size(0.95, 0.05) == 59


def test_clopper_pearson_known_values():
    lo, hi = O.clopper_pearson(0, 59)
    assert lo == 0 and hi == pytest.approx(0.0606, abs=1e-3)
    lo, hi = O.clopper_pearson(5, 50)
    assert lo == pytest.approx(0.0333, abs=1e-3) and hi == pytest.approx(0.2181, abs=1e-3)


def test_completeness_finds_the_feed_gap(run):
    miss = run.completeness[run.completeness["missing_count"] > 0]
    assert set(miss["source"]) == {f"CARD {C.FEED_GAP[2]}"}
    assert set(miss["month"]) == {"2026-06", "2026-07"}


def test_qa_singles_out_the_weak_analyst(run):
    d = run.qa_by_analyst[run.qa_by_analyst["error_type"] == "decision_error"].set_index("analyst")
    assert d["ci_low"].idxmax() == C.WEAK_ANALYST
    assert d.loc[C.WEAK_ANALYST, "ci_low"] > C.QA_TOLERABLE_ERROR
    assert len(run.lookback) > 20


def test_r02_change_is_detected(run):
    assert run.volume_change["change_pct"] < -0.4 and run.volume_change["p_value"] < 0.01
    btl = run.below_the_line.set_index("min_deposits")
    assert btl.loc[3, "clients_alerted"] > btl.loc[5, "clients_alerted"]


def test_mule_typology_is_a_coverage_gap_found_by_network_analysis(run, tables):
    cov = run.coverage.set_index("typology")
    assert cov.loc["T4 mule ring", "any_rule"] < 0.1
    assert (cov.drop(index="T4 mule ring")["any_rule"] > 0.9).all()
    mules = set(tables["typology_truth"].query("typology == 'T4 mule ring'")["client_id"])
    found = set(", ".join(run.networks["client_ids"]).split(", "))
    assert mules <= found and len(run.networks) == 6


def test_screening_qa_finds_the_wrong_closure(run):
    wrong = run.screening_qa[run.screening_qa["true_match"]]
    assert len(wrong) == 1
    assert run.screening["screened_late"] > 0


def test_findings_register_covers_every_planted_problem(run):
    areas = set(run.findings["area"])
    assert {"TM data completeness", "Rule governance", "Typology coverage", "Alert decision quality", "Sanctions screening",
            "Alert timeliness", "Documentation", "Screening timeliness", "Periodic reviews"} <= areas
    assert run.findings.iloc[0]["severity"] == "Critical"


def test_kri_status_matches_limits(run):
    k = run.kri.dropna(subset=["value"])
    for r in k.itertuples():
        assert r.status == O.rag(r.value, C.KRI_LIMITS[r.kri])


def test_sql_matches_python(tables, run):
    conn = db.connect(tables)
    rec = db.run_sql(conn, "01_feed_reconciliation.sql")
    assert rec["missing_count"].sum() == run.completeness["missing_count"].sum()
    rules = db.run_sql(conn, "03_rule_effectiveness.sql").set_index("rule")
    assert (rules["sars"] == run.rules.set_index("rule")["sars"]).all()
    shared = db.run_sql(conn, "04_shared_payout_accounts.sql")
    assert len(shared) == 6
    rev = db.run_sql(conn, "05_overdue_reviews.sql").set_index("risk_rating")
    assert rev.loc["high", "overdue"] == run.reviews.set_index("risk_rating").loc["high", "overdue"]
