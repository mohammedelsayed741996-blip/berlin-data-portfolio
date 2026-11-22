import asyncio
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agentlake import lakehouse  # noqa: E402
from agentlake.agent import Agent  # noqa: E402
from agentlake.config import Settings  # noqa: E402


@pytest.fixture(scope="session")
def lake(tmp_path_factory):
    """Build the whole lakehouse from scratch in a temporary folder, as CI does."""
    d = tmp_path_factory.mktemp("lake")
    out = lakehouse.build_all(d)
    return d, out


@pytest.fixture()
def agent(lake, tmp_path):
    return Agent(Settings(lake_dir=lake[0], trace_dir=tmp_path / "traces"))


class ASGIClient:
    def __init__(self, app):
        self.app = app

    def request(self, method, path, body=None, headers=None):
        data = json.dumps(body).encode() if body is not None else b""
        msgs, sent = [], False

        async def receive():
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": data, "more_body": False}
            await asyncio.Event().wait()

        async def send(m):
            msgs.append(m)

        hdrs = [(b"content-type", b"application/json")] + [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
        scope = {"type": "http", "method": method, "path": path, "query_string": b"", "headers": hdrs, "http_version": "1.1",
                 "scheme": "http", "server": ("t", 80), "client": ("c", 1), "root_path": ""}
        asyncio.run(self.app(scope, receive, send))
        status = next(m["status"] for m in msgs if m["type"] == "http.response.start")
        return status, json.loads(b"".join(m.get("body", b"") for m in msgs if m["type"] == "http.response.body"))
