"""Battery (BESS) day-ahead arbitrage value with perfect foresight, by dynamic programming.

A 1 MW / 2 MWh battery charges and discharges in 1 MW steps each hour. State of charge is 0, 1 or 2 MWh.
Round-trip efficiency is applied on discharge; a degradation cost is charged per MWh discharged.
Perfect foresight overstates what a trader earns, so results are also shown with a capture factor
(the share of the perfect-foresight value a real optimiser typically keeps).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

LEVELS = (0, 1, 2)


def optimise_day(prices: np.ndarray, eff: float = 0.88, degradation: float = 4.0, start_soc: int = 0) -> tuple[float, np.ndarray]:
    """Best revenue for one day and the action per hour (+1 charge, -1 discharge, 0 idle). Ends empty."""
    n = len(prices)
    value = np.full((n + 1, 3), -np.inf)
    value[n, 0] = 0.0
    choice = np.zeros((n, 3), dtype=int)
    for t in range(n - 1, -1, -1):
        for s in LEVELS:
            best, act = -np.inf, 0
            for a in (-1, 0, 1):
                s2 = s + a
                if s2 < 0 or s2 > 2:
                    continue
                cash = -prices[t] if a == 1 else (prices[t] * eff - degradation if a == -1 else 0.0)
                v = cash + value[t + 1, s2]
                if v > best:
                    best, act = v, a
            value[t, s], choice[t, s] = best, act
    actions, s = np.zeros(n, dtype=int), start_soc
    for t in range(n):
        actions[t] = choice[t, s]
        s += actions[t]
    return float(value[0, start_soc]), actions


def run(hourly: pd.DataFrame, **kw) -> pd.DataFrame:
    """Daily revenue in EUR for a 1 MW / 2 MWh battery."""
    h = hourly[["timestamp", "price_eur_mwh"]].copy()
    h["date"] = h.timestamp.dt.normalize()
    rows = []
    for d, g in h.groupby("date"):
        rev, act = optimise_day(g.price_eur_mwh.to_numpy(), **kw)
        rows.append({"date": d, "revenue_eur": rev, "cycles": float((act == -1).sum()) / 2})
    return pd.DataFrame(rows)


def yearly(daily: pd.DataFrame, capture_factor: float = 0.75) -> pd.DataFrame:
    y = daily.groupby(daily.date.dt.year).agg(days=("date", "count"), revenue_eur=("revenue_eur", "sum"), cycles=("cycles", "sum"))
    y["revenue_eur_per_mw_year"] = y.revenue_eur / y.days * 365
    y["realistic_eur_per_mw_year"] = y.revenue_eur_per_mw_year * capture_factor
    return y.reset_index(names="year")


def solar_plus_storage(hourly: pd.DataFrame, solar_mw: float = 10.0, bess_mw: float = 5.0, eff: float = 0.88) -> pd.DataFrame:
    """How much a co-located battery (2 h) lifts the solar capture price: midday output shifted to the evening.

    Daily heuristic: the battery stores the solar output of the cheapest daylight hours (up to its size) and
    releases it in the most expensive hours after them.
    """
    h = hourly[["timestamp", "price_eur_mwh", "solar_cf"]].copy()
    h["year"], h["date"] = h.timestamp.dt.year, h.timestamp.dt.normalize()
    out = []
    for y, gy in h.groupby("year"):
        base_val = shifted_val = paid_total = 0.0
        for _, g in gy.groupby("date"):
            p, gen = g.price_eur_mwh.to_numpy(), g.solar_cf.to_numpy() * solar_mw
            run = np.where(p >= 0, gen, 0.0)
            base_val += (run * p).sum()
            paid_total += run.sum()
            sunny = np.where(gen > 0)[0]
            if len(sunny) == 0:
                continue
            charge_hours = sunny[np.argsort(p[sunny])][:2]
            stored = np.minimum(gen[charge_hours], bess_mw)
            later = np.arange(charge_hours.max() + 1, len(p))
            if len(later) < 2:
                shifted_val += (run * p).sum()
                continue
            sell_hours = later[np.argsort(p[later])[::-1][:2]]
            gain = (stored.sum() * eff) * p[sell_hours].mean() - (stored * np.maximum(p[charge_hours], 0)).sum()
            shifted_val += (run * p).sum() + max(gain, 0)
        out.append({"year": y, "solar_capture": base_val / paid_total, "with_storage": shifted_val / paid_total})
    r = pd.DataFrame(out)
    r["uplift_eur_mwh"] = r.with_storage - r.solar_capture
    return r
