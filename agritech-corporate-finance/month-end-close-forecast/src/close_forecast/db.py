"""Load the extract into SQLite and run the SQL files in sql/ (the same checks, in SQL)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

from . import config as C
from .fiscal import fiscal_period, fiscal_year, month_end


def connect(tables: dict[str, pd.DataFrame], path: str | Path = ":memory:") -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    for name, df in tables.items():
        df.to_sql(name, conn, index=False, if_exists="replace")
    conn.execute("CREATE INDEX IF NOT EXISTS ix_gl_month ON gl_items(month, company_code, gl_account)")
    return conn


def params(month: str = C.CLOSE_PERIOD) -> dict:
    return {"close_month": month, "fiscal_year": fiscal_year(month), "period": fiscal_period(month),
            "month_end": month_end(month).isoformat()}


def run_sql(conn: sqlite3.Connection, name: str, month: str = C.CLOSE_PERIOD) -> pd.DataFrame:
    sql = (C.Paths().sql / name).read_text()
    p = params(month)
    used = {k: v for k, v in p.items() if f":{k}" in sql}
    return pd.read_sql_query(sql, conn, params=used)
