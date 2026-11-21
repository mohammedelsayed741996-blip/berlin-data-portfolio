"""Store redacted questions and feedback: SQLite by default, PostgreSQL when DATABASE_URL points to one.

Only redacted text is ever written. Rows older than the retention period are deleted on start-up.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

RETENTION_DAYS = 90

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS queries (
        id {pk}, created_at DOUBLE PRECISION NOT NULL, session TEXT, role TEXT NOT NULL, question TEXT NOT NULL,
        redacted_types TEXT, answered BOOLEAN NOT NULL, confidence DOUBLE PRECISION, citations TEXT,
        engine TEXT, latency_ms DOUBLE PRECISION)""",
    """CREATE TABLE IF NOT EXISTS feedback (
        id {pk}, created_at DOUBLE PRECISION NOT NULL, query_id INTEGER NOT NULL, helpful BOOLEAN NOT NULL, comment TEXT)""",
]


class Store:
    def __init__(self, url: str):
        self.url = url
        if url.startswith("postgres"):
            import psycopg                                                    # installed in the Docker image
            self.conn = psycopg.connect(url, autocommit=True)
            self.ph, pk = "%s", "BIGSERIAL PRIMARY KEY"
        else:
            path = url.replace("sqlite:///", "")
            if path != ":memory:":
                Path(path).parent.mkdir(parents=True, exist_ok=True)
            self.conn = sqlite3.connect(path, check_same_thread=False)
            self.ph, pk = "?", "INTEGER PRIMARY KEY AUTOINCREMENT"
        for stmt in SCHEMA:
            self._exec(stmt.format(pk=pk))
        self.purge()

    def _exec(self, sql: str, params: tuple = ()):
        cur = self.conn.cursor()
        cur.execute(sql.replace("?", self.ph), params)
        if not self.url.startswith("postgres"):
            self.conn.commit()
        return cur

    def log_query(self, *, session: str, role: str, question: str, redacted_types: list[str], answered: bool,
                  confidence: float, citations: list[str], engine: str, latency_ms: float) -> int:
        sql = ("INSERT INTO queries (created_at, session, role, question, redacted_types, answered, confidence, citations, engine, latency_ms) "
               "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)")
        params = (time.time(), session[:64], role, question[:500], ",".join(redacted_types), answered, confidence,
                  ";".join(citations), engine, latency_ms)
        if self.url.startswith("postgres"):
            return int(self._exec(sql + " RETURNING id", params).fetchone()[0])
        return int(self._exec(sql, params).lastrowid)

    def add_feedback(self, query_id: int, helpful: bool, comment: str = "") -> None:
        self._exec("INSERT INTO feedback (created_at, query_id, helpful, comment) VALUES (?, ?, ?, ?)",
                   (time.time(), int(query_id), bool(helpful), (comment or "")[:500]))

    def stats(self) -> dict:
        q = self._exec("SELECT COUNT(*), AVG(CASE WHEN answered THEN 1.0 ELSE 0.0 END), AVG(latency_ms) FROM queries").fetchone()
        f = self._exec("SELECT COUNT(*), AVG(CASE WHEN helpful THEN 1.0 ELSE 0.0 END) FROM feedback").fetchone()
        top = self._exec("SELECT citations, COUNT(*) AS n FROM queries WHERE answered GROUP BY citations ORDER BY n DESC LIMIT 5").fetchall()
        return {"questions": int(q[0] or 0), "answered_share": float(q[1] or 0), "avg_latency_ms": float(q[2] or 0),
                "feedback": int(f[0] or 0), "helpful_share": float(f[1] or 0), "top_citations": [{"citations": c, "n": int(n)} for c, n in top]}

    def purge(self, days: int = RETENTION_DAYS) -> None:
        cutoff = time.time() - days * 86400
        self._exec("DELETE FROM feedback WHERE created_at < ?", (cutoff,))
        self._exec("DELETE FROM queries WHERE created_at < ?", (cutoff,))
