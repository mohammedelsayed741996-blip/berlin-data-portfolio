import pytest

from close_forecast import close_checks, config as C, db

P = C.PLANTED_CLOSE_ISSUES


def test_every_planted_issue_is_found(checks):
    assert checks["C01"].amount_eur == P["unbalanced_document"]["difference"]
    assert checks["C02"].amount_eur == P["blocked_cost_center"]["amount"]
    assert checks["C03"].amount_eur == P["wrong_entity_cost_center"]["amount"]
    assert checks["C04"].amount_eur == P["missing_cost_center"]["amount"]
    assert checks["C05"].amount_eur == P["duplicate_invoice"]["amount"]
    assert len(checks["C06"].exceptions) == P["late_postings"]["count"]
    assert len(checks["C09"].exceptions) == P["aged_grir"]["count"]
    assert checks["C10"].amount_eur == P["suspense_balance"]["amount"]
    assert list(checks["C12"].exceptions["wbs"]) == [P["capex_overrun"]["wbs"]]


def test_missing_recurring_postings(checks):
    missing = set(checks["C07"].exceptions["posting"])
    assert missing == {"depreciation run", "rent", "IC IT recharge"}


def test_intercompany_gap_matches_missing_charge(checks):
    gap = checks["C08"].exceptions
    assert list(gap["pair"]) == ["DE10-AT10"]
    missing_ic = checks["C07"].exceptions.set_index("posting").loc["IC IT recharge", "last_month_eur"]
    assert gap["balance_difference_eur"].iloc[0] == pytest.approx(missing_ic)


def test_clean_month_passes(tables):
    results = close_checks.run_close_checks(tables, "2025-12")
    assert all(r.status == "PASS" for r in results), [r.check_id for r in results if r.status != "PASS"]


def test_billing_agrees_with_ledger(checks):
    assert checks["C11"].status == "PASS"


def test_adjustments_cover_the_fixable_issues(run):
    adj = run.adjustments
    assert {"C02", "C03", "C04", "C05", "C07", "VAR"} <= set(adj["check_id"])
    moves = adj[adj["check_id"].isin(["C02", "C03", "C04", "VAR"])]
    assert moves["amount_eur"].sum() == pytest.approx(0, abs=0.01)   # reclasses do not change profit
    assert adj.loc[adj["check_id"] == "C05", "amount_eur"].sum() == -P["duplicate_invoice"]["amount"]


@pytest.fixture(scope="module")
def conn(tables):
    return db.connect(tables)


def test_sql_unbalanced_matches_python(conn, checks):
    sql = db.run_sql(conn, "02_unbalanced_documents.sql")
    assert list(sql["doc_no"]) == list(checks["C01"].exceptions["doc_no"])


def test_sql_intercompany_matches_python(conn, tables):
    sql = db.run_sql(conn, "03_intercompany_reconciliation.sql").set_index("pair")
    py = close_checks.intercompany_matrix(tables, C.CLOSE_PERIOD).set_index("pair")
    assert sql["difference_eur"].to_dict() == pytest.approx(py["balance_difference_eur"].to_dict())


def test_sql_grir_and_duplicates_match_python(conn, checks):
    aging = db.run_sql(conn, "04_grir_aging.sql")
    assert (aging["age_days"] > 60).sum() == len(checks["C09"].exceptions)
    dups = db.run_sql(conn, "05_duplicate_invoices.sql")
    assert dups["reference"].tolist() == [P["duplicate_invoice"]["reference"]]


def test_sql_trial_balance_matches_python(conn, tables):
    sql = db.run_sql(conn, "01_trial_balance.sql")
    py = close_checks.trial_balance(tables)
    py = py[py["gl_account"] != "2970"]
    assert sql["balance_eur"].sum() == pytest.approx(py["amount_eur"].sum(), abs=0.05)
    assert len(sql) == len(py)
