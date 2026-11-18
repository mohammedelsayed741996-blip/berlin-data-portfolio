"""Fiscal calendar helpers (fiscal year July to June)."""

from __future__ import annotations

import datetime as dt

import pandas as pd


def month_range(first: str, last: str) -> list[str]:
    return [p.strftime("%Y-%m") for p in pd.period_range(first, last, freq="M")]


def fiscal_year(month: str) -> str:
    """'2026-09' -> '2026/27'."""
    y, m = int(month[:4]), int(month[5:7])
    start = y if m >= 7 else y - 1
    return f"{start}/{str(start + 1)[2:]}"


def fiscal_period(month: str) -> int:
    """July is period 1, June is period 12."""
    m = int(month[5:7])
    return (m - 7) % 12 + 1


def fiscal_months(fy: str) -> list[str]:
    start = int(fy[:4])
    return month_range(f"{start}-07", f"{start + 1}-06")


def fy_index(month_or_fy: str) -> int:
    """0 for FY 2024/25, 1 for 2025/26, 2 for 2026/27."""
    fy = month_or_fy if "/" in month_or_fy else fiscal_year(month_or_fy)
    return int(fy[:4]) - 2024


def month_end(month: str) -> dt.date:
    return (pd.Period(month, freq="M").end_time).date()


def working_day(month_after: str, n: int) -> dt.date:
    """The n-th working day (Mon-Fri) of a month."""
    day = pd.Period(month_after, freq="M").start_time.date()
    count = 0
    while True:
        if day.weekday() < 5:
            count += 1
            if count == n:
                return day
        day += dt.timedelta(days=1)


def next_month(month: str) -> str:
    return (pd.Period(month, freq="M") + 1).strftime("%Y-%m")


def cutoff_date(month: str, working_days: int) -> dt.date:
    """Last allowed entry date for postings into `month`."""
    return working_day(next_month(month), working_days)
