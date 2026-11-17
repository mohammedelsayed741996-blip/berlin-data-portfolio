import sqlite3

import pytest

from saas_elt import config
from saas_elt.ingest import _call_with_retry, load_event_files
from saas_elt.contracts import load_contract
from saas_elt.minidbt import DbtProject
from saas_elt.orchestrator import DAG, Task
from saas_elt.simulator import TransientAPIError
from saas_elt.warehouse import Warehouse


def test_retry_gives_up_after_limit():
    calls = {"n": 0}

    def always_down():
        calls["n"] += 1
        raise TransientAPIError("503")

    with pytest.raises(TransientAPIError):
        _call_with_retry(always_down, retries=3)
    assert calls["n"] == 3


def test_retry_recovers():
    state = {"n": 0}

    def flaky():
        state["n"] += 1
        if state["n"] < 3:
            raise TransientAPIError("503")
        return "ok"

    assert _call_with_retry(flaky, retries=5) == "ok"


def test_orchestrator_retries_and_skips_downstream(tmp_path):
    wh = Warehouse(tmp_path / "wh.db")
    attempts = {"flaky": 0}

    def flaky(ctx):
        attempts["flaky"] += 1
        if attempts["flaky"] < 2:
            raise RuntimeError("blip")
        return 1

    def broken(ctx):
        raise RuntimeError("down")

    dag = DAG("t", [Task("a", flaky, retries=2), Task("b", broken, ["a"], retries=1),
                    Task("c", lambda ctx: 3, ["b"])])
    run = dag.run(wh, "2026-07-01", {})
    assert run.outcomes["a"].status == "success" and run.outcomes["a"].attempts == 2
    assert run.outcomes["b"].status == "failed" and run.outcomes["b"].attempts == 2
    assert run.outcomes["c"].status == "upstream_failed"
    assert run.status == "failed"
    logged = wh.query("SELECT COUNT(*) FROM meta_task_runs WHERE task='b' AND status='failed'")[0][0]
    assert logged == 2


def test_dag_rejects_unknown_dependency():
    with pytest.raises(KeyError):
        DAG("t", [Task("a", lambda c: 1, ["missing"])])


def test_dbt_project_parses_into_a_dag():
    conn = sqlite3.connect(":memory:")
    project = DbtProject(config.DBT_DIR, conn)
    g = project.graph()
    assert "fct_mrr_daily" in g and "int_subscription_versions" in g
    assert ("int_subscription_versions", "fct_mrr_daily") in g.edges
    assert project.nodes["fct_invoices"].config["materialized"] == "incremental"
    assert project.nodes["fct_invoices"].config["unique_key"] == "invoice_id"
    assert project.nodes["stg_crm__accounts"].config["materialized"] == "view"
    assert "raw_crm_subscriptions --> int_subscription_versions" in project.lineage_mermaid()


def test_generic_test_sql():
    name, sql, sev = DbtProject._test_sql({"relationships": {"to": "ref('dim_accounts')", "field": "account_id",
                                                             "config": {"severity": "warn"}}}, "fct_x", "account_id")
    assert sev == "warn" and "LEFT JOIN \"dim_accounts\"" in sql
    with pytest.raises(ValueError):
        DbtProject._test_sql("not_a_test", "m", "c")


def test_changed_event_file_is_reloaded(tmp_path):
    wh = Warehouse(tmp_path / "wh.db")
    contract = load_contract("product_events")
    drop = tmp_path / "drops"
    drop.mkdir()
    line = '{"account_id": "ACC-00001", "event_id": "EVT-%08d", "event_ts": "2026-07-01T10:00:00", "event_type": "login", "user_hash": "%s"}'
    f = drop / "events_2026-07-01.ndjson"
    f.write_text("\n".join(line % (i, "b" * 64) for i in range(3)) + "\n")
    s1 = load_event_files(wh, drop, contract, "2026-07-01")
    assert s1.loaded == 3
    f.write_text("\n".join(line % (i, "b" * 64) for i in range(5)) + "\n")  # re-delivered with more rows
    s2 = load_event_files(wh, drop, contract, "2026-07-02")
    assert s2.loaded == 5 and "reloaded" in s2.note
    assert wh.query("SELECT COUNT(*) FROM raw_product_events")[0][0] == 5
