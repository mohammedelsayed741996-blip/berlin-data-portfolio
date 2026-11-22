import pytest

from agentlake import semantic as S
from agentlake.planners import ATTACKS, HostilePlanner
from agentlake.tools import TOOLS, User, bedrock_tool_config

AM = User("AM01", "account_manager")


def test_semantic_layer_binds_values_and_adds_row_level_security():
    sql, params = S.compile_metric("open_receivables", ["account_id"], [{"column": "account_id", "value": "A001' OR '1'='1"}], S.Scope("AM01", "AM01"))
    assert "owner = ?" in sql and "A001' OR" not in sql and params == ["AM01", "A001' OR '1'='1"]


@pytest.mark.parametrize("metric,group,filters", [("passwords", [], []), ("open_receivables", ["contact_email"], []),
                                                  ("revenue", [], [{"column": "contact_email", "value": "x"}]),
                                                  ("open_receivables", [], [{"column": "owner", "op": "gte", "value": "A"}])])
def test_semantic_layer_rejects_anything_off_the_list(metric, group, filters):
    with pytest.raises(S.SemanticError):
        S.compile_metric(metric, group, filters, S.Scope("AM01", "AM01"))


def test_other_owners_account_looks_like_it_does_not_exist(agent):
    assert agent.tools.call(AM, "get_account", {"account_id": "A002"}).data == agent.tools.call(AM, "get_account", {"account_id": "A999"}).data


def test_every_attack_is_blocked_or_contained(agent):
    for name, script in ATTACKS.items():
        res = agent.run(name, AM, planner=HostilePlanner(list(script)))
        for c in res.calls:
            r = agent.tools.call(AM, c["tool"], c["args"])
            rows = r.data if isinstance(r.data, list) else []
            assert all(row.get("owner", "AM01") == "AM01" for row in rows if isinstance(row, dict)), name
    assert all(a.owner == "AM01" for a in agent.approvals.items.values())
    assert not any(a.kind == "credit_hold" for a in agent.approvals.items.values())


def test_step_budget_stops_runaway_loops(agent):
    res = agent.run("loop", AM, planner=HostilePlanner(ATTACKS["runaway loop"]))
    assert res.stopped == "step_budget" and len(res.calls) <= agent.s.max_steps + 1


def test_bedrock_tool_config_matches_tools():
    cfg = bedrock_tool_config()
    assert [t["toolSpec"]["name"] for t in cfg["tools"]] == list(TOOLS)
    assert all("json" in t["toolSpec"]["inputSchema"] for t in cfg["tools"])


def test_leak_detector_catches_a_broken_guard(agent, monkeypatch):
    """If row-level security were removed, the evaluation must notice."""
    from agentlake import evaluate as E
    monkeypatch.setattr(User, "scope", property(lambda self: S.Scope(self.user_id, None)))
    res = agent.run("x", AM, planner=HostilePlanner([ATTACKS["other owner's account by id"][0]]))
    assert E.leaks(res, AM, E.load_gold(agent), E._observed(agent, AM, res))
