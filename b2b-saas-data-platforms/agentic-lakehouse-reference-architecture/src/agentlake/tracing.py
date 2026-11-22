"""Minimal tracing in the shape of OpenTelemetry spans, exported as JSON lines.

Every agent run is one trace. Planner calls, guard decisions and tool calls are child spans with
attributes: tool name, arguments (with personal data masked), rows returned, tokens and estimated
cost, and the guard's verdict. The JSON lines can be shipped to any OTLP-compatible backend
(CloudWatch, Grafana Tempo, Langfuse, Arize Phoenix); here they feed the evaluation and the charts.
"""

from __future__ import annotations

import json
import secrets
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class Span:
    trace_id: str
    span_id: str
    parent_id: str | None
    name: str
    start_ns: int
    end_ns: int = 0
    status: str = "OK"
    attributes: dict = field(default_factory=dict)

    @property
    def ms(self) -> float:
        return (self.end_ns - self.start_ns) / 1e6


class Tracer:
    def __init__(self, export_dir: Path | None = None):
        self.export_dir = export_dir
        self.spans: list[Span] = []
        self._stack: list[Span] = []
        self.trace_id = ""

    def new_trace(self) -> str:
        self.trace_id = secrets.token_hex(16)
        self.spans, self._stack = [], []
        return self.trace_id

    @contextmanager
    def span(self, name: str, **attributes):
        s = Span(self.trace_id, secrets.token_hex(8), self._stack[-1].span_id if self._stack else None, name,
                 time.perf_counter_ns(), attributes=dict(attributes))
        self._stack.append(s)
        try:
            yield s
        except Exception as e:
            s.status = "ERROR"
            s.attributes["error"] = type(e).__name__
            raise
        finally:
            s.end_ns = time.perf_counter_ns()
            self._stack.pop()
            self.spans.append(s)

    def export(self) -> Path | None:
        if not self.export_dir:
            return None
        self.export_dir.mkdir(parents=True, exist_ok=True)
        path = self.export_dir / f"{self.trace_id}.jsonl"
        with open(path, "w") as f:
            for s in sorted(self.spans, key=lambda x: x.start_ns):
                f.write(json.dumps({**asdict(s), "duration_ms": round(s.ms, 3)}, default=str) + "\n")
        return path
