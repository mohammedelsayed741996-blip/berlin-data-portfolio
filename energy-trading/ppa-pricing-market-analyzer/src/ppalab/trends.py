"""Market trend analysis: price levels, volatility, seasonality, negative prices and capture rates."""

from __future__ import annotations

import numpy as np
import pandas as pd

PEAK_HOURS = range(8, 20)


def enrich(h: pd.DataFrame) -> pd.DataFrame:
    h = h.copy()
    ts = h.timestamp
    h["year"], h["month"], h["hour"] = ts.dt.year, ts.dt.to_period("M").dt.to_timestamp(), ts.dt.hour
    h["date"] = ts.dt.normalize()
    h["is_peak"] = (ts.dt.dayofweek < 5) & ts.dt.hour.isin(PEAK_HOURS)
    return h


def capture(df: pd.DataFrame, gen_col: str) -> float:
    return float((df.price_eur_mwh * df[gen_col]).sum() / df[gen_col].sum())


def yearly(h: pd.DataFrame) -> pd.DataFrame:
    """One row per year: base, peak, spread, volatility, negative hours, solar and wind capture rates."""
    rows = []
    for y, g in h.groupby("year"):
        daily = g.groupby("date").price_eur_mwh.mean()
        base = g.price_eur_mwh.mean()
        rows.append({"year": y, "hours": len(g), "base": base, "peak": g[g.is_peak].price_eur_mwh.mean(),
                     "offpeak": g[~g.is_peak].price_eur_mwh.mean(), "daily_vol": daily.diff().abs().mean(),
                     "intraday_spread": g.groupby("date").price_eur_mwh.agg(lambda s: s.max() - s.min()).mean(),
                     "negative_hours": int((g.price_eur_mwh < 0).sum()), "solar_capture": capture(g, "solar_gw"),
                     "wind_capture": capture(g, "wind_gw")})
    y = pd.DataFrame(rows)
    y["peak_base_spread"] = y.peak - y.base
    y["solar_capture_rate"], y["wind_capture_rate"] = y.solar_capture / y.base, y.wind_capture / y.base
    return y


def monthly(h: pd.DataFrame) -> pd.DataFrame:
    m = h.groupby("month").agg(base=("price_eur_mwh", "mean"), negative_hours=("price_eur_mwh", lambda s: int((s < 0).sum())))
    m["solar_capture_rate"] = h.groupby("month").apply(lambda g: capture(g, "solar_gw"), include_groups=False) / m.base
    m["wind_capture_rate"] = h.groupby("month").apply(lambda g: capture(g, "wind_gw"), include_groups=False) / m.base
    daily = h.groupby("date").price_eur_mwh.mean()
    r = daily.diff().abs().rolling(30).mean()
    m["vol_30d_abs_change"] = r.groupby(r.index.to_period("M").to_timestamp()).last()
    return m.reset_index()


def hour_month_profile(h: pd.DataFrame, last_months: int = 12) -> pd.DataFrame:
    """Average price by calendar month and hour over the most recent period, relative to the period's base."""
    recent = h[h.timestamp > h.timestamp.max() - pd.DateOffset(months=last_months)]
    t = recent.pivot_table(index=recent.timestamp.dt.month, columns="hour", values="price_eur_mwh", aggfunc="mean")
    return t / recent.price_eur_mwh.mean()


def forward_volatility(cal: pd.DataFrame, window: int = 60) -> pd.DataFrame:
    r = np.log(cal.set_index("date").cal27_base_eur_mwh).diff()
    out = pd.DataFrame({"annualised_vol": r.rolling(window).std() * np.sqrt(252)})
    return out.dropna().reset_index()
