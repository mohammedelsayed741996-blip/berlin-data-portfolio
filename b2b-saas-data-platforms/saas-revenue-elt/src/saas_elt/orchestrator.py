"""A minimal DAG orchestrator with retries, run logging and failure isolation.

It does what the job ad asks Airflow or Dagster to do here: run tasks in
dependency order, retry transient failures, stop downstream tasks when an
upstream one fails, and keep a log that tells you which run failed, where,
and why. Every attempt is written to ``meta_task_runs``.
"""

from __future__ import annotations

import logging
import time
import traceback
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

import networkx as nx

from .warehouse import Warehouse, now_utc

logger = logging.getLogger(__name__)


@dataclass
class Task:
    name: str
    fn: Callable[[dict], object]
    upstream: list[str] = field(default_factory=list)
    retries: int = 2


@dataclass
class TaskOutcome:
    task: str
    status: str  # success | failed | upstream_failed
    attempts: int
    result: object = None
    error: str = ""


@dataclass
class DagRun:
    run_id: str
    run_date: str
    outcomes: dict[str, TaskOutcome]

    @property
    def status(self) -> str:
        return "success" if all(o.status == "success" for o in self.outcomes.values()) else "failed"

    def failed_tasks(self) -> list[str]:
        return [t for t, o in self.outcomes.items() if o.status != "success"]


class DAG:
    """Tasks plus their dependencies."""

    def __init__(self, name: str, tasks: list[Task]) -> None:
        self.name = name
        self.tasks = {t.name: t for t in tasks}
        self.graph = nx.DiGraph()
        for t in tasks:
            self.graph.add_node(t.name)
            for up in t.upstream:
                if up not in self.tasks:
                    raise KeyError(f"Task {t.name} depends on unknown task {up}")
                self.graph.add_edge(up, t.name)
        if not nx.is_directed_acyclic_graph(self.graph):
            raise ValueError("Task graph has a cycle")

    def run(self, wh: Warehouse, run_date: str, context: dict, backoff_s: float = 0.0) -> DagRun:
        run_id = f"{self.name}-{run_date}-{uuid.uuid4().hex[:6]}"
        outcomes: dict[str, TaskOutcome] = {}
        ctx = dict(context, run_id=run_id, run_date=run_date, results={})
        for name in nx.topological_sort(self.graph):
            task = self.tasks[name]
            if any(outcomes[u].status != "success" for u in task.upstream):
                outcomes[name] = TaskOutcome(name, "upstream_failed", 0)
                wh.log_task(run_id=run_id, run_date=run_date, task=name, attempt=0, status="upstream_failed",
                            started_at=now_utc(), finished_at=now_utc(), duration_s=0.0, message="skipped")
                continue
            for attempt in range(1, task.retries + 2):
                started = now_utc()
                t0 = time.perf_counter()
                try:
                    result = task.fn(ctx)
                    ctx["results"][name] = result
                    outcomes[name] = TaskOutcome(name, "success", attempt, result)
                    wh.log_task(run_id=run_id, run_date=run_date, task=name, attempt=attempt, status="success",
                                started_at=started, finished_at=now_utc(),
                                duration_s=round(time.perf_counter() - t0, 3), message="")
                    break
                except Exception as exc:  # every failure is logged with its message
                    msg = f"{type(exc).__name__}: {exc}"
                    wh.log_task(run_id=run_id, run_date=run_date, task=name, attempt=attempt, status="failed",
                                started_at=started, finished_at=now_utc(),
                                duration_s=round(time.perf_counter() - t0, 3), message=msg[:500])
                    logger.warning("Task %s attempt %d failed: %s", name, attempt, msg)
                    if attempt > task.retries:
                        outcomes[name] = TaskOutcome(name, "failed", attempt, error=msg)
                        logger.debug(traceback.format_exc())
                    else:
                        time.sleep(backoff_s * 2 ** (attempt - 1))
        return DagRun(run_id, run_date, outcomes)
