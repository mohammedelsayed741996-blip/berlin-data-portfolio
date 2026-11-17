"""Portfolio monitoring: runs the SQL in ``sql/`` against an in-memory SQLite copy.

SQLite keeps the project dependency-free; the queries use standard window
functions and FILTER clauses, so they port to Snowflake or Postgres with
only the date functions changed.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

from . import config
from .data_generator import LoanBook


class PortfolioDB:
    """Loads the loan book into SQLite and runs the named monitoring queries."""

    def __init__(self, book: LoanBook, sql_dir: Path = config.SQL_DIR) -> None:
        self.sql_dir = sql_dir
        self.conn = sqlite3.connect(":memory:")
        for name, frame in (("installers", book.installers), ("loans", book.loans), ("performance", book.performance)):
            out = frame.copy()
            for col in out.select_dtypes(include=["datetime", "datetimetz"]).columns:
                out[col] = out[col].dt.strftime("%Y-%m-%d")
            out.to_sql(name, self.conn, index=False)
        self.conn.execute("CREATE INDEX ix_perf_loan ON performance(loan_id, months_on_book)")
        self.conn.execute("CREATE INDEX ix_perf_date ON performance(as_of_date)")
        self.conn.execute("CREATE UNIQUE INDEX ix_loans_id ON loans(loan_id)")
        self.conn.execute("CREATE UNIQUE INDEX ix_inst_id ON installers(installer_id)")

    def queries(self) -> list[str]:
        return sorted(p.stem for p in self.sql_dir.glob("*.sql"))

    def run(self, name: str) -> pd.DataFrame:
        """Run ``sql/<name>.sql`` and return the result."""
        path = self.sql_dir / f"{name}.sql"
        if not path.exists():
            raise FileNotFoundError(f"No query named {name!r} in {self.sql_dir}")
        return pd.read_sql_query(path.read_text(encoding="utf-8"), self.conn)

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "PortfolioDB":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def herfindahl_index(shares: pd.Series) -> float:
    """HHI on a 0-10,000 scale. Above 1,500 is usually read as concentrated."""
    return float(round((shares.fillna(0) ** 2).sum() * 10_000, 1))


def roll_rate_matrix(roll_rates: pd.DataFrame) -> pd.DataFrame:
    """Pivot the long roll-rate table into a from x to matrix."""
    return roll_rates.pivot(index="from_bucket", columns="to_bucket", values="roll_rate").fillna(0.0)
