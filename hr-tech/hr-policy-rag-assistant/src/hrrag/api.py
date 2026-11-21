"""HTTP API and web UI (Starlette, served by uvicorn).

Endpoints
    GET  /health            liveness and readiness: passages loaded, answer engine
    GET  /api/policies      policies the current role may read
    POST /api/ask           {"question": ..., "session": ...} -> answer, citations, query_id
    POST /api/feedback      {"query_id": ..., "helpful": true/false, "comment": ...}
    GET  /api/stats         usage and feedback counts (HR role only)
    GET  /                  the web UI

Roles: in production the role comes from the X-User-Role header, set by the company's identity
proxy after single sign-on; the browser cannot choose it. With DEMO_MODE=true (the default for the
public demo) the request body may set the role, so visitors can see the access control at work.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from .answer import Assistant
from .config import ROLE_LEVEL, ROOT, Settings
from .corpus import load
from .privacy import redact
from .retrieval import Retriever, visible
from .store import Store

WEB = ROOT / "web"
MAX_BODY = 4000
RATE = {"window": 60.0, "max": 30}          # requests per session per minute


def create_app(settings: Settings | None = None) -> Starlette:
    s = settings or Settings()
    passages = load(s.policies_dir)
    assistant = Assistant(Retriever(passages, s.retriever), s)
    store = Store(s.database_url)
    demo = os.getenv("DEMO_MODE", "true").lower() == "true"
    hits: dict[str, list[float]] = {}

    def role_of(request: Request, body: dict | None = None) -> str:
        role = request.headers.get("x-user-role", "")
        if not role and demo and body:
            role = str(body.get("role", ""))
        return role if role in ROLE_LEVEL else "employee"

    def limited(session: str) -> bool:
        now = time.time()
        recent = [t for t in hits.get(session, []) if now - t < RATE["window"]]
        recent.append(now)
        hits[session] = recent
        return len(recent) > RATE["max"]

    async def read_json(request: Request) -> dict | None:
        raw = await request.body()
        if len(raw) > MAX_BODY:
            return None
        try:
            data = await request.json()
            return data if isinstance(data, dict) else None
        except Exception:
            return None

    async def health(request: Request):
        return JSONResponse({"status": "ok", "passages": len(passages), "engine": assistant.a.name, "demo_mode": demo})

    async def policies(request: Request):
        role = role_of(request, dict(request.query_params))
        seen = {}
        for i in visible(passages, role):
            p = passages[i]
            seen.setdefault(p.policy_id, {"policy_id": p.policy_id, "title": p.title, "version": p.version,
                                          "effective_date": p.effective_date, "sections": []})["sections"].append(p.section)
        return JSONResponse({"role": role, "policies": list(seen.values())})

    async def ask(request: Request):
        body = await read_json(request)
        if body is None or not isinstance(body.get("question"), str):
            return JSONResponse({"error": "send JSON with a 'question' string"}, status_code=400)
        session = str(body.get("session", "anonymous"))[:64]
        if limited(session):
            return JSONResponse({"error": "too many questions, please wait a minute"}, status_code=429)
        role = role_of(request, body)
        question, found = redact(body["question"][:500])
        a = assistant.ask(question, role=role)
        out = a.to_dict()
        out["role"] = role
        out["redacted"] = found
        if s.log_queries:
            out["query_id"] = store.log_query(session=session, role=role, question=question, redacted_types=found,
                                              answered=a.answered, confidence=a.confidence,
                                              citations=[c["pid"] for c in a.citations], engine=a.engine, latency_ms=a.latency_ms)
        return JSONResponse(out)

    async def feedback(request: Request):
        body = await read_json(request)
        if body is None or "query_id" not in body or not isinstance(body.get("helpful"), bool):
            return JSONResponse({"error": "send JSON with 'query_id' and a boolean 'helpful'"}, status_code=400)
        comment, _ = redact(str(body.get("comment", "")))
        store.add_feedback(int(body["query_id"]), body["helpful"], comment)
        return JSONResponse({"ok": True})

    async def stats(request: Request):
        if role_of(request, dict(request.query_params)) != "hr":
            return JSONResponse({"error": "HR role required"}, status_code=403)
        return JSONResponse(store.stats())

    async def index(request: Request):
        return FileResponse(WEB / "index.html")

    routes = [Route("/health", health), Route("/api/policies", policies), Route("/api/ask", ask, methods=["POST"]),
              Route("/api/feedback", feedback, methods=["POST"]), Route("/api/stats", stats), Route("/", index)]
    if (WEB / "dist").exists():
        routes.append(Mount("/static", StaticFiles(directory=WEB / "dist"), name="static"))
    app = Starlette(routes=routes)
    app.state.assistant, app.state.store = assistant, store
    return app


def main() -> None:
    import uvicorn

    uvicorn.run(create_app(), host=os.getenv("HOST", "0.0.0.0"), port=int(os.getenv("PORT", "8000")), log_level="info")


if __name__ == "__main__":
    main()
