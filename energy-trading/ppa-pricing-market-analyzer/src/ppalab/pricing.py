"""PPA pricing: hourly price forward curve, fundamental Monte Carlo, risk premia and structure comparison.

Setting: an originator offers to buy the output of a renewable plant under a PPA and sells it on the market.
For pay-as-produced, the originator pays a fixed price per MWh produced and earns the plant's market value,
so the offer starts from the expected capture price and subtracts the costs and risks it takes over:
balancing, profile risk, volume risk, credit risk and a margin.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import ASSET_YIELD, BALANCING_EUR_MWH, RISK_LAMBDA
from .market import simulate_year

RATING_PD = {"AA": 0.0004, "A": 0.0008, "BBB": 0.0020, "BB": 0.0090, "B": 0.0350}   # one-year default probabilities, indicative
LGD = 0.6


# ------------------------------------------------------------------ hourly price forward curve
def hpfc(history: pd.DataFrame, year: int, base: float, peak: float, months_of_shape: int = 24) -> pd.DataFrame:
    """Hourly price forward curve for a delivery year.

    Shape factors (price / monthly mean, by month, day type and hour) come from recent history; peak and
    off-peak hours are then scaled separately so the curve averages exactly to the traded base and peak.
    """
    recent = history[history.timestamp > history.timestamp.max() - pd.DateOffset(months=months_of_shape)].copy()
    recent["m"], recent["wk"], recent["h"] = recent.timestamp.dt.month, recent.timestamp.dt.dayofweek >= 5, recent.timestamp.dt.hour
    recent["rel"] = recent.price_eur_mwh / recent.groupby(recent.timestamp.dt.to_period("M")).price_eur_mwh.transform("mean")
    shape = recent.groupby(["m", "wk", "h"]).rel.mean()
    idx = pd.date_range(f"{year}-01-01", f"{year}-12-31 23:00", freq="h")
    idx = idx[~((idx.month == 2) & (idx.day == 29))]
    c = pd.DataFrame({"timestamp": idx})
    c["shape_factor"] = shape.reindex(pd.MultiIndex.from_arrays([idx.month, idx.dayofweek >= 5, idx.hour])).to_numpy()
    c["is_peak"] = (idx.dayofweek < 5) & (idx.hour >= 8) & (idx.hour < 20)
    n_pk, n = c.is_peak.sum(), len(c)
    off = (base * n - peak * n_pk) / (n - n_pk)
    c["price"] = np.where(c.is_peak, c.shape_factor / c[c.is_peak].shape_factor.mean() * peak, c.shape_factor / c[~c.is_peak].shape_factor.mean() * off)
    return c


# ------------------------------------------------------------------ fundamental Monte Carlo
def scenarios(years: list[int], n: int, curve: pd.DataFrame, level_vol: float, seed: int = 7) -> list[pd.DataFrame]:
    """n weather and price-level scenarios per delivery year.

    Each scenario simulates the year's hours with that year's installed capacity and a new weather draw, then
    rescales prices so the expected base equals the forward, times a lognormal level shock whose spread grows
    with time to delivery.
    """
    rng = np.random.default_rng(seed)
    fwd = curve.set_index("year").base_eur_mwh
    # level shocks, moment-matched so that every delivery year averages exactly to its forward across scenarios
    shocks = np.exp(np.column_stack([rng.normal(0, level_vol * np.sqrt(j + 0.67), n) for j in range(len(years))]))
    shocks /= shocks.mean(axis=0)
    out = []
    for k in range(n):
        frames = []
        for j, y in enumerate(years):
            s = simulate_year(y, seed=seed * 1000 + k * 10 + j)
            s["price_eur_mwh"] = s.price_eur_mwh / s.price_eur_mwh.mean() * fwd[y] * shocks[k, j]
            s["scenario"], s["year"] = k, y
            frames.append(s)
        out.append(pd.concat(frames, ignore_index=True))
    return out


def asset_stats(scen: list[pd.DataFrame], tech: str, mw: float, curtail_negative: bool = True) -> pd.DataFrame:
    """Per scenario: generation, market value and capture prices of a plant of `mw` with the given technology.

    capture_all  : value of every MWh the weather allows, at the hourly price (negative hours included)
    capture_paid : value per MWh actually produced when the plant curtails in negative hours (PPA standard)
    """
    cf = "solar_cf" if tech == "solar" else "wind_cf"
    rows = []
    for s in scen:
        p = s.price_eur_mwh
        gen = s[cf] * mw * ASSET_YIELD[tech]
        paid = gen.where(p >= 0, 0) if curtail_negative else gen
        rows.append({"scenario": s.scenario.iloc[0], "potential_mwh": gen.sum(), "paid_mwh": paid.sum(),
                     "capture_all": (gen * p).sum() / gen.sum(), "capture_paid": (paid * p).sum() / paid.sum(),
                     "base_eur_mwh": p.mean(), "curtailed_share": float(1 - paid.sum() / gen.sum())})
    r = pd.DataFrame(rows)
    r["capture_rate"] = r.capture_paid / r.base_eur_mwh
    return r


def offer(stats: pd.DataFrame, tech: str, tenor_years: int, rating: str, margin: float = 1.0, lam: float = RISK_LAMBDA,
          hedge_cost: float = 0.35) -> dict:
    """Pay-as-produced offer price per MWh produced, as a walk from the forward base price.

    forward base -> shape (the plant produces when prices are low) -> curtailment uplift (negative hours are not
    produced or paid) = expected capture price; minus balancing, profile risk, volume risk, credit and margin.
    The originator hedges the price level by selling baseload futures (hedge_cost covers bid-ask and rolling), so the
    risk premia cover what a futures hedge cannot: the capture rate (profile risk) and the volume.
    Risk premia are lambda times the standard deviation across scenarios.
    """
    cap = stats.capture_paid
    base = stats.base_eur_mwh.mean()
    shape = stats.capture_all.mean() - base
    curtail = cap.mean() - stats.capture_all.mean()
    # the price level is hedged with baseload futures, so what stays is the shape risk (capture rate uncertainty)
    profile_risk = lam * (stats.capture_rate * base).std()
    vol_shortfall = (stats.paid_mwh.mean() - stats.paid_mwh.quantile(0.1)) / stats.paid_mwh.mean()
    volume_risk = lam * vol_shortfall * cap.mean()
    exposure = 1.65 * cap.std() * np.sqrt(tenor_years / 2)
    credit = RATING_PD[rating] * LGD * exposure * tenor_years
    balancing = BALANCING_EUR_MWH[tech]
    price = cap.mean() - balancing - hedge_cost - profile_risk - volume_risk - credit - margin
    return {"forward_base": base, "shape": shape, "curtailment_uplift": curtail, "expected_capture": cap.mean(), "balancing": -balancing,
            "hedging": -hedge_cost, "profile_risk": -profile_risk, "volume_risk": -volume_risk, "credit": -credit, "margin": -margin,
            "offer_price": price, "capture_rate": cap.mean() / base, "curtailed_share": stats.curtailed_share.mean()}


def structures(scen: list[pd.DataFrame], tech: str, mw: float, pap_price: float, base_price: float, dm_fee: float = 1.5) -> pd.DataFrame:
    """Realised revenue per MWh for the producer under four structures, per scenario.

    merchant      : sells at the hourly price, stops in negative hours
    pay_as_prod.  : fixed price on every MWh produced (negative hours curtailed and unpaid)
    baseload      : delivers a flat band equal to expected average output at a fixed price, buys or sells the
                    difference between production and the band at the hourly price
    swap          : financial fixed-for-floating swap on the same band; the plant still sells physically through a
                    direct marketer, so it pays that fee on every MWh on top of the baseload cash flows
    """
    cf = "solar_cf" if tech == "solar" else "wind_cf"
    band = np.mean([s[cf].mean() * mw * ASSET_YIELD[tech] for s in scen])
    rows = []
    for s in scen:
        p = s.price_eur_mwh.to_numpy()
        gen = s[cf].to_numpy() * mw * ASSET_YIELD[tech]
        run = np.where(p >= 0, gen, 0)
        total = run.sum()
        merchant = (run * p).sum()
        pap = pap_price * total
        baseload = base_price * band * len(p) + ((run - band) * p).sum()
        rows.append({"scenario": s.scenario.iloc[0], "merchant": merchant / total, "pay_as_produced": pap / total, "baseload": baseload / total})
    r = pd.DataFrame(rows)
    r["swap"] = r.baseload - dm_fee
    return r


def summarise_structures(r: pd.DataFrame) -> pd.DataFrame:
    cols = ["merchant", "pay_as_produced", "baseload", "swap"]
    return pd.DataFrame({"expected": r[cols].mean(), "P90 (bad case)": r[cols].quantile(0.1), "P10 (good case)": r[cols].quantile(0.9),
                         "spread P10-P90": r[cols].quantile(0.9) - r[cols].quantile(0.1)}).round(2)
