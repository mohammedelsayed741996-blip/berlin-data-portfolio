"""Load the tables into SQLite and run the SQL in sql/ (the same checks an MI analyst would schedule)."""

from __future__ import annotations

import sqlite3

import pandas as pd

from . import config as C


def connect(tables: dict) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    for name in ["transactions", "tm_feed_ids", "alerts", "clients"]:
        tables[name].to_sql(name, conn, index=False)
    conn.execute("CREATE INDEX ix_feed ON tm_feed_ids(tx_id)")
    return conn


def run_sql(conn, name: str, as_of: str = C.END) -> pd.DataFrame:
    sql = (C.Paths().sql / name).read_text()
    params = {"as_of": as_of} if ":as_of" in sql else {}
    return pd.read_sql_query(sql, conn, params=params)
