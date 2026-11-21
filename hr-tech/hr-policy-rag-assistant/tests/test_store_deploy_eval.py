import os
import time
from pathlib import Path

import pytest
import yaml

from hrrag import evaluate as E
from hrrag.store import Store

ROOT = Path(__file__).resolve().parents[1]


def test_store_roundtrip_and_retention():
    s = Store("sqlite:///:memory:")
    qid = s.log_query(session="a", role="employee", question="q", redacted_types=[], answered=True, confidence=0.3,
                      citations=["HR-01#entitlement"], engine="extractive", latency_ms=1.0)
    s.add_feedback(qid, False, "wrong section")
    assert s.stats()["questions"] == 1 and s.stats()["helpful_share"] == 0.0
    s._exec("UPDATE queries SET created_at = ?", (time.time() - 100 * 86400,))
    s.purge()
    assert s.stats()["questions"] == 0


@pytest.mark.skipif(not os.getenv("DATABASE_URL", "").startswith("postgres"), reason="needs PostgreSQL (runs in CI)")
def test_postgres_store():
    s = Store(os.environ["DATABASE_URL"])
    qid = s.log_query(session="ci", role="employee", question="q", redacted_types=["NAME"], answered=False, confidence=0.1,
                      citations=[], engine="extractive", latency_ms=2.0)
    s.add_feedback(qid, True)
    assert s.stats()["questions"] >= 1


def test_kubernetes_manifests_are_valid_yaml():
    kinds = set()
    for f in (ROOT / "deploy" / "k8s").glob("*.yaml"):
        for doc in yaml.safe_load_all(f.read_text()):
            assert {"apiVersion", "kind", "metadata"} <= set(doc)
            kinds.add(doc["kind"])
    assert {"Deployment", "Service", "ConfigMap", "HorizontalPodAutoscaler"} <= kinds


def test_gold_set_is_consistent(passages):
    by_id = {p.pid: p for p in passages}
    g = E.gold()
    assert len(g) >= 90 and set(g["split"]) == {"dev", "test"}
    for r in g.itertuples():
        if isinstance(r.expected, str):
            assert all(f.lower() in by_id[r.expected].text.lower() for f in r.must_include)


def test_quality_gate(passages):
    """The same gate CI enforces: on held-out questions, enough correct answers, refusals and zero leaks."""
    f = E.full(passages)
    t = f["test"]
    assert t["leaks"] == 0
    assert t["decline_rate_when_should"] >= 0.95
    assert t["hit_at_3"] >= 0.90
    assert t["answer_correct"] >= 0.65
