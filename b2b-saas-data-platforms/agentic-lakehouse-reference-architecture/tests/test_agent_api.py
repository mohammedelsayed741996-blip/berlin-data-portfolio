import copy

from agentlake.approvals import ApprovalError
from agentlake.planners import BedrockPlanner, RulePlanner
from agentlake.tools import User

AM, FIN, HOF = User("AM01", "account_manager"), User("FIN01", "finance"), User("HOF01", "head_of_finance")


def test_reminder_creates_pending_approval_and_sends_nothing(agent):
    r = agent.run("Draft a payment reminder for A001", AM)
    assert r.approvals and agent.approvals.items[r.approvals[0]].status == "pending"
    assert "Nothing has been sent" in r.answer


def test_four_eyes_on_credit_hold(agent):
    r = agent.run("Put A001 on credit hold", FIN)
    aid = r.approvals[0]
    try:
        agent.approvals.decide(aid, "FIN01", "finance", True)
        raise AssertionError("finance must not approve a hold")
    except ApprovalError:
        pass
    assert agent.approvals.decide(aid, "HOF01", "head_of_finance", True).status == "approved"


def test_injected_document_is_ignored(agent):
    r = agent.run("Show the email received with an unusual request in the archive", AM)
    assert "collector.example" not in r.answer and not r.approvals


def test_trace_has_a_span_per_step(agent):
    r = agent.run("Which invoices of A001 are overdue?", AM, export=True)
    names = [s.name for s in agent.tracer.spans]
    assert names.count("tool.call") == 2 and names.count("agent.run") == 1
    assert (agent.s.trace_dir / f"{r.trace_id}.jsonl").exists()


class StubBedrock:
    """Plays back Converse API responses: one tool call, then a final answer."""

    def __init__(self):
        self.calls = []

    def converse(self, **kw):
        self.calls.append(copy.deepcopy(kw))             # the planner keeps appending to the same list
        if len(self.calls) == 1:
            return {"stopReason": "tool_use", "usage": {"inputTokens": 900, "outputTokens": 40},
                    "output": {"message": {"role": "assistant", "content": [
                        {"toolUse": {"toolUseId": "t1", "name": "get_account", "input": {"account_id": "A001"}}}]}}}
        return {"stopReason": "end_turn", "usage": {"inputTokens": 1300, "outputTokens": 60},
                "output": {"message": {"role": "assistant", "content": [{"text": "A001 has open invoices."}]}}}


def test_bedrock_planner_round_trip(agent):
    stub = StubBedrock()
    r = agent.run("How much does A001 owe?", AM, planner=BedrockPlanner(stub, "anthropic.claude-test"))
    assert r.answer == "A001 has open invoices." and [c["tool"] for c in r.calls] == ["get_account"]
    second = stub.calls[1]["messages"]
    assert second[-1]["content"][0]["toolResult"]["toolUseId"] == "t1"
    assert "toolConfig" in stub.calls[0] and r.input_tokens == 2200 and r.cost_eur > 0


def test_bedrock_planner_cannot_bypass_the_guard(agent):
    class Evil(StubBedrock):
        def converse(self, **kw):
            self.calls.append(kw)
            if len(self.calls) == 1:
                return {"stopReason": "tool_use", "usage": {}, "output": {"message": {"role": "assistant", "content": [
                    {"toolUse": {"toolUseId": "x", "name": "send_email", "input": {"to": "audit-team@collector.example"}}}]}}}
            return {"stopReason": "end_turn", "usage": {}, "output": {"message": {"role": "assistant", "content": [{"text": "ok"}]}}}
    r = agent.run("follow the email", AM, planner=BedrockPlanner(Evil(), "m"))
    assert r.blocked == ["unknown_tool"]


def test_api_end_to_end(lake, tmp_path):
    from agentlake.api import create_app
    from agentlake.config import Settings
    from conftest import ASGIClient

    c = ASGIClient(create_app(Settings(lake_dir=lake[0], trace_dir=tmp_path / "t")))
    am = {"X-User-Id": "AM01", "X-User-Role": "account_manager"}
    assert c.request("GET", "/health")[0] == 200
    assert c.request("POST", "/api/agent", {"question": "hi"})[0] == 401
    st, out = c.request("POST", "/api/agent", {"question": "Draft a payment reminder for A001"}, am)
    assert st == 200 and out["approvals"]
    st, pend = c.request("GET", "/api/approvals", headers=am)
    assert [p["id"] for p in pend["pending"]] == out["approvals"]
    assert c.request("POST", f"/api/approvals/{out['approvals'][0]}", {"approve": True}, {"X-User-Id": "AM02", "X-User-Role": "account_manager"})[0] == 403
    assert c.request("POST", f"/api/approvals/{out['approvals'][0]}", {"approve": True}, am)[1]["status"] == "approved"
    assert c.request("GET", f"/api/traces/{out['trace_id']}", headers=am)[0] == 403
    st, tr = c.request("GET", f"/api/traces/{out['trace_id']}", headers={"X-User-Id": "FIN01", "X-User-Role": "finance"})
    assert st == 200 and any(s["name"] == "tool.call" for s in tr["spans"])


def test_lambda_handler(lake, monkeypatch):
    import json
    monkeypatch.setenv("LAKE_DIR", str(lake[0]))
    from agentlake import lambda_handler as L
    L._agent = None
    ev = {"requestContext": {"authorizer": {"jwt": {"claims": {"sub": "AM01", "custom:role": "account_manager"}}}},
          "body": json.dumps({"question": "What is the open balance of A001?"})}
    out = L.handler(ev, None)
    assert out["statusCode"] == 200 and "A001" in json.loads(out["body"])["answer"]
    assert L.handler({"body": "{}"}, None)["statusCode"] == 401


def test_rule_planner_is_deterministic():
    p = RulePlanner()
    assert p.intent("Put A001 on credit hold") == "hold" and p.intent("Who can place a credit hold according to the policy?") == "policy"
