"""AWS Lambda entry point behind an API Gateway HTTP API (payload format 2.0).

Identity comes from the JWT authoriser's claims, never from the request body. The lakehouse is read
from the gold layer packaged with the function or synced from S3 at cold start; in a larger setup the
semantic layer would send its compiled SQL to Athena instead (ADR 0005).
"""

from __future__ import annotations

import json

from .agent import Agent
from .config import ROLES
from .tools import User

_agent: Agent | None = None


def handler(event, context):
    global _agent
    if _agent is None:
        _agent = Agent()
    claims = event.get("requestContext", {}).get("authorizer", {}).get("jwt", {}).get("claims", {})
    user = User(claims.get("sub", ""), claims.get("custom:role", ""))
    if not user.user_id or user.role not in ROLES:
        return {"statusCode": 401, "body": json.dumps({"error": "unauthorised"})}
    try:
        question = json.loads(event.get("body") or "{}").get("question", "")
    except ValueError:
        question = ""
    if not isinstance(question, str) or not question.strip():
        return {"statusCode": 400, "body": json.dumps({"error": "send JSON with a 'question'"})}
    r = _agent.run(question[:500], user, export=False)
    for s in _agent.tracer.spans:                          # one structured log line per span goes to CloudWatch
        print(json.dumps({"trace_id": s.trace_id, "span": s.name, "ms": round(s.ms, 2), "status": s.status, **s.attributes}, default=str))
    return {"statusCode": 200, "headers": {"content-type": "application/json"},
            "body": json.dumps({"answer": r.answer, "approvals": r.approvals, "trace_id": r.trace_id})}
