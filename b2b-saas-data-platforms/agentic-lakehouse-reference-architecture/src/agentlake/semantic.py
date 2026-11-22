"""The semantic layer: the only way the agent reads the lakehouse.

The agent never writes SQL. It asks for a named metric, optional dimensions and filters from an
allow-list, and this module compiles that into parameterised SQL. Values are bound as parameters,
never pasted into the query, and the row-level security predicate for the user is added here, in
code, so no prompt can remove it (ADR 0001 and ADR 0002).

Locally the gold tables are loaded into SQLite; in AWS the same compiled SQL runs on Athena.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

METRICS = {
    "open_receivables": {"table": "account_ar", "expr": "SUM(open_eur)", "dims": ["account_id", "owner", "region", "segment"]},
    "overdue_receivables": {"table": "account_ar", "expr": "SUM(overdue_eur)", "dims": ["account_id", "owner", "region", "segment"]},
    "accounts": {"table": "account_ar", "expr": "COUNT(*)", "dims": ["owner", "region", "segment"]},
    "revenue": {"table": "revenue_monthly", "expr": "SUM(revenue_eur)", "dims": ["month", "account_id", "owner", "region", "category"]},
    "open_invoice_count": {"table": "open_invoices", "expr": "COUNT(*)", "dims": ["account_id", "owner", "region", "bucket"]},
    "open_invoice_amount": {"table": "open_invoices", "expr": "SUM(open_eur)", "dims": ["account_id", "owner", "region", "bucket"]},
}
# filters: column -> allowed operators
FILTERS = {
    "account_id": {"eq"}, "owner": {"eq"}, "region": {"eq"}, "segment": {"eq"}, "category": {"eq"},
    "bucket": {"eq"}, "month": {"eq", "gte", "lte"},
}
OPS = {"eq": "=", "gte": ">=", "lte": "<="}
ACCOUNT_COLUMNS = ["account_id", "name", "region", "segment", "owner", "payment_terms_days", "credit_limit_eur", "open_eur",
                   "overdue_eur", "oldest_days_past_due", "open_invoices", "credit_used_pct"]


class SemanticError(ValueError):
    """A request the semantic layer does not allow. The message is safe to show to the user."""


@dataclass
class Scope:
    """What rows a user may see. owner=None means all accounts."""
    user: str
    owner: str | None


class Warehouse:
    def __init__(self, gold_dir: Path):
        self.conn = sqlite3.connect(":memory:", check_same_thread=False)
        for f in sorted(gold_dir.glob("*.csv")):
            pd.read_csv(f).to_sql(f.stem, self.conn, index=False)
        self.queries: list[str] = []                    # compiled SQL, kept for tracing and review

    def run(self, sql: str, params: list) -> pd.DataFrame:
        self.queries.append(sql)
        return pd.read_sql_query(sql, self.conn, params=params)


def _rls(scope: Scope) -> tuple[str, list]:
    return ("owner = ?", [scope.owner]) if scope.owner else ("1 = 1", [])


def compile_metric(metric: str, group_by: list[str] | None, filters: list[dict] | None, scope: Scope,
                   limit: int = 20, order: str = "desc") -> tuple[str, list]:
    if metric not in METRICS:
        raise SemanticError(f"unknown metric '{metric}'; allowed: {', '.join(METRICS)}")
    m = METRICS[metric]
    group_by = group_by or []
    for d in group_by:
        if d not in m["dims"]:
            raise SemanticError(f"'{d}' is not a dimension of {metric}; allowed: {', '.join(m['dims'])}")
    where, params = [], []
    rls_sql, rls_params = _rls(scope)
    where.append(rls_sql)
    params += rls_params
    for f in filters or []:
        col, op, val = f.get("column"), f.get("op", "eq"), f.get("value")
        if col not in FILTERS or col not in m["dims"] + ["month"] or (col == "month" and "month" not in m["dims"]):
            raise SemanticError(f"cannot filter {metric} by '{col}'")
        if op not in FILTERS[col]:
            raise SemanticError(f"operator '{op}' not allowed on '{col}'")
        if not isinstance(val, (str, int, float)):
            raise SemanticError("filter values must be plain text or numbers")
        where.append(f"{col} {OPS[op]} ?")
        params.append(val)
    if order not in ("asc", "desc"):
        raise SemanticError("order must be asc or desc")
    select = ", ".join(group_by + [f"ROUND({m['expr']}, 2) AS value"])
    sql = f"SELECT {select} FROM {m['table']} WHERE {' AND '.join(where)}"
    if group_by:
        sql += f" GROUP BY {', '.join(group_by)} ORDER BY value {order.upper()} LIMIT {int(limit)}"
    return sql, params


def account_lookup(wh: Warehouse, scope: Scope, account_id: str | None = None, name: str | None = None) -> pd.DataFrame:
    """Find one account by id or (part of) its name, only among accounts the user may see."""
    rls_sql, params = _rls(scope)
    cols = ", ".join(ACCOUNT_COLUMNS)
    if account_id:
        return wh.run(f"SELECT {cols} FROM account_ar WHERE {rls_sql} AND account_id = ?", params + [account_id])
    if name:
        return wh.run(f"SELECT {cols} FROM account_ar WHERE {rls_sql} AND LOWER(name) LIKE ? ORDER BY name LIMIT 5",
                      params + [f"%{name.lower()}%"])
    raise SemanticError("give an account_id or a name")


def open_invoices(wh: Warehouse, scope: Scope, account_id: str, min_days_past_due: int = 1, limit: int = 20) -> pd.DataFrame:
    rls_sql, params = _rls(scope)
    return wh.run("SELECT invoice_id, account_id, due, open_eur, days_past_due, bucket FROM open_invoices "
                  f"WHERE {rls_sql} AND account_id = ? AND days_past_due >= ? ORDER BY days_past_due DESC LIMIT {int(limit)}",
                  params + [account_id, int(min_days_past_due)])


def list_accounts(wh: Warehouse, scope: Scope, over_limit_only: bool = False, min_days_past_due: int = 0,
                  sort_by: str = "overdue_eur", limit: int = 10) -> pd.DataFrame:
    if sort_by not in ("overdue_eur", "open_eur", "credit_used_pct", "oldest_days_past_due"):
        raise SemanticError("sort_by must be overdue_eur, open_eur, credit_used_pct or oldest_days_past_due")
    rls_sql, params = _rls(scope)
    where = [rls_sql, "oldest_days_past_due >= ?"]
    params = params + [int(min_days_past_due)]
    if over_limit_only:
        where.append("credit_used_pct > 1")
    return wh.run(f"SELECT account_id, name, owner, open_eur, overdue_eur, credit_used_pct, oldest_days_past_due FROM account_ar "
                  f"WHERE {' AND '.join(where)} ORDER BY {sort_by} DESC LIMIT {int(limit)}", params)
