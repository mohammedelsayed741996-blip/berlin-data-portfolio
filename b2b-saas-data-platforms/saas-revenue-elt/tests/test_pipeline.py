"""Integration tests on the full 92-day simulation: known answers and planted incidents."""

import json
import re
import shutil

from saas_elt.contracts import PII_PATTERNS
from saas_elt.reporting import incident_log, mrr_vs_truth, usage_vs_truth
from saas_elt.warehouse import Warehouse


def test_only_the_outage_day_fails(sim):
    failed = [r.run_date for r in sim.runs if r.status != "success"]
    assert failed == ["2026-09-13"]
    run = next(r for r in sim.runs if r.run_date == "2026-09-13")
    assert run.outcomes["transform"].attempts == 3
    assert run.outcomes["publish"].status == "upstream_failed"


def test_warehouse_mrr_matches_source_truth_every_day(sim):
    df = mrr_vs_truth(sim)
    assert len(df) == 93
    assert (df["difference"].abs() <= 0.01).all()


def test_usage_matches_delivered_events_every_day(sim):
    df = usage_vs_truth(sim)
    assert (df["difference"] == 0).all()


def test_no_failed_data_tests_or_reconciliations(wh):
    assert wh.query("SELECT COUNT(*) FROM meta_test_results WHERE status IN ('fail','error')")[0][0] == 0
    assert wh.query("SELECT COUNT(*) FROM meta_reconciliation WHERE status='fail'")[0][0] == 0


def test_planted_incidents_are_caught(wh, sim):
    reasons = " ".join(r[0] for r in wh.query("SELECT reasons FROM meta_quarantine"))
    assert "Mid-Market" in reasons
    assert "below_min: amount_net" in reasons
    assert reasons.count("malformed_json") == 5
    assert wh.query("SELECT field FROM meta_schema_drift") == [("discount_eur",)]
    overlap = wh.query("SELECT extracted, control_count FROM meta_batches WHERE batch_id='billing_invoices:2026-07-20'")[0]
    assert overlap[0] > overlap[1]
    assert len(incident_log(sim)) == 7


def test_bad_account_value_is_corrected_next_day(wh):
    seg = wh.query("SELECT segment FROM stg_crm__accounts WHERE account_id='ACC-00018'")[0][0]
    assert seg == "MidMarket"


def test_quarantine_holds_no_personal_data(wh):
    for (payload,) in wh.query("SELECT payload_json FROM meta_quarantine"):
        for pat in PII_PATTERNS.values():
            assert not pat.search(payload)
    # Broken event lines are logged by position only.
    for (payload,) in wh.query("SELECT payload_json FROM meta_quarantine WHERE reasons LIKE 'malformed_json%'"):
        assert set(json.loads(payload)) == {"file", "line", "length"}


def test_user_ids_are_pseudonymised(wh):
    sample = [r[0] for r in wh.query("SELECT user_hash FROM raw_product_events LIMIT 500")]
    assert all(re.fullmatch(r"[0-9a-f]{64}", h) for h in sample)


def test_rerunning_a_day_loads_nothing_twice(sim):
    from saas_elt.pipeline import build_dag, load_contracts

    wh = sim.warehouse
    before = {t: wh.query(f"SELECT COUNT(*) FROM raw_{t}")[0][0]
              for t in ("crm_accounts", "crm_subscriptions", "billing_invoices", "product_events")}
    mrr_before = wh.query("SELECT SUM(mrr_eur) FROM fct_mrr_daily")[0][0]
    dag = build_dag(sim.settings, sim.world, wh, load_contracts(), "2026-06-30")
    run = dag.run(wh, "2026-09-30", {})
    assert run.status == "success"
    after = {t: wh.query(f"SELECT COUNT(*) FROM raw_{t}")[0][0] for t in before}
    assert after == before
    assert wh.query("SELECT SUM(mrr_eur) FROM fct_mrr_daily")[0][0] == mrr_before


def test_erasure_removes_an_account_everywhere(sim, tmp_path):
    copy = tmp_path / "wh_copy.db"
    shutil.copy(sim.settings.warehouse_db, copy)
    wh = Warehouse(copy)
    tables = [r[0] for r in wh.query("SELECT name FROM sqlite_master WHERE type='table'")]
    n = wh.erase_account("ACC-00018", "DSR-TEST")
    assert n > 0
    for t in tables:
        cols = [c[1] for c in wh.query(f"PRAGMA table_info({t})")]
        if "account_id" in cols:
            assert wh.query(f"SELECT COUNT(*) FROM {t} WHERE account_id='ACC-00018'")[0][0] == 0
    log = wh.query("SELECT subject_hash FROM meta_erasure_log")[0][0]
    assert "ACC-00018" not in log and len(log) == 64
