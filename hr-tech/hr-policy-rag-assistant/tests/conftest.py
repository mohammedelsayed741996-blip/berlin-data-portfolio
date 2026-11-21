import asyncio
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hrrag.corpus import load  # noqa: E402
from hrrag.retrieval import Retriever  # noqa: E402


@pytest.fixture(scope="session")
def passages():
    return load(ROOT / "policies")


@pytest.fixture(scope="session")
def retriever(passages):
    return Retriever(passages)


class ASGIClient:
    """Minimal test client: calls the ASGI app directly, no network and no extra packages."""

    def __init__(self, app):
        self.app = app

    def request(self, method, path, body=None, headers=None, query=""):
        data = json.dumps(body).encode() if body is not None and not isinstance(body, bytes) else (body or b"")
        msgs, sent = [], False

        async def receive():
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": data, "more_body": False}
            return {"type": "http.disconnect"}

        async def send(m):
            msgs.append(m)

        hdrs = [(b"content-type", b"application/json")] + [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
        scope = {"type": "http", "method": method, "path": path, "query_string": query.encode(), "headers": hdrs,
                 "http_version": "1.1", "scheme": "http", "server": ("test", 80), "client": ("127.0.0.1", 1), "root_path": ""}
        asyncio.run(self.app(scope, receive, send))
        status = next(m["status"] for m in msgs if m["type"] == "http.response.start")
        raw = b"".join(m.get("body", b"") for m in msgs if m["type"] == "http.response.body")
        try:
            return status, json.loads(raw)
        except ValueError:
            return status, raw


@pytest.fixture()
def client(tmp_path):
    from hrrag.api import create_app
    from hrrag.config import Settings

    return ASGIClient(create_app(Settings(database_url=f"sqlite:///{tmp_path / 'test.db'}")))
