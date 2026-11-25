"""Simulate an hourly German-style power market: demand, solar, wind, fuel costs and day-ahead prices.

Price formation is a stylised merit order on residual load (demand minus solar and wind):
  * low residual load -> cheap must-run and renewables set the price; below a threshold prices go negative;
  * mid residual load -> coal and gas, priced at their short-run marginal cost (fuel / efficiency + carbon);
  * high residual load -> peakers, with occasional scarcity spikes.
Gas and carbon follow monthly paths with a 2021-22 crisis. Solar capacity more than doubles over the
period, so solar hours get cheaper relative to the rest: the cannibalisation every PPA buyer now prices in.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import END, RAW, SEED, SOLAR_GW, START, WIND_GW


def _capacity(index: pd.DatetimeIndex, table: dict[int, float]) -> np.ndarray:
    years = index.year + (index.dayofyear - 1) / 365.0
    xs = np.array(sorted(table))
    return np.interp(years, xs, [table[x] for x in xs])


def fuel_paths(months: pd.DatetimeIndex, rng) -> pd.DataFrame:
    """Monthly gas (EUR/MWh thermal) and carbon (EUR/t) prices with a crisis peak in August 2022."""
    t = (months - pd.Timestamp("2019-01-01")).days / 365.25
    crisis = np.exp(-0.5 * ((t - 3.6) / 0.38) ** 2)                 # peaks Aug 2022
    pre = np.exp(-0.5 * ((t - 2.9) / 0.35) ** 2)                    # autumn 2021 run-up
    base = np.interp(t, [0, 1.3, 2.0, 4.5, 5.5, 8], [19, 9, 18, 38, 33, 31])
    gas = base + 155 * crisis + 70 * pre
    gas *= np.exp(rng.normal(0, 0.06, len(t)))
    co2 = np.interp(t, [0, 1.2, 2.0, 3.0, 4.2, 5.2, 6.0, 8], [24, 22, 38, 80, 90, 66, 72, 78]) * np.exp(rng.normal(0, 0.04, len(t)))
    return pd.DataFrame({"month": months, "gas_eur_mwh": gas.round(2), "co2_eur_t": co2.round(2)})


def _hourly(idx: pd.DatetimeIndex, rng, gas: np.ndarray, co2: np.ndarray, solar_cap: np.ndarray, wind_cap: np.ndarray, years_in: np.ndarray) -> pd.DataFrame:
    """Weather, demand and price formation for any hourly index. gas and co2 are hourly arrays."""
    n = len(idx)
    hour, doy, dow = idx.hour.to_numpy(), idx.dayofyear.to_numpy(), idx.dayofweek.to_numpy()
    days = (idx.normalize() - idx[0].normalize()).days.to_numpy()

    season = 1 + 0.10 * np.cos(2 * np.pi * (doy - 15) / 365)
    daily = 0.82 + 0.24 * np.clip(np.sin(np.pi * (hour - 5) / 16), 0, None) + 0.06 * np.exp(-0.5 * ((hour - 19) / 1.6) ** 2)
    weekend = np.where(dow >= 5, 0.84, 1.0)
    holiday = np.where(((idx.month == 12) & (idx.day >= 24)) | ((idx.month == 1) & (idx.day == 1)), 0.85, 1.0)
    demand = 57 * season * daily * weekend * holiday * (1 + rng.normal(0, 0.02, n))

    day_len = 12 + 4.2 * np.sin(2 * np.pi * (doy - 80) / 365)
    noon_dist = (hour + 0.5 - 13.0) / (day_len / 2)
    clear = np.clip(1 - noon_dist**2, 0, None) ** 1.3 * (0.55 + 0.45 * np.sin(np.pi * np.clip(doy, 0, 365) / 365))
    cloud_day = np.clip(rng.beta(2.4, 1.6, days.max() + 1), 0.08, 1)[days]
    solar_cf = 0.50 * clear * cloud_day

    ar = np.zeros(n)
    eps = rng.normal(0, 0.11, n)
    for i in range(1, n):
        ar[i] = 0.985 * ar[i - 1] + eps[i]
    wind_cf = np.clip(0.20 + 0.09 * np.cos(2 * np.pi * (doy - 20) / 365) + 0.16 * ar + 0.02 * np.sin(2 * np.pi * hour / 24), 0.01, 0.93)
    solar, wind = solar_cf * solar_cap, wind_cf * wind_cap

    srmc_gas = gas / 0.52 + co2 * 0.37
    srmc_coal = 6 / 0.40 + co2 * 0.85 + 0.15 * gas                     # coal price loosely follows gas
    rl_raw = demand - solar - wind                                     # residual load in GW
    flex = (1.5 + 1.25 * years_in + 4.0 * np.clip(years_in - 7, 0, None)) / (1 + np.exp(-(10 - rl_raw) / 3))  # exports, storage; batteries ramp up from 2026
    rl = rl_raw + flex
    flex_floor = 9.0                                                    # below this prices turn negative
    lo, hi = np.minimum(srmc_coal, srmc_gas), np.maximum(srmc_coal, srmc_gas)
    p_mid = np.where(rl < 28, srmc_coal * (0.35 + 0.65 * (rl - flex_floor) / (28 - flex_floor)), lo + (hi - lo) * np.clip((rl - 28) / 14, 0, 1))
    price = np.where(rl > 44, srmc_gas * (1 + 0.03 * (rl - 44)) + 9 * (rl - 44), p_mid)
    price = np.where(rl < flex_floor, -3.0 * np.maximum(flex_floor - rl, 0) ** 1.1 - 0.5, price)
    price *= np.exp(rng.normal(0, 0.07, n))
    spikes = rng.random(n) < 0.0008 * (rl > 40)
    price = np.where(spikes, price + rng.uniform(150, 900, n), price)
    price = np.clip(price, -500, 4000).round(2)
    return pd.DataFrame({"timestamp": idx, "price_eur_mwh": price, "demand_gw": demand.round(2), "solar_gw": solar.round(2), "wind_gw": wind.round(2),
                         "solar_cf": solar_cf.round(4), "wind_cf": wind_cf.round(4)})


def simulate(seed: int = SEED) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    idx = pd.date_range(START, END, freq="h")
    months = pd.date_range(idx[0].to_period("M").to_timestamp(), idx[-1].to_period("M").to_timestamp(), freq="MS")
    fuels = fuel_paths(months, rng)
    m = pd.Series(np.arange(len(months)), index=months)
    mi = m.reindex(idx.to_period("M").to_timestamp()).to_numpy()
    years_in = (idx.normalize() - idx[0].normalize()).days.to_numpy() / 365.0
    df = _hourly(idx, rng, fuels.gas_eur_mwh.to_numpy()[mi], fuels.co2_eur_t.to_numpy()[mi], _capacity(idx, SOLAR_GW), _capacity(idx, WIND_GW), years_in)
    return df, fuels


def simulate_year(year: int, seed: int, gas: float = 31.0, co2: float = 78.0) -> pd.DataFrame:
    """One delivery-year scenario with that year's capacity and a fresh weather draw (fundamental Monte Carlo)."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range(f"{year}-01-01", f"{year}-12-31 23:00", freq="h")
    idx = idx[~((idx.month == 2) & (idx.day == 29))]
    years_in = (idx.normalize() - pd.Timestamp(START)).days.to_numpy() / 365.0
    return _hourly(idx, rng, np.full(len(idx), gas), np.full(len(idx), co2), _capacity(idx, SOLAR_GW), _capacity(idx, WIND_GW), years_in)


def forwards(hourly: pd.DataFrame, fuels: pd.DataFrame, seed: int = SEED) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Calendar futures settlement prices on the pricing date, and a daily history of the Cal-27 baseload contract.

    The forward level is anchored on the last 12 months of spot prices with mild backwardation; the history is a
    geometric random walk with volatility falling as delivery approaches less (long-dated power is calmer).
    """
    rng = np.random.default_rng(seed + 1)
    last = hourly[hourly.timestamp >= hourly.timestamp.max() - pd.Timedelta(days=365)]
    base = last.price_eur_mwh.mean()
    pk = last[(last.timestamp.dt.dayofweek < 5) & last.timestamp.dt.hour.between(8, 19)].price_eur_mwh.mean()
    curve = pd.DataFrame({"product": ["Cal-27", "Cal-28", "Cal-29", "Cal-30"], "year": [2027, 2028, 2029, 2030]})
    curve["base_eur_mwh"] = (base * np.array([0.97, 0.93, 0.90, 0.88])).round(2)
    curve["peak_eur_mwh"] = (pk * np.array([0.97, 0.93, 0.90, 0.88])).round(2)
    days = pd.bdate_range("2024-01-02", "2026-11-02")
    vol = 0.30 / np.sqrt(252)
    path = np.exp(np.cumsum(rng.normal(-vol**2 / 2, vol, len(days))))
    path = path / path[-1] * curve.base_eur_mwh.iloc[0]
    hist = pd.DataFrame({"date": days, "cal27_base_eur_mwh": path.round(2)})
    return curve, hist


def write(raw=RAW, seed: int = SEED) -> dict:
    raw.mkdir(parents=True, exist_ok=True)
    hourly, fuels = simulate(seed)
    curve, hist = forwards(hourly, fuels, seed)
    hourly.to_csv(raw / "de_hourly_market.csv.gz", index=False, compression={"method": "gzip", "mtime": 0})
    fuels.to_csv(raw / "fuels_monthly.csv", index=False, date_format="%Y-%m")
    curve.to_csv(raw / "forward_curve.csv", index=False)
    hist.to_csv(raw / "cal27_history.csv", index=False)
    return {"hourly": hourly, "fuels": fuels, "curve": curve, "cal27": hist}


def load(raw=RAW) -> dict:
    hourly = pd.read_csv(raw / "de_hourly_market.csv.gz", parse_dates=["timestamp"])
    return {"hourly": hourly, "fuels": pd.read_csv(raw / "fuels_monthly.csv", parse_dates=["month"]),
            "curve": pd.read_csv(raw / "forward_curve.csv"), "cal27": pd.read_csv(raw / "cal27_history.csv", parse_dates=["date"])}
