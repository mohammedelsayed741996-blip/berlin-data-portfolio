"""Copy the raw landing tables from the SQLite warehouse into DuckDB.

Used by the CI job that runs the real dbt (dbt-duckdb) against the same
models: the Python loaders fill SQLite, this script moves raw.* across, and
`dbt build` then has to produce passing tests on a second engine.

Usage: python scripts/export_raw_to_duckdb.py <warehouse.db> <target.duckdb>
"""

from __future__ import annotations

import sqlite3
import sys

import duckdb
import pandas as pd

TABLES = ("crm_accounts", "crm_subscriptions", "billing_invoices", "product_events")


def main(src_path: str, dst_path: str) -> None:
    src = sqlite3.connect(src_path)
    dst = duckdb.connect(dst_path)
    dst.execute("CREATE SCHEMA IF NOT EXISTS raw")
    for table in TABLES:
        df = pd.read_sql_query(f"SELECT * FROM raw_{table}", src)
        # Keep text columns as text even when every value in them is NULL.
        for col in df.columns:
            if df[col].isna().all():
                df[col] = df[col].astype("string")
        dst.register("incoming", df)
        dst.execute(f"CREATE OR REPLACE TABLE raw.{table} AS SELECT * FROM incoming")
        dst.unregister("incoming")
        n = dst.execute(f"SELECT COUNT(*) FROM raw.{table}").fetchone()[0]
        print(f"raw.{table}: {n} rows")
    dst.close()
    src.close()


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
