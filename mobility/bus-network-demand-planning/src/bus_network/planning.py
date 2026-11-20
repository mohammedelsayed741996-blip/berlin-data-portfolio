"""Demand forecast and demand-based offer planning for the winter timetable.

Forecast
    Sold-out trips hide demand: the bus was full, so the bookings stop at the seat count.
    The model is a log-linear regression per departure (line, direction, time) with month,
    weekday, holiday and a line-specific trend. Censored trips are handled by iterative
    imputation: fit on all trips, replace each sold-out trip's demand with the larger of
    its bookings and the prediction, refit, repeat.

Offer plan
    For each line and direction, every option of 1 to 8 departures a day and single or
    double-deckers is scored on expected contribution over the season (revenue of the
    passengers who fit, minus bus-km cost), with demand noise simulated. A mixed-integer
    program picks one option per line and direction within a bus-hour budget and the
    partners' double-decker fleets.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import Bounds, LinearConstraint, milp

from . import config as C
from .world import EASTER, HOLIDAYS, road_km


# ---------------------------------------------------------------------------- features
def _calendar(dates: pd.Series) -> pd.DataFrame:
    d = pd.to_datetime(dates)
    md = d.dt.strftime("%m-%d")
    hol = md.isin(HOLIDAYS)
    for e in EASTER.values():
        e = pd.Timestamp(e)
        hol |= (d >= e - pd.Timedelta(days=1)) & (d <= e + pd.Timedelta(days=3))
    hol |= (d.dt.year == 2027) & (md.isin(["03-26", "03-27", "03-28", "03-29"]))      # Easter 2027
    return pd.DataFrame({"month": d.dt.month, "weekday": d.dt.weekday, "holiday": hol.astype(float),
                         "t": (d - pd.Timestamp(C.START)).dt.days / 365.25}, index=dates.index)


def _design(df: pd.DataFrame, keys: list[str], lines: list[str]) -> np.ndarray:
    cal = _calendar(df["date"])
    cols = [np.ones(len(df))]
    for m in range(2, 13):
        cols.append((cal["month"] == m).values.astype(float))
    for w in range(1, 7):
        cols.append((cal["weekday"] == w).values.astype(float))
    cols.append(cal["holiday"].values)
    key = df["line"] + df["direction"] + df["dep_time"]
    for k in keys[1:]:
        cols.append((key == k).values.astype(float))
    for line in lines:
        cols.append(((df["line"] == line).values * cal["t"].values).astype(float))
    return np.column_stack(cols)


class DemandModel:
    def __init__(self, iterations: int = 4):
        self.iterations = iterations

    def fit(self, trips: pd.DataFrame) -> "DemandModel":
        t = trips[trips["pax"] > 0].copy()
        self.keys = sorted((t["line"] + t["direction"] + t["dep_time"]).unique())
        self.lines = sorted(t["line"].unique())
        X = _design(t, self.keys, self.lines)
        y = np.log(t["pax"].values.astype(float))
        censored = t["sold_out"].values.astype(bool)
        target = y.copy()
        for _ in range(self.iterations):
            beta, *_ = np.linalg.lstsq(X, target, rcond=None)
            pred = X @ beta
            resid_sd = np.std((target - pred)[~censored])
            # expected value of a lognormal tail above the observed bookings
            target = np.where(censored, np.maximum(y, pred + 0.5 * resid_sd), y)
        self.beta, self.sigma = beta, float(resid_sd)
        return self

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        X = _design(df, self.keys, self.lines)
        return np.exp(X @ self.beta + 0.5 * self.sigma ** 2)


def season_grid(tt: pd.DataFrame, season: tuple[str, str]) -> pd.DataFrame:
    dates = pd.date_range(*season, freq="D").strftime("%Y-%m-%d")
    g = tt[["line", "direction", "dep_time"]].merge(pd.DataFrame({"date": dates}), how="cross")
    return g


def backtest(trips: pd.DataFrame, truth: pd.DataFrame, tt: pd.DataFrame) -> tuple[dict, pd.DataFrame]:
    """Fit on data before the 2025/26 winter season and predict it; compare at line-direction-week level."""
    start, end = C.BACKTEST_SEASON
    train = trips[trips["date"] < start]
    m = DemandModel().fit(train)
    test = trips[trips["date"].between(start, end)].merge(truth, on="trip_id")
    test["pred"] = m.predict(test)
    last = trips[trips["date"].between(str(int(start[:4]) - 1) + start[4:], str(int(end[:4]) - 1) + end[4:])]
    naive = last.groupby(["line", "direction", "dep_time"])["pax"].mean()
    test["naive"] = test.set_index(["line", "direction", "dep_time"]).index.map(naive).values
    test["week"] = pd.to_datetime(test["date"]).dt.strftime("%G-%V")
    w = test.groupby(["line", "direction", "week"])[["unconstrained_pax", "pax", "pred", "naive"]].sum()

    def wape(a, f):
        return float(np.abs(a - f).sum() / a.sum())

    metrics = {"model_wape_vs_true_demand": wape(w["unconstrained_pax"], w["pred"]),
            "naive_wape_vs_true_demand": wape(w["unconstrained_pax"], w["naive"]),
            "bookings_understate_demand_pct": float(1 - w["pax"].sum() / w["unconstrained_pax"].sum()),
            "model_bias_pct": float(w["pred"].sum() / w["unconstrained_pax"].sum() - 1), "weeks": len(w)}
    return metrics, w.reset_index()


# ---------------------------------------------------------------------------- offer options
FREQ_ELASTICITY = 0.35        # demand grows with the number of departures, with diminishing returns
MAX_SOLD_OUT = 0.25           # at most a quarter of departures sold out: a full bus turns customers away

def _profile(trips: pd.DataFrame) -> pd.DataFrame:
    """Per line and direction: revenue per passenger and the ratio of peak load to passengers."""
    t = trips[trips["pax"] > 0]
    return t.groupby(["line", "direction"]).agg(rev_per_pax=("revenue_eur", "sum"), pax=("pax", "sum"),
                                                peak=("peak_load", "sum")).assign(
        rev_per_pax=lambda d: d["rev_per_pax"] / d["pax"], peak_ratio=lambda d: d["peak"] / d["pax"])[["rev_per_pax", "peak_ratio"]]


def options(model: DemandModel, trips: pd.DataFrame, tt: pd.DataFrame, season: tuple[str, str],
            draws: int = 200, seed: int = C.SEED) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    grid = season_grid(tt, season)
    grid["demand"] = model.predict(grid)
    daily = grid.groupby(["line", "direction", "date"])["demand"].sum().rename("total").reset_index()
    prof = _profile(trips)
    cur = tt.groupby(["line", "direction"]).agg(cur_f=("dep_time", "size"), cur_bus=("bus_type_planned", "first"),
                                                partner_id=("partner_id", "first"))
    order = list(np.argsort(C.SLOT_WEIGHT)[::-1])
    rows = []
    for (line, d), g in daily.groupby(["line", "direction"]):
        seq = C.LINES[line]
        km = sum(road_km(seq[i], seq[i + 1]) for i in range(len(seq) - 1))
        hours = km / C.DRIVE_SPEED_KMH
        rpp, ratio = prof.loc[(line, d), "rev_per_pax"], prof.loc[(line, d), "peak_ratio"]
        total = g["total"].values
        noise = rng.lognormal(-0.5 * 0.25 ** 2, 0.25, (draws, len(total), 1))
        for f in range(1, 9):
            slots = sorted(order[:f])
            w = np.array([C.SLOT_WEIGHT[s] for s in slots])
            share = w / w.sum()
            # more departures win more passengers and fewer lose some (frequency elasticity)
            elastic = (f / cur.loc[(line, d), "cur_f"]) ** FREQ_ELASTICITY
            dep_demand = total[None, :, None] * elastic * share[None, None, :] * noise   # draws x days x departures
            for bus, seats in C.BUS_TYPES.items():
                cap_pax = seats / ratio                                               # passengers that fit given the peak segment
                served = np.minimum(dep_demand, cap_pax)
                served_mean = served.mean(axis=0).sum()
                sold_out = (dep_demand >= cap_pax).mean()
                cost = len(total) * f * km * C.COST_PER_BUS_KM * (1.2 if bus == "double" else 1.0)
                rows.append({"line": line, "direction": d, "departures": f, "bus": bus, "seats": seats,
                             "demand_pax": float(total.sum() * elastic), "served_pax": float(served_mean), "sold_out_share": float(sold_out),
                             "revenue_eur": float(served_mean * rpp), "cost_eur": float(cost),
                             "contribution_eur": float(served_mean * rpp - cost), "bus_hours": float(len(total) * f * hours),
                             "double_departures_per_day": f if bus == "double" else 0,
                             "load_factor": float(served_mean * ratio / (f * seats * len(total))),
                             "partner_id": cur.loc[(line, d), "partner_id"],
                             "is_current": (f == cur.loc[(line, d), "cur_f"]) and (bus == cur.loc[(line, d), "cur_bus"])})
    return pd.DataFrame(rows)


def optimise(opts: pd.DataFrame, partners: pd.DataFrame, budget_growth: float = 0.03) -> pd.DataFrame:
    """Pick one option per line and direction: maximise contribution within the bus-hour budget and fleets."""
    o = opts.reset_index(drop=True)
    n = len(o)
    groups = o.groupby(["line", "direction"]).indices
    A, lo, hi = [], [], []
    for idx in groups.values():
        row = np.zeros(n)
        row[idx] = 1
        A.append(row); lo.append(1); hi.append(1)
    # buses run round trips: both directions of a line get the same number of departures and bus type
    for (line, f, bus), idx in o.groupby(["line", "departures", "bus"]).indices.items():
        if len(idx) == 2:
            row = np.zeros(n)
            row[idx[0]], row[idx[1]] = 1, -1
            A.append(row); lo.append(0); hi.append(0)
    budget = o.loc[o["is_current"], "bus_hours"].sum() * (1 + budget_growth)
    A.append(o["bus_hours"].values); lo.append(0); hi.append(budget)
    fleet = partners.set_index("partner_id")["fleet_double"]
    for pid, idx in o.groupby("partner_id").indices.items():
        row = np.zeros(n)
        row[idx] = o.loc[idx, "double_departures_per_day"].values
        A.append(row); lo.append(0); hi.append(float(fleet.get(pid, 0) * 2))       # about two trips per bus and day
    # keep the network growing: carry at least as many passengers as the current timetable
    A.append(o["served_pax"].values); lo.append(o.loc[o["is_current"], "served_pax"].sum()); hi.append(np.inf)
    # service quality: no option that sells out too often, unless it is what runs today
    ok = (o["sold_out_share"] <= MAX_SOLD_OUT) | o["is_current"]
    bounds_hi = np.where(ok, 1, 0)
    res = milp(c=-o["contribution_eur"].values, constraints=LinearConstraint(np.array(A), lo, hi),
               integrality=np.ones(n), bounds=Bounds(0, bounds_hi))
    if not res.success:
        raise RuntimeError(res.message)
    o["chosen"] = res.x > 0.5
    return o


def plan_table(o: pd.DataFrame) -> pd.DataFrame:
    cur = o[o["is_current"]].set_index(["line", "direction"])
    new = o[o["chosen"]].set_index(["line", "direction"])
    t = pd.DataFrame({
        "current": cur["departures"].astype(str) + " x " + cur["bus"], "proposed": new["departures"].astype(str) + " x " + new["bus"],
        "demand_pax": cur["demand_pax"].round(0), "served_now": cur["served_pax"].round(0), "served_plan": new["served_pax"].round(0),
        "sold_out_now": cur["sold_out_share"].round(3), "sold_out_plan": new["sold_out_share"].round(3),
        "lf_now": cur["load_factor"].round(3), "lf_plan": new["load_factor"].round(3),
        "contribution_now": cur["contribution_eur"].round(0), "contribution_plan": new["contribution_eur"].round(0),
        "bus_hours_now": cur["bus_hours"].round(0), "bus_hours_plan": new["bus_hours"].round(0)})
    t["change"] = np.where(t["current"] == t["proposed"], "keep", "change")
    t["contribution_delta"] = t["contribution_plan"] - t["contribution_now"]
    return t.reset_index()
