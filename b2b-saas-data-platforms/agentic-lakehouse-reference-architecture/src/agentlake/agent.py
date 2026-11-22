"""The agent loop: plan, check, call, observe, repeat, with a span for every step.

The loop is identical for every planner. It stops at the step budget, records every guard
decision, and reports what happened: tool calls, blocked calls, approval requests, tokens,
estimated cost and latency.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from .approvals import ApprovalQueue
from .config import Settings
from .docsearch import DocSearch
from .planners import Call, Final, Observation, RulePlanner
from .semantic import Warehouse
from .tools import Toolbox, User
from .tracing import Tracer


@dataclass
class RunResult:
    question: str
    user: str
    role: str
    answer: str
    calls: list[dict] = field(default_factory=list)
    approvals: list[int] = field(default_factory=list)
    trace_id: str = ""
    latency_ms: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_eur: float = 0.0
    stopped: str = "final"

    @property
    def blocked(self) -> list[str]:
        return [c["blocked"] for c in self.calls if c["blocked"]]


class Agent:
    def __init__(self, settings: Settings | None = None, approvals: ApprovalQueue | None = None, tracer: Tracer | None = None):
        self.s = settings or Settings()
        self.wh = Warehouse(self.s.lake_dir / "gold")
        self.docs = DocSearch(self.s.docs_dir)
        self.approvals = approvals or ApprovalQueue()
        self.tools = Toolbox(self.wh, self.docs, self.approvals, self.s.max_rows)
        self.tracer = tracer or Tracer(self.s.trace_dir)

    def make_planner(self):
        if self.s.planner == "bedrock":
            from .planners import BedrockPlanner, make_bedrock_client

            return BedrockPlanner(make_bedrock_client(self.s.aws_region), self.s.bedrock_model_id)
        return RulePlanner()

    def run(self, question: str, user: User, planner=None, export: bool = False) -> RunResult:
        planner = planner or self.make_planner()
        t0 = time.perf_counter()
        trace_id = self.tracer.new_trace()
        history: list[Observation] = []
        res = RunResult(question[:500], user.user_id, user.role, "", trace_id=trace_id)
        with self.tracer.span("agent.run", user=user.user_id, role=user.role, planner=planner.name, question_chars=len(question)) as root:
            step = 0
            while True:
                with self.tracer.span("planner.next", step=step):
                    decision = planner.next(question[:500], history)
                if isinstance(decision, Final):
                    res.answer = decision.text
                    break
                call: Call = decision
                with self.tracer.span("tool.call", tool=call.name, args=_mask(call.args), step=step) as sp:
                    r = self.tools.call(user, call.name, call.args, step, self.s.max_steps)
                    sp.attributes.update({"allowed": r.blocked is None, "blocked_by": r.blocked, "rows": r.rows})
                    if r.blocked:
                        sp.status = "BLOCKED"
                res.calls.append({"tool": call.name, "args": call.args, "blocked": r.blocked, "rows": r.rows})
                if r.ok and isinstance(r.data, dict) and "approval_id" in r.data:
                    res.approvals.append(r.data["approval_id"])
                history.append(Observation(call, r.ok, r.data, r.blocked))
                step += 1
                if r.blocked == "step_budget" or step > self.s.max_steps:
                    res.answer = "I stopped because the request needed too many steps. Please ask a narrower question."
                    res.stopped = "step_budget"
                    break
            res.input_tokens, res.output_tokens = planner.usage.input_tokens, planner.usage.output_tokens
            res.cost_eur = (res.input_tokens * self.s.cost_in_per_1k + res.output_tokens * self.s.cost_out_per_1k) / 1000
            root.attributes.update({"tool_calls": len(res.calls), "blocked": len(res.blocked), "approvals": len(res.approvals),
                                    "input_tokens": res.input_tokens, "output_tokens": res.output_tokens, "stopped": res.stopped})
        res.latency_ms = (time.perf_counter() - t0) * 1000
        if export:
            self.tracer.export()
        return res


def _mask(args: dict) -> dict:
    """Keep traces free of free text that may contain personal data: long strings are truncated."""
    return {k: (v[:40] + "…" if isinstance(v, str) and len(v) > 40 else v) for k, v in args.items()}
