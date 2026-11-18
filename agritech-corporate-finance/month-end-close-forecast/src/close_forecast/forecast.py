"""Rolling forecast for functional costs, revenue and capex.

Four methods are compared for costs, per functional area and cost type
(personnel vs everything else):

    budget     remaining months = budget
    run_rate   average of the last three actual months, flat
    seasonal   prior-year actuals for the remaining months, scaled by the YTD ratio to prior year
    driver     personnel: planned FTE x actual hiring gap x actual cost per FTE (13th salary in November)
               other costs: remaining budget x YTD actual-to-budget ratio; rent and depreciation at last month

The choice is made on evidence: each method forecasts FY 2025/26 from period 3,
6 and 9 cut-offs, and the one with the lowest weighted absolute error on the
remaining months wins for that functional area and cost type. The winners then
produce the 3+9 forecast for FY 2026/27, built on actuals after the proposed
close corrections.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as C
from .fiscal import fiscal_months, fiscal_period, fiscal_year
from .variance import actual_costs

METHODS = ["budget", "run_rate", "seasonal", "driver"]
KEY = ["company_code", "cost_center", "functional_area", "gl_account"]


def cost_class(account: str) -> str:
    return "Personnel" if account == "6000" else "Other costs"


def _matrices(tables, adjustments: pd.DataFrame | None = None):
    act = actual_costs(tables)
    if adjustments is not None and not adjustments.empty:
        adj = adjustments.rename(columns={"amount_eur": "actual_eur"})
        adj = adj.assign(fiscal_year=adj["month"].map(fiscal_year), period=adj["month"].map(fiscal_period))
        act = pd.concat([act, adj[act.columns]], ignore_index=True)
    act = act[act["cost_center"] != ""]
    A = act.pivot_table(index=KEY, columns="month", values="actual_eur", aggfunc="sum", fill_value=0.0)
    B = tables["budget"].pivot_table(index=KEY, columns="month", values="budget_eur", aggfunc="sum", fill_value=0.0)
    idx = A.index.union(B.index)
    A = A.reindex(idx, fill_value=0.0)
    B = B.reindex(idx, fill_value=0.0)
    hc = tables["headcount"]
    fte_plan = hc.pivot_table(index="cost_center", columns="month", values="fte_plan")
    fte_act = hc.pivot_table(index="cost_center", columns="month", values="fte_actual")
    return A, B, fte_plan, fte_act


def _bonus(month: str) -> float:
    return 1.5 if int(month[5:]) == C.THIRTEENTH_SALARY_MONTH else 1.0


def forecast_costs(tables, fy: str, cutoff: int, method: str, adjustments=None, mats=None) -> pd.DataFrame:
    """Forecast for the months after `cutoff` in `fy`, one column per remaining month."""
    A, B, fte_plan, fte_act = mats or _matrices(tables, adjustments)
    months = fiscal_months(fy)
    done, rest = months[:cutoff], months[cutoff:]
    py = [(pd.Period(m, freq="M") - 12).strftime("%Y-%m") for m in months]
    py_done, py_rest = py[:cutoff], py[cutoff:]
    F = pd.DataFrame(0.0, index=A.index, columns=pd.Index(rest, name="month"))

    if method == "budget":
        F[rest] = B[rest].values
    elif method == "run_rate":
        last3 = done[-3:]
        F[rest] = np.repeat(A[last3].mean(axis=1).values[:, None], len(rest), axis=1)
    elif method == "seasonal":
        ytd = A[done].sum(axis=1)
        ytd_py = A[py_done].sum(axis=1).replace(0, np.nan)
        ratio = (ytd / ytd_py).clip(0.7, 1.3).fillna(1.0)
        F[rest] = A[py_rest].values * ratio.values[:, None]
    elif method == "driver":
        ytd_a = A[done].sum(axis=1)
        ytd_b = B[done].sum(axis=1).replace(0, np.nan)
        ratio = (ytd_a / ytd_b).clip(0.7, 1.3).fillna(1.0)
        F[rest] = B[rest].values * ratio.values[:, None]
        accounts = A.index.get_level_values("gl_account")
        flat = np.isin(accounts, list(C.FLAT_ACCOUNTS))
        last = A[done[-1]].where(A[done[-1]] != 0, B[done[-1]])
        F.loc[flat, rest] = np.repeat(last[flat].values[:, None], len(rest), axis=1)
        pers = accounts == "6000"
        for key in A.index[pers]:
            cc = key[1]
            if cc not in fte_plan.index:
                continue
            fa = fte_act.loc[cc, done]
            fp = fte_plan.loc[cc, done]
            gap = fa.sum() / fp.sum()
            weighted = sum(fa[m] * _bonus(m) for m in done)
            rate = A.loc[key, done].sum() / weighted if weighted else 0.0
            F.loc[key, rest] = [fte_plan.loc[cc, m] * gap * rate * _bonus(m) for m in rest]
    else:
        raise ValueError(method)
    return F


def backtest(tables, fy: str = "2025/26", cutoffs=(3, 6, 9)) -> pd.DataFrame:
    """Weighted absolute percentage error of each method on the remaining months, by cost center and account."""
    mats = _matrices(tables)
    A = mats[0]
    months = fiscal_months(fy)
    rows = []
    for cutoff in cutoffs:
        rest = months[cutoff:]
        truth = A[rest].sum(axis=1)
        for method in METHODS:
            f = forecast_costs(tables, fy, cutoff, method, mats=mats).sum(axis=1)
            df = pd.DataFrame({"truth": truth, "forecast": f}).reset_index()
            df["cost_type"] = df["gl_account"].map(cost_class)
            for (fa, ct), g in df.groupby(["functional_area", "cost_type"]):
                wape = (g["forecast"] - g["truth"]).abs().sum() / g["truth"].abs().sum()
                bias = (g["forecast"].sum() - g["truth"].sum()) / g["truth"].sum()
                rows.append({"cutoff_period": cutoff, "method": method, "functional_area": fa, "cost_type": ct,
                             "wape": round(wape, 4), "bias": round(bias, 4)})
    return pd.DataFrame(rows)


def choose_methods(bt: pd.DataFrame) -> pd.DataFrame:
    avg = bt.groupby(["functional_area", "cost_type", "method"], as_index=False)["wape"].mean()
    best = avg.loc[avg.groupby(["functional_area", "cost_type"])["wape"].idxmin()]
    budget = avg[avg["method"] == "budget"][["functional_area", "cost_type", "wape"]].rename(columns={"wape": "budget_wape"})
    out = best.merge(budget, on=["functional_area", "cost_type"]).rename(columns={"wape": "chosen_wape", "method": "chosen_method"})
    return out.reset_index(drop=True)


def forecast_fy(tables, adjustments=None, fy: str | None = None, cutoff: int | None = None,
                choice: pd.DataFrame | None = None) -> pd.DataFrame:
    """Actual YTD (after corrections) + forecast with the chosen methods, long format by month."""
    fy = fy or fiscal_year(C.CLOSE_PERIOD)
    cutoff = cutoff or fiscal_period(C.CLOSE_PERIOD)
    choice = choice if choice is not None else choose_methods(backtest(tables))
    mats = _matrices(tables, adjustments)
    A, B = mats[0], mats[1]
    months = fiscal_months(fy)
    done, rest = months[:cutoff], months[cutoff:]
    per_method = {m: forecast_costs(tables, fy, cutoff, m, mats=mats) for m in METHODS}
    pick = {(r.functional_area, r.cost_type): r.chosen_method for r in choice.itertuples()}
    F = pd.DataFrame(0.0, index=A.index, columns=rest)
    method_used = pd.Series("", index=A.index)
    for key in A.index:
        m = pick.get((key[2], cost_class(key[3])), "budget")
        F.loc[key] = per_method[m].loc[key].values
        method_used[key] = m
    F.columns.name = "month"
    long_a = A[done].stack().rename("amount_eur").reset_index().assign(kind="actual")
    long_f = F.stack().rename("amount_eur").reset_index().assign(kind="forecast")
    long_b = B[months].stack().rename("amount_eur").reset_index().assign(kind="budget")
    out = pd.concat([long_a, long_f, long_b], ignore_index=True)
    out["method"] = out.set_index(KEY).index.map(method_used).where(out["kind"] == "forecast", "")
    out["fiscal_year"] = fy
    out["period"] = out["month"].map(fiscal_period)
    return out


def revenue_forecast(tables, fy: str | None = None, cutoff: int | None = None) -> pd.DataFrame:
    """Per entity and crop: remaining budget units x YTD volume ratio (only once at least 15% of the
    season is in) x YTD price ratio."""
    fy = fy or fiscal_year(C.CLOSE_PERIOD)
    cutoff = cutoff or fiscal_period(C.CLOSE_PERIOD)
    s, b = tables["sales"], tables["revenue_budget"]
    s, b = s[s["fiscal_year"] == fy], b[b["fiscal_year"] == fy]
    rows = []
    for (entity, crop), bud in b.groupby(["company_code", "crop"]):
        act = s[(s["company_code"] == entity) & (s["crop"] == crop) & (s["period"] <= cutoff)]
        bud_ytd = bud[bud["period"] <= cutoff]
        share = bud_ytd["units"].sum() / bud["units"].sum()
        vol_ratio = act["units"].sum() / bud_ytd["units"].sum() if share >= 0.15 and bud_ytd["units"].sum() else 1.0
        price_a = act["revenue_eur"].sum() / act["units"].sum() if act["units"].sum() else np.nan
        price_b = bud_ytd["revenue_eur"].sum() / bud_ytd["units"].sum() if bud_ytd["units"].sum() else np.nan
        price_ratio = price_a / price_b if np.isfinite(price_a) and np.isfinite(price_b) else 1.0
        for r in bud[bud["period"] > cutoff].itertuples():
            rows.append({"company_code": entity, "crop": crop, "month": r.month, "period": r.period,
                         "units": r.units * vol_ratio, "revenue_eur": r.revenue_eur * vol_ratio * price_ratio,
                         "volume_ratio": round(vol_ratio, 3), "price_ratio": round(price_ratio, 3)})
    f = pd.DataFrame(rows)
    a = s[s["period"] <= cutoff][["company_code", "crop", "month", "period", "units", "revenue_eur"]]
    return pd.concat([a.assign(kind="actual"), f.assign(kind="forecast"),
                      b[["company_code", "crop", "month", "period", "units", "revenue_eur"]].assign(kind="budget")],
                     ignore_index=True)


def landing(tables, cost_fc: pd.DataFrame, rev_fc: pd.DataFrame) -> pd.DataFrame:
    """Full-year outlook by line vs budget and prior year (group view, intercompany eliminated)."""
    fy = cost_fc["fiscal_year"].iloc[0]
    pyfy = f"{int(fy[:4]) - 1}/{fy[2:4]}"
    act = actual_costs(tables)
    act_py = act[(act["fiscal_year"] == pyfy) & (act["gl_account"] != "6950")]
    c = cost_fc[cost_fc["gl_account"] != "6950"]
    rows = []
    rv = rev_fc
    rows.append(("Revenue", rv[rv["kind"] == "actual"]["revenue_eur"].sum(), rv[rv["kind"] == "forecast"]["revenue_eur"].sum(),
                 rv[rv["kind"] == "budget"]["revenue_eur"].sum(),
                 tables["sales"][tables["sales"]["fiscal_year"] == pyfy]["revenue_eur"].sum()))
    for fa in ["COS", "SEL", "RND", "GNA"]:
        g = c[c["functional_area"] == fa]
        rows.append((C.FUNCTIONAL_AREAS[fa], -g[g["kind"] == "actual"]["amount_eur"].sum(),
                     -g[g["kind"] == "forecast"]["amount_eur"].sum(), -g[g["kind"] == "budget"]["amount_eur"].sum(),
                     -act_py[act_py["functional_area"] == fa]["actual_eur"].sum()))
    df = pd.DataFrame(rows, columns=["line", "actual_ytd", "forecast_rest", "budget_fy", "prior_year_fy"])
    total = df[["actual_ytd", "forecast_rest", "budget_fy", "prior_year_fy"]].sum()
    df.loc[len(df)] = ["EBIT", *total]
    df.insert(3, "outlook_fy", df["actual_ytd"] + df["forecast_rest"])
    df["var_vs_budget_eur"] = df["outlook_fy"] - df["budget_fy"]
    df["var_vs_budget_pct"] = df["var_vs_budget_eur"] / df["budget_fy"].abs()
    return df.round({"actual_ytd": 0, "forecast_rest": 0, "outlook_fy": 0, "budget_fy": 0, "prior_year_fy": 0,
                     "var_vs_budget_eur": 0, "var_vs_budget_pct": 4})


def capex_forecast(tables, month: str = C.CLOSE_PERIOD) -> pd.DataFrame:
    """Per project: FY outlook and estimate at completion (EAC). Remaining spend is the larger of the
    remaining plan and the open orders."""
    gl = tables["gl_items"]
    plan = tables["capex_plan"]
    com = tables["capex_commitments"].set_index("wbs")["open_po_eur"]
    fy = fiscal_year(month)
    rows = []
    for wbs, p in plan.groupby("wbs"):
        budget = p["approved_budget_eur"].iloc[0]
        actual_to_date = gl[(gl["wbs"] == wbs) & (gl["month"] <= month)]["amount_eur"].sum()
        actual_fy = gl[(gl["wbs"] == wbs) & (gl["month"] <= month) & (gl["fiscal_year"] == fy)]["amount_eur"].sum()
        rest_plan = p[p["month"] > month]["planned_eur"].sum()
        rest_plan_fy = p[(p["month"] > month) & (p["fiscal_year"] == fy)]["planned_eur"].sum()
        committed = com.get(wbs, 0.0)
        remaining = max(rest_plan, committed)
        rest_fy = max(rest_plan_fy, min(committed, remaining))
        rows.append({"wbs": wbs, "description": p["description"].iloc[0], "approved_budget_eur": budget,
                     "actual_to_date_eur": actual_to_date, "open_commitments_eur": committed,
                     "eac_eur": actual_to_date + remaining, "eac_vs_budget_pct": (actual_to_date + remaining) / budget - 1,
                     "plan_fy_eur": p[p["fiscal_year"] == fy]["planned_eur"].sum(), "actual_fy_ytd_eur": actual_fy,
                     "outlook_fy_eur": actual_fy + rest_fy})
    return pd.DataFrame(rows).round({"actual_to_date_eur": 2, "eac_eur": 0, "eac_vs_budget_pct": 3,
                                     "plan_fy_eur": 0, "actual_fy_ytd_eur": 2, "outlook_fy_eur": 0})
