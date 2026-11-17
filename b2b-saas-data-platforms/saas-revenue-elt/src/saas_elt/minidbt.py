"""A small runner for the dbt project in ``dbt_project/``.

It exists because this repo has to run anywhere, including a laptop or Colab
without a warehouse account. It reads the same files dbt reads (models with
Jinja, ``sources.yml``, ``schema.yml``, macros, seeds, singular tests) and
supports the parts of dbt this project uses:

* ``ref()``, ``source()``, ``var()``, ``config()``, ``this``, ``is_incremental()``, ``target``;
* materialisations: view, table (built in a temp table, then swapped), and
  incremental with ``unique_key`` (delete+insert);
* seeds from CSV;
* generic tests (unique, not_null, accepted_values, relationships) and
  singular tests, with ``severity: warn``.

CI also runs the real dbt (dbt-duckdb) on the same project, so the models
stay portable. Cross-database differences live in ``macros/cross_db.sql``.
"""

from __future__ import annotations

import csv
import logging
import re
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path

import networkx as nx
import yaml
from jinja2 import Environment, StrictUndefined

logger = logging.getLogger(__name__)


@dataclass
class Node:
    name: str
    path: Path
    kind: str  # "model" | "seed"
    sql: str = ""
    config: dict = field(default_factory=dict)
    refs: set[str] = field(default_factory=set)
    sources: set[tuple[str, str]] = field(default_factory=set)


@dataclass
class TestResult:
    name: str
    model: str
    status: str  # pass | fail | warn | error
    failures: int
    severity: str
    message: str = ""


@dataclass
class RunResult:
    node: str
    status: str
    rows: int | None
    seconds: float
    message: str = ""


class DbtProject:
    """Parses and runs a dbt project against a SQLite connection."""

    def __init__(self, project_dir: Path, conn: sqlite3.Connection, vars: dict | None = None) -> None:
        self.dir = project_dir
        self.conn = conn
        cfg = yaml.safe_load((project_dir / "dbt_project.yml").read_text(encoding="utf-8"))
        self.project_name = cfg["name"]
        self.vars = dict(cfg.get("vars", {}) or {})
        self.vars.update(vars or {})
        self.folder_config = (cfg.get("models", {}) or {}).get(self.project_name, {}) or {}
        self.macros = "\n".join(p.read_text(encoding="utf-8") for p in sorted((project_dir / "macros").glob("*.sql")))
        self.env = Environment(undefined=StrictUndefined, trim_blocks=False)
        self.nodes: dict[str, Node] = {}
        self.yaml_docs = [yaml.safe_load(p.read_text(encoding="utf-8")) or {}
                          for p in sorted((project_dir / "models").rglob("*.yml"))]
        self.source_tables = {
            (s["name"], t["name"]): t.get("identifier", f"{s['name']}_{t['name']}")
            for doc in self.yaml_docs for s in doc.get("sources", []) or [] for t in s.get("tables", [])
        }
        self._parse()

    # ------------------------------------------------------------ parsing
    def _folder_defaults(self, path: Path) -> dict:
        rel = path.relative_to(self.dir / "models").parts[:-1]
        out: dict = {}
        level = self.folder_config
        for part in rel:
            level = level.get(part, {}) if isinstance(level, dict) else {}
            out.update({k.lstrip("+"): v for k, v in level.items() if k.startswith("+")})
        return out

    def _context(self, node: Node, incremental: bool, collect: bool) -> dict:
        def ref(name: str) -> str:
            if collect:
                node.refs.add(name)
            return name

        def source(src: str, table: str) -> str:
            if (src, table) not in self.source_tables:
                raise KeyError(f"{node.name}: unknown source {src}.{table}")
            if collect:
                node.sources.add((src, table))
            return self.source_tables[(src, table)]

        def config(**kw) -> str:
            if collect:
                node.config.update(kw)
            return ""

        def var(name: str, default=None):
            if name in self.vars:
                return self.vars[name]
            if default is not None:
                return default
            raise KeyError(f"{node.name}: var {name!r} is not set")

        return {
            "ref": ref, "source": source, "config": config, "var": var,
            "is_incremental": lambda: incremental, "this": node.name,
            "target": {"type": "sqlite", "name": "local", "schema": "main"},
        }

    def render(self, node: Node, incremental: bool = False, collect: bool = False) -> str:
        template = self.env.from_string(self.macros + "\n" + node.sql)
        return template.render(**self._context(node, incremental, collect)).strip()

    def _parse(self) -> None:
        for path in sorted((self.dir / "seeds").glob("*.csv")):
            self.nodes[path.stem] = Node(path.stem, path, "seed")
        for path in sorted((self.dir / "models").rglob("*.sql")):
            node = Node(path.stem, path, "model", sql=path.read_text(encoding="utf-8"))
            node.config = {"materialized": "view", **self._folder_defaults(path)}
            self.render(node, collect=True)
            self.nodes[node.name] = node
        for n in self.nodes.values():
            missing = [r for r in n.refs if r not in self.nodes]
            if missing:
                raise KeyError(f"{n.name} refers to unknown nodes: {missing}")

    def graph(self) -> nx.DiGraph:
        g = nx.DiGraph()
        for n in self.nodes.values():
            g.add_node(n.name, kind=n.kind)
            for r in n.refs:
                g.add_edge(r, n.name)
        if not nx.is_directed_acyclic_graph(g):
            raise ValueError(f"Cycle in model graph: {nx.find_cycle(g)}")
        return g

    # ------------------------------------------------------------ execution
    def _exists(self, name: str) -> str | None:
        row = self.conn.execute("SELECT type FROM sqlite_master WHERE name=?", (name,)).fetchone()
        return row[0] if row else None

    def _drop(self, name: str) -> None:
        kind = self._exists(name)
        if kind in ("table", "view"):
            self.conn.execute(f'DROP {kind.upper()} "{name}"')

    def _load_seed(self, node: Node) -> int:
        with node.path.open(newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        cols = list(rows[0]) if rows else []
        self._drop(node.name)
        self.conn.execute(f'CREATE TABLE "{node.name}" ({", ".join(cols)})')

        def cast(v: str):
            try:
                return float(v) if re.fullmatch(r"-?\d+(\.\d+)?", v) else v
            except ValueError:
                return v

        self.conn.executemany(f'INSERT INTO "{node.name}" VALUES ({", ".join("?" for _ in cols)})',
                              [[cast(r[c]) for c in cols] for r in rows])
        return len(rows)

    def _materialise(self, node: Node, full_refresh: bool) -> int | None:
        mat = node.config.get("materialized", "view")
        name = node.name
        if mat == "view":
            self._drop(name)
            self.conn.execute(f'CREATE VIEW "{name}" AS {self.render(node)}')
            return None
        if mat == "table":
            tmp = f"{name}__tmp"
            self._drop(tmp)
            self.conn.execute(f'CREATE TABLE "{tmp}" AS {self.render(node)}')
            self._drop(name)
            self.conn.execute(f'ALTER TABLE "{tmp}" RENAME TO "{name}"')
            return self.conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
        if mat == "incremental":
            exists = self._exists(name) == "table"
            if not exists or full_refresh:
                self._drop(name)
                self.conn.execute(f'CREATE TABLE "{name}" AS {self.render(node, incremental=False)}')
            else:
                tmp = f"{name}__incr"
                self._drop(tmp)
                self.conn.execute(f'CREATE TEMP TABLE "{tmp}" AS {self.render(node, incremental=True)}')
                cols = [c[1] for c in self.conn.execute(f'PRAGMA table_info("{name}")')]
                key = node.config.get("unique_key")
                if key:
                    self.conn.execute(f'DELETE FROM "{name}" WHERE {key} IN (SELECT {key} FROM "{tmp}")')
                col_list = ", ".join(cols)
                self.conn.execute(f'INSERT INTO "{name}" ({col_list}) SELECT {col_list} FROM "{tmp}"')
                self.conn.execute(f'DROP TABLE "{tmp}"')
            return self.conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
        raise ValueError(f"{name}: materialisation {mat!r} is not supported")

    def run(self, full_refresh: bool = False, fail_on: set[str] | None = None) -> list[RunResult]:
        """Build seeds and models in dependency order. Stops at the first error."""
        results: list[RunResult] = []
        for name in nx.topological_sort(self.graph()):
            node = self.nodes[name]
            t0 = time.perf_counter()
            try:
                if fail_on and name in fail_on:
                    raise RuntimeError(f"simulated outage while building {name}")
                rows = self._load_seed(node) if node.kind == "seed" else self._materialise(node, full_refresh)
                self.conn.commit()
                results.append(RunResult(name, "success", rows, round(time.perf_counter() - t0, 3)))
            except Exception as exc:
                self.conn.rollback()
                results.append(RunResult(name, "error", None, round(time.perf_counter() - t0, 3), str(exc)))
                raise RuntimeError(f"model {name} failed: {exc}") from exc
        return results

    # ------------------------------------------------------------ tests
    @staticmethod
    def _test_sql(test: str | dict, model: str, column: str) -> tuple[str, str, str]:
        if isinstance(test, str):
            kind, args = test, {}
        else:
            kind, args = next(iter(test.items()))
            args = dict(args or {})
            args.update(args.pop("arguments", {}) or {})
        severity = (args.pop("config", {}) or {}).get("severity", args.pop("severity", "error"))
        if kind == "unique":
            sql = f'SELECT {column} FROM "{model}" WHERE {column} IS NOT NULL GROUP BY {column} HAVING COUNT(*) > 1'
        elif kind == "not_null":
            sql = f'SELECT {column} FROM "{model}" WHERE {column} IS NULL'
        elif kind == "accepted_values":
            vals = ", ".join("'" + str(v).replace("'", "''") + "'" for v in args["values"])
            sql = f'SELECT {column} FROM "{model}" WHERE {column} IS NOT NULL AND {column} NOT IN ({vals})'
        elif kind == "relationships":
            to = re.fullmatch(r"ref\(['\"](\w+)['\"]\)", args["to"].strip()).group(1)
            sql = (f'SELECT c.{column} FROM "{model}" c LEFT JOIN "{to}" p ON c.{column} = p.{args["field"]} '
                   f'WHERE c.{column} IS NOT NULL AND p.{args["field"]} IS NULL')
        else:
            raise ValueError(f"Unsupported generic test {kind!r}")
        return f"{kind}_{model}_{column}", sql, severity

    def test(self) -> list[TestResult]:
        """Run generic tests from schema.yml files and singular tests from tests/."""
        out: list[TestResult] = []
        for doc in self.yaml_docs:
            for model in doc.get("models", []) or []:
                for col in model.get("columns", []) or []:
                    for t in (col.get("data_tests") or col.get("tests") or []):
                        name, sql, sev = self._test_sql(t, model["name"], col["name"])
                        out.append(self._run_test(name, model["name"], sql, sev))
        for path in sorted((self.dir / "tests").glob("*.sql")):
            node = Node(path.stem, path, "test", sql=path.read_text(encoding="utf-8"))
            sql = self.render(node, collect=True)
            sev = node.config.get("severity", "error")
            out.append(self._run_test(path.stem, ",".join(sorted(node.refs)), sql, sev))
        return out

    def _run_test(self, name: str, model: str, sql: str, severity: str) -> TestResult:
        try:
            n = self.conn.execute(f"SELECT COUNT(*) FROM ({sql})").fetchone()[0]
        except sqlite3.Error as exc:
            return TestResult(name, model, "error", -1, severity, str(exc))
        status = "pass" if n == 0 else ("warn" if severity == "warn" else "fail")
        return TestResult(name, model, status, n, severity)

    # ------------------------------------------------------------ docs
    def lineage_mermaid(self) -> str:
        lines = ["flowchart LR"]
        for (src, table), ident in sorted(self.source_tables.items()):
            lines.append(f"    {ident}[({ident})]")
        for n in sorted(self.nodes.values(), key=lambda x: x.name):
            shape = f"{n.name}[/{n.name}/]" if n.kind == "seed" else f"{n.name}[{n.name}]"
            lines.append(f"    {shape}")
            for s in sorted(n.sources):
                lines.append(f"    {self.source_tables[s]} --> {n.name}")
            for r in sorted(n.refs):
                lines.append(f"    {r} --> {n.name}")
        return "\n".join(lines)
