"""Load the tables into SQLite and run the SQL checks in sql/."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

from . import config as C
from .world import road_km


def connect(tables: dict[str, pd.DataFrame]) -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    for name, df in tables.items():
        df.to_sql(name, con, index=False)
    seg = []
    for line, seq in C.LINES.items():
        for i in range(len(seq) - 1):
            seg.append({"line": line, "seq": i, "seg_km": road_km(seq[i], seq[i + 1])})
    pd.DataFrame(seg).to_sql("line_km", con, index=False)
    return con


def run(con: sqlite3.Connection, sql_file: Path, **params) -> pd.DataFrame:
    return pd.read_sql_query(sql_file.read_text(), con, params=params or None)
