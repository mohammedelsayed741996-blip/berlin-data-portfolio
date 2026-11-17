"""Copy the raw landing tables from the SQLite warehouse into DuckDB.

Used by the CI job that runs the real dbt (dbt-duckdb) against the same
models: the Python loaders fill SQLite, this script moves raw.* across with
explicit column types, and `dbt build` then has to pass on a second engine.

Usage: python scripts/export_raw_to_duckdb.py <warehouse.db> <target.duckdb>
"""

from __future__ import annotations

import csv
import sqlite3
import sys
import tempfile
from pathlib import Path

import duckdb

TABLES = ("crm_accounts", "crm_subscriptions", "billing_invoices", "product_events")
TYPE_MAP = {"TEXT": "VARCHAR", "INTEGER": "BIGINT", "REAL": "DOUBLE"}


def export_table(src: sqlite3.Connection, dst: duckdb.DuckDBPyConnection, table: str, tmp: Path) -> int:
    cols = [(c[1], TYPE_MAP.get(c[2].upper(), "VARCHAR")) for c in src.execute(f"PRAGMA table_info(raw_{table})")]
    path = tmp / f"{table}.csv"
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow([c for c, _ in cols])
        for row in src.execute(f"SELECT * FROM raw_{table}"):
            writer.writerow(["" if v is None else v for v in row])
    ddl = ", ".join(f'"{c}" {t}' for c, t in cols)
    dst.execute(f"CREATE OR REPLACE TABLE raw.{table} ({ddl})")
    dst.execute(f"COPY raw.{table} FROM '{path.as_posix()}' (HEADER true, NULLSTR '')")
    return dst.execute(f"SELECT COUNT(*) FROM raw.{table}").fetchone()[0]


def main(src_path: str, dst_path: str) -> None:
    src = sqlite3.connect(src_path)
    dst = duckdb.connect(dst_path)
    dst.execute("CREATE SCHEMA IF NOT EXISTS raw")
    with tempfile.TemporaryDirectory() as tmp:
        for table in TABLES:
            expected = src.execute(f"SELECT COUNT(*) FROM raw_{table}").fetchone()[0]
            n = export_table(src, dst, table, Path(tmp))
            if n != expected:
                raise RuntimeError(f"raw.{table}: copied {n} rows, expected {expected}")
            print(f"raw.{table}: {n} rows")
    dst.close()
    src.close()


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    try:
        main(sys.argv[1], sys.argv[2])
    except Exception as exc:
        print(f"::error::export failed: {type(exc).__name__}: {exc}")
        raise
