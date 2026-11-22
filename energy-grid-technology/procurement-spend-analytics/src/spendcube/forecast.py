"""Commodity price forecasting and index pass-through to purchase prices.

Two questions a category buyer asks:
1. Where will copper, steel, electrical steel, aluminium and oil go in the next six months?
2. How much of an index move reaches our purchase prices, and with what delay?

Forecasts are judged by a rolling-origin backtest against the naive forecast ("next month equals this
month"). Commodity prices are close to a random walk, so a model is only used if it beats naive.
"""

from __future__ import annotations

import itertools

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge

from .config import CATEGORIES

H = 6


# ------------------------------------------------------------------ models (all work on log prices)
def f_naive(y: np.ndarray, h: int) -> np.ndarray:
    return np.repeat(y[-1], h)


def f_drift(y: np.ndarray, h: int, window: int = 36) -> np.ndarray:
    w = y[-window:]
    slope = (w[-1] - w[0]) / (len(w) - 1)
    return y[-1] + slope * np.arange(1, h + 1)


def f_seasonal_naive(y: np.ndarray, h: int) -> np.ndarray:
    """Last value plus last year's month-to-month pattern."""
    base = y[-1] - y[-13]
    return np.array([y[-13 + k] + base for k in range(1, h + 1)])


def _holt_damped(y, alpha, beta, phi):
    level, trend = y[0], y[1] - y[0]
    sse = 0.0
    for t in range(1, len(y)):
        pred = level + phi * trend
        sse += (y[t] - pred) ** 2
        new_level = alpha * y[t] + (1 - alpha) * (level + phi * trend)
        trend = beta * (new_level - level) + (1 - beta) * phi * trend
        level = new_level
    return level, trend, sse


def f_holt_damped(y: np.ndarray, h: int) -> np.ndarray:
    best = None
    for a, b, p in itertools.product([0.3, 0.5, 0.7, 0.9, 1.0], [0.01, 0.05, 0.1, 0.2], [0.8, 0.9, 0.98]):
        lv, tr, sse = _holt_damped(y, a, b, p)
        if best is None or sse < best[0]:
            best = (sse, lv, tr, p)
    _, lv, tr, p = best
    return np.array([lv + tr * sum(p ** i for i in range(1, k + 1)) for k in range(1, h + 1)])


def f_ar_ridge(y: np.ndarray, h: int, lags: int = 3) -> np.ndarray:
    """Ridge regression of monthly log returns on their own lags, iterated forward."""
    r = np.diff(y)
    X = np.column_stack([r[lags - k - 1: len(r) - k - 1] for k in range(lags)])
    target = r[lags:]
    m = Ridge(alpha=1.0).fit(X, target)
    hist, out, level = list(r[-lags:]), [], y[-1]
    for _ in range(h):
        step = float(m.predict(np.array(hist[::-1][:lags]).reshape(1, -1))[0])
        level += step
        out.append(level)
        hist.append(step)
    return np.array(out)


MODELS = {"naive": f_naive, "drift": f_drift, "seasonal_naive": f_seasonal_naive, "holt_damped": f_holt_damped, "ar_ridge": f_ar_ridge}


def backtest(indices: pd.DataFrame, first_origin: str = "2023-10-01", min_train: int = 48) -> pd.DataFrame:
    """Rolling origin: refit at every month from first_origin, forecast 1-6 months ahead, compare with actuals."""
    rows = []
    idx = indices.set_index("month")
    for name in idx.columns:
        y = np.log(idx[name].to_numpy())
        months = idx.index
        for o in range(max(min_train, months.get_loc(pd.Timestamp(first_origin))), len(y) - 1):
            h = min(H, len(y) - 1 - o)
            for model, f in MODELS.items():
                pred = f(y[: o + 1], h)
                for k in range(h):
                    actual = np.exp(y[o + 1 + k])
                    rows.append({"index": name, "origin": months[o], "model": model, "h": k + 1, "actual": actual,
                                 "forecast": float(np.exp(pred[k])), "ape": abs(np.exp(pred[k]) - actual) / actual})
    return pd.DataFrame(rows)


def summarise(bt: pd.DataFrame) -> pd.DataFrame:
    """MAPE by index and model (all horizons), and the skill against naive (positive = better than naive)."""
    m = bt.groupby(["index", "model"]).ape.mean().unstack()
    skill = 1 - m.div(m["naive"], axis=0)
    out = m.round(4).add_suffix("_mape").join(skill.drop(columns="naive").round(3).add_suffix("_skill"))
    out["chosen"] = [r.idxmax() if r.max() > 0.05 else "naive" for _, r in skill.drop(columns="naive").iterrows()]
    return out


def intervals(indices: pd.DataFrame, level: float = 0.8) -> pd.DataFrame:
    """Empirical h-step log-change quantiles from the history, used as prediction bands around any point forecast."""
    rows = []
    for name in indices.columns.drop("month"):
        y = np.log(indices[name].to_numpy())
        for h in range(1, H + 1):
            ch = y[h:] - y[:-h]
            rows.append({"index": name, "h": h, "lo": float(np.quantile(ch, (1 - level) / 2)), "hi": float(np.quantile(ch, 1 - (1 - level) / 2))})
    return pd.DataFrame(rows)


def coverage(bt: pd.DataFrame, indices: pd.DataFrame, model_by_index: dict, level: float = 0.8) -> float:
    """Share of backtest actuals that fell inside the bands (bands built only from data before each origin)."""
    hits = []
    idx = indices.set_index("month")
    for (name, origin), g in bt[bt.model.map(lambda m: True)].groupby(["index", "origin"]):
        g = g[g.model == model_by_index[name]]
        hist = np.log(idx.loc[:origin, name].to_numpy())
        for _, r in g.iterrows():
            ch = hist[r.h:] - hist[:-r.h]
            lo, hi = np.quantile(ch, (1 - level) / 2), np.quantile(ch, 1 - (1 - level) / 2)
            base = np.log(r.forecast)
            hits.append(base + lo <= np.log(r.actual) <= base + hi)
    return float(np.mean(hits))


def forecast(indices: pd.DataFrame, chosen: dict, level: float = 0.8) -> pd.DataFrame:
    iv = intervals(indices, level).set_index(["index", "h"])
    last = indices.month.max()
    rows = []
    for name in indices.columns.drop("month"):
        y = np.log(indices[name].to_numpy())
        pred = MODELS[chosen[name]](y, H)
        for k in range(H):
            lo, hi = iv.loc[(name, k + 1)]
            rows.append({"index": name, "month": last + pd.DateOffset(months=k + 1), "model": chosen[name], "forecast": float(np.exp(pred[k])),
                         "lo": float(np.exp(pred[k] + lo)), "hi": float(np.exp(pred[k] + hi))})
    return pd.DataFrame(rows)


def volatility(indices: pd.DataFrame, months: int = 36) -> dict[str, float]:
    r = np.log(indices.set_index("month")).diff().tail(months)
    return r.std().to_dict()


# ------------------------------------------------------------------ pass-through to purchase prices
def pass_through(fact: pd.DataFrame, indices: pd.DataFrame, max_lag: int = 3) -> pd.DataFrame:
    """For each index-linked category, regress relative purchase price on the relative index at lags 0..max_lag.

    Relative price = line price / mean price of that material; relative index = index / its mean over the same
    months. The best lag by R^2 and the slope (share of the price that moves with the index) are reported.
    """
    idx = indices.set_index("month")
    f = fact[~fact.is_return & fact.quantity.gt(0)].copy()
    f["rel_price"] = f.unit_price_eur / f.groupby("material_id").unit_price_eur.transform("mean")
    rows = []
    for cat, c in CATEGORIES.items():
        if not c["index"]:
            continue
        m = f[f.category == cat].groupby("month").rel_price.mean()
        best = None
        for lag in range(max_lag + 1):
            x = idx[c["index"]].shift(lag).reindex(m.index)
            x = x / x.mean()
            A = np.column_stack([np.ones(len(m)), x.to_numpy()])
            coef, *_ = np.linalg.lstsq(A, m.to_numpy(), rcond=None)
            pred = A @ coef
            r2 = 1 - ((m - pred) ** 2).sum() / ((m - m.mean()) ** 2).sum()
            if best is None or r2 > best["r2"]:
                best = {"category": cat, "index": c["index"], "lag_months": lag, "pass_through": float(coef[1]), "r2": float(r2)}
        rows.append(best)
    return pd.DataFrame(rows)


def budget_impact(fact: pd.DataFrame, indices: pd.DataFrame, fc: pd.DataFrame, pt: pd.DataFrame) -> pd.DataFrame:
    """Expected change in spend over the next six months versus today's prices, at the last 12 months' average volume.

    price change = pass_through x (index at month - lag) / (index over the last 3 months) - pass_through.
    """
    idx = indices.set_index("month")
    full = {name: pd.concat([idx[name], fc[fc["index"] == name].set_index("month")[col]]) for name in idx.columns for col in ["forecast"]}
    lo = {name: pd.concat([idx[name], fc[fc["index"] == name].set_index("month")["lo"]]) for name in idx.columns}
    hi = {name: pd.concat([idx[name], fc[fc["index"] == name].set_index("month")["hi"]]) for name in idx.columns}
    last = fact.month.max()
    recent = fact[(fact.month > last - pd.DateOffset(months=12)) & ~fact.is_return]
    monthly_spend = recent.groupby("category").spend_eur.sum() / 12
    rows = []
    for _, p in pt.iterrows():
        base = idx[p["index"]].loc[last - pd.DateOffset(months=2 + p.lag_months): last - pd.DateOffset(months=p.lag_months)].mean()
        for which, series in (("expected", full), ("low", lo), ("high", hi)):
            s = series[p["index"]]
            change = [p.pass_through * (s.loc[m - pd.DateOffset(months=int(p.lag_months))] / base - 1) for m in fc.month.unique()]
            rows.append({"category": p.category, "case": which, "avg_price_change": float(np.mean(change)),
                         "impact_eur_6m": float(np.sum(change) * monthly_spend[p.category])})
    out = pd.DataFrame(rows).pivot(index="category", columns="case", values=["avg_price_change", "impact_eur_6m"])
    out.columns = [f"{a}_{b}" for a, b in out.columns]
    out["monthly_spend_eur"] = monthly_spend.reindex(out.index)
    return out.reset_index()
