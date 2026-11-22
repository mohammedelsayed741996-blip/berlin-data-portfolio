"""HTTP API for the agent (Starlette). In AWS it runs behind API Gateway on Lambda or ECS (see infra/).

Identity: X-User-Id and X-User-Role are set by the authoriser in front of the service (Cognito or the
customer's identity provider through API Gateway). The request body cannot change them.

    GET  /health
    POST /api/agent                    {"question": "..."}  -> answer, tool calls, approvals, trace id
    GET  /api/approvals                pending requests the caller may decide on
    POST /api/approvals/{id}           {"approve": true|false}
    GET  /api/traces/{trace_id}        spans of one run (Finance and Head of Finance only)
"""

from __future__ import annotations

import json
import os

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from .agent import Agent
from .approvals import ApprovalError
from .config import ROLES, Settings
from .tools import User


def create_app(settings: Settings | None = None) -> Starlette:
    agent = Agent(settings)

    def who(request: Request) -> User | None:
        uid, role = request.headers.get("x-user-id", ""), request.headers.get("x-user-role", "")
        return User(uid, role) if uid and role in ROLES else None

    async def body(request: Request) -> dict | None:
        raw = await request.body()
        if len(raw) > 4000:
            return None
        try:
            d = json.loads(raw or b"{}")
            return d if isinstance(d, dict) else None
        except ValueError:
            return None

    async def health(request):
        return JSONResponse({"status": "ok", "planner": agent.s.planner, "tables": len(list((agent.s.lake_dir / "gold").glob("*.csv")))})

    async def ask(request):
        user = who(request)
        if not user:
            return JSONResponse({"error": "missing or unknown identity headers"}, status_code=401)
        b = await body(request)
        if not b or not isinstance(b.get("question"), str) or not b["question"].strip():
            return JSONResponse({"error": "send JSON with a 'question'"}, status_code=400)
        r = agent.run(b["question"], user, export=True)
        return JSONResponse({"answer": r.answer, "tool_calls": r.calls, "approvals": r.approvals, "trace_id": r.trace_id,
                             "latency_ms": round(r.latency_ms, 1), "stopped": r.stopped})

    async def approvals(request):
        user = who(request)
        if not user:
            return JSONResponse({"error": "missing or unknown identity headers"}, status_code=401)
        items = agent.approvals.pending(user.user_id, user.role)
        return JSONResponse({"pending": [{"id": a.id, "kind": a.kind, "account_id": a.account_id, "requested_by": a.requested_by,
                                          "payload": a.payload} for a in items]})

    async def decide(request):
        user = who(request)
        if not user:
            return JSONResponse({"error": "missing or unknown identity headers"}, status_code=401)
        b = await body(request)
        if not b or not isinstance(b.get("approve"), bool):
            return JSONResponse({"error": "send JSON with a boolean 'approve'"}, status_code=400)
        try:
            a = agent.approvals.decide(int(request.path_params["id"]), user.user_id, user.role, b["approve"])
        except ApprovalError as e:
            return JSONResponse({"error": str(e)}, status_code=403)
        return JSONResponse({"id": a.id, "status": a.status, "decided_by": a.decided_by})

    async def trace(request):
        user = who(request)
        if not user or user.role not in ("finance", "head_of_finance"):
            return JSONResponse({"error": "Finance role required"}, status_code=403)
        tid = request.path_params["trace_id"]
        if not tid.isalnum():
            return JSONResponse({"error": "bad trace id"}, status_code=400)
        path = agent.s.trace_dir / f"{tid}.jsonl"
        if not path.exists():
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse({"spans": [json.loads(line) for line in path.read_text().splitlines()]})

    app = Starlette(routes=[Route("/health", health), Route("/api/agent", ask, methods=["POST"]),
                            Route("/api/approvals", approvals), Route("/api/approvals/{id:int}", decide, methods=["POST"]),
                            Route("/api/traces/{trace_id}", trace)])
    app.state.agent = agent
    return app


def main():
    import uvicorn

    uvicorn.run(create_app(), host="0.0.0.0", port=int(os.getenv("PORT", "8000")))


if __name__ == "__main__":
    main()
