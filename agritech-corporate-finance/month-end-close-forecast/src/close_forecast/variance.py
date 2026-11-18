"""Budget vs actual vs prior year, revenue price-volume analysis, and variance drill-down."""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as C
from .fiscal import fiscal_period, fiscal_year

KEYS = ["company_code", "cost_center", "functional_area", "gl_account"]


def actual_costs(tables) -> pd.DataFrame:
    """Expense lines by cost center, account and month (intercompany charges included, as in the entity view)."""
    gl = tables["gl_items"]
    types = dict(zip(tables["gl_accounts"]["gl_account"], tables["gl_accounts"]["account_type"]))
    exp = gl[gl["gl_account"].map(types).isin(["EXP", "EXP_IC"])]
    return exp.groupby(["fiscal_year", "period", "month"] + KEYS, as_index=False)["amount_eur"].sum().rename(
        columns={"amount_eur": "actual_eur"})


def _prior_year(month: str) -> str:
    return (pd.Period(month, freq="M") - 12).strftime("%Y-%m")


def bva(tables, month: str = C.CLOSE_PERIOD, by: list[str] | None = None) -> pd.DataFrame:
    """Month and fiscal-year-to-date actual vs budget vs prior year, at the level given by `by`."""
    by = by or ["functional_area"]
    fy, per = fiscal_year(month), fiscal_period(month)
    py_month = _prior_year(month)
    pyfy = fiscal_year(py_month)
    act = actual_costs(tables)
    bud = tables["budget"]

    def agg(df, value, fyear, cond):
        d = df[(df["fiscal_year"] == fyear) & cond(df["period"])]
        return d.groupby(by)[value].sum()

    out = pd.DataFrame({
        "actual_month": agg(act, "actual_eur", fy, lambda p: p == per),
        "budget_month": agg(bud, "budget_eur", fy, lambda p: p == per),
        "actual_ytd": agg(act, "actual_eur", fy, lambda p: p <= per),
        "budget_ytd": agg(bud, "budget_eur", fy, lambda p: p <= per),
        "prior_year_ytd": agg(act, "actual_eur", pyfy, lambda p: p <= per),
        "budget_full_year": agg(bud, "budget_eur", fy, lambda p: p > 0),
    }).fillna(0.0)
    out["var_month_eur"] = out["actual_month"] - out["budget_month"]
    out["var_ytd_eur"] = out["actual_ytd"] - out["budget_ytd"]
    out["var_ytd_pct"] = np.where(out["budget_ytd"] != 0, out["var_ytd_eur"] / out["budget_ytd"], np.nan)
    out["vs_prior_year_pct"] = np.where(out["prior_year_ytd"] != 0, out["actual_ytd"] / out["prior_year_ytd"] - 1, np.nan)
    out["flag"] = (out["var_ytd_pct"].abs() > C.VARIANCE_THRESHOLD_PCT) & (out["var_ytd_eur"].abs() > C.VARIANCE_THRESHOLD_EUR)
    return out.round(2).reset_index()


def flagged_cost_centers(tables, month: str = C.CLOSE_PERIOD) -> pd.DataFrame:
    cc = bva(tables, month, by=["company_code", "cost_center", "functional_area"])
    names = dict(zip(tables["cost_centers"]["cost_center"], tables["cost_centers"]["cost_center_name"]))
    cc.insert(2, "cost_center_name", cc["cost_center"].map(names))
    return cc[cc["flag"]].sort_values("var_ytd_eur", key=abs, ascending=False)


def account_drivers(tables, cost_center: str, month: str = C.CLOSE_PERIOD) -> pd.DataFrame:
    """Which accounts drive a cost center's YTD variance."""
    d = bva(tables, month, by=["cost_center", "gl_account"])
    d = d[d["cost_center"] == cost_center].copy()
    groups = C.ACCOUNT_GROUPS | {"6000": "Personnel"}
    d.insert(2, "account_group", d["gl_account"].map(groups))
    return d.sort_values("var_ytd_eur", key=abs, ascending=False)


def top_documents(tables, cost_center: str, gl_account: str, month: str = C.CLOSE_PERIOD, n: int = 5) -> pd.DataFrame:
    gl = tables["gl_items"]
    fy = fiscal_year(month)
    d = gl[(gl["fiscal_year"] == fy) & (gl["month"] <= month) & (gl["cost_center"] == cost_center)
           & (gl["gl_account"] == gl_account)]
    return d.nlargest(n, "amount_eur")[["month", "doc_no", "doc_type", "posting_date", "vendor", "amount_eur", "text", "user_id"]]


def find_misallocations(tables, month: str = C.CLOSE_PERIOD, min_amount: float = 100_000) -> pd.DataFrame:
    """Large single postings that push their cost center far over budget for the month while
    another cost center of the same company has the same amount unspent on the same account.
    That pattern is the usual sign of a booking on the wrong cost center."""
    gl = tables["gl_items"]
    act = actual_costs(tables)
    act = act[act["month"] == month].groupby(["company_code", "cost_center", "gl_account"])["actual_eur"].sum()
    bud = tables["budget"]
    bud = bud[bud["month"] == month].groupby(["company_code", "cost_center", "gl_account"])["budget_eur"].sum()
    gap = act.sub(bud, fill_value=0.0)  # positive = over budget this month
    big = gl[(gl["month"] == month) & (gl["amount_eur"] >= min_amount) & (gl["cost_center"] != "")
             & (gl["doc_type"] == "KR")]
    names = dict(zip(tables["cost_centers"]["cost_center"], tables["cost_centers"]["cost_center_name"]))
    rows = []
    for r in big.itertuples():
        if gap.get((r.company_code, r.cost_center, r.gl_account), 0.0) < 0.8 * r.amount_eur:
            continue
        cands = gap[(gap.index.get_level_values(0) == r.company_code) & (gap.index.get_level_values(2) == r.gl_account)
                    & (gap < -0.8 * r.amount_eur)]
        cands = cands[[i[1] != r.cost_center for i in cands.index]]
        if cands.empty:
            continue
        target = cands.idxmin()[1]
        area = dict(zip(tables["cost_centers"]["cost_center"], tables["cost_centers"]["functional_area"]))
        rows.append({"doc_no": r.doc_no, "text": r.text, "gl_account": r.gl_account, "amount_eur": r.amount_eur,
                     "booked_cost_center": f"{r.cost_center} {names.get(r.cost_center, '')}", "booked_area": area.get(r.cost_center),
                     "proposed_cost_center": f"{target} {names.get(target, '')}", "proposed_area": area.get(target),
                     "unspent_budget_there_eur": round(-float(cands.min()), 2)})
    return pd.DataFrame(rows)


def flagged_lines(tables, month: str = C.CLOSE_PERIOD) -> pd.DataFrame:
    """Cost center x account combinations over both thresholds (YTD)."""
    d = bva(tables, month, by=["company_code", "cost_center", "functional_area", "gl_account"])
    names = dict(zip(tables["cost_centers"]["cost_center"], tables["cost_centers"]["cost_center_name"]))
    groups = C.ACCOUNT_GROUPS | {"6000": "Personnel"}
    d.insert(2, "cost_center_name", d["cost_center"].map(names))
    d.insert(5, "account_group", d["gl_account"].map(groups))
    return d[d["flag"]].sort_values("var_ytd_eur", key=abs, ascending=False).reset_index(drop=True)


def price_volume(tables, month: str = C.CLOSE_PERIOD, ytd: bool = True) -> pd.DataFrame:
    """Revenue variance per crop split into volume and price effects.

    Volume effect = (actual units - budget units) x budget price
    Price effect  = (actual price - budget price) x actual units
    The two add up to the total variance. A mix effect across crops is left out on
    purpose: the crops are sold in different units (seed units, dt, kg), so a
    group-level average price would mean nothing.
    """
    fy, per = fiscal_year(month), fiscal_period(month)
    cond = (lambda p: p <= per) if ytd else (lambda p: p == per)
    s = tables["sales"]
    b = tables["revenue_budget"]
    a = s[(s["fiscal_year"] == fy) & cond(s["period"])].groupby("crop")[["units", "revenue_eur"]].sum()
    p = b[(b["fiscal_year"] == fy) & cond(b["period"])].groupby("crop")[["units", "revenue_eur"]].sum()
    df = a.join(p, lsuffix="_actual", rsuffix="_budget", how="outer").fillna(0.0)
    df["price_actual"] = np.where(df["units_actual"] > 0, df["revenue_eur_actual"] / df["units_actual"], 0)
    df["price_budget"] = np.where(df["units_budget"] > 0, df["revenue_eur_budget"] / df["units_budget"], 0)
    df["volume_effect_eur"] = (df["units_actual"] - df["units_budget"]) * df["price_budget"]
    df["price_effect_eur"] = (df["price_actual"] - df["price_budget"]) * df["units_actual"]
    df["total_variance_eur"] = df["revenue_eur_actual"] - df["revenue_eur_budget"]
    df["units_vs_budget_pct"] = np.where(df["units_budget"] > 0, df["units_actual"] / df["units_budget"] - 1, np.nan)
    df["price_vs_budget_pct"] = np.where(df["price_budget"] > 0, df["price_actual"] / df["price_budget"] - 1, np.nan)
    return df.round(2).reset_index()


def income_statement(tables, month: str = C.CLOSE_PERIOD) -> pd.DataFrame:
    """Group P&L by function (cost of sales method), YTD actual vs budget vs prior year.
    Intercompany income and charges are eliminated."""
    fy, per = fiscal_year(month), fiscal_period(month)
    pyfy = fiscal_year(_prior_year(month))
    s = tables["sales"]
    rb = tables["revenue_budget"]
    act = actual_costs(tables)
    act = act[act["gl_account"] != "6950"]
    bud = tables["budget"]
    bud = bud[bud["gl_account"] != "6950"]

    def rev(df, f):
        return df[(df["fiscal_year"] == f) & (df["period"] <= per)]["revenue_eur"].sum()

    def cost(df, col, f, fa):
        return df[(df["fiscal_year"] == f) & (df["period"] <= per) & (df["functional_area"] == fa)][col].sum()

    rows = [("Revenue", rev(s, fy), rev(rb, fy), rev(s, pyfy))]
    for fa in ["COS", "SEL", "RND", "GNA"]:
        rows.append((C.FUNCTIONAL_AREAS[fa], -cost(act, "actual_eur", fy, fa), -cost(bud, "budget_eur", fy, fa),
                     -cost(act, "actual_eur", pyfy, fa)))
    df = pd.DataFrame(rows, columns=["line", "actual_ytd", "budget_ytd", "prior_year_ytd"])
    unassigned = act[(act["fiscal_year"] == fy) & (act["period"] <= per) & (act["functional_area"] == "")]["actual_eur"].sum()
    if unassigned:
        df.loc[len(df)] = ["Not assigned (missing cost center)", -unassigned, 0.0, 0.0]
    gross = df.iloc[:2][["actual_ytd", "budget_ytd", "prior_year_ytd"]].sum()
    ebit = df[["actual_ytd", "budget_ytd", "prior_year_ytd"]].sum()
    df = pd.concat([df.iloc[:2], pd.DataFrame([["Gross profit", *gross]], columns=df.columns), df.iloc[2:],
                    pd.DataFrame([["EBIT", *ebit]], columns=df.columns)], ignore_index=True)
    df["var_vs_budget_eur"] = df["actual_ytd"] - df["budget_ytd"]
    return df.round(0)


def commentary(tables, month: str = C.CLOSE_PERIOD, checks=None) -> pd.DataFrame:
    """One comment per flagged cost center x account, tied to the close checks where they explain it."""
    from . import close_checks as cc
    checks = checks if checks is not None else cc.run_close_checks(tables, month)
    by_id = {c.check_id: c for c in checks}
    mis = find_misallocations(tables, month)
    rows = []
    for r in flagged_lines(tables, month).itertuples():
        direction = "over" if r.var_ytd_eur > 0 else "under"
        cause, action = "", ""
        miss = by_id["C07"].exceptions
        dup = by_id["C05"].exceptions
        if not mis.empty and (mis["booked_cost_center"].str.startswith(r.cost_center).any()
                              or mis["proposed_cost_center"].str.startswith(r.cost_center).any()) and r.gl_account in set(mis["gl_account"]):
            m = mis.iloc[0]
            cause = f"Document {m.doc_no} ({m.text}) booked on {m.booked_cost_center}, budgeted on {m.proposed_cost_center}"
            action = "Reclass to the budgeted cost center"
        elif not miss.empty and ((miss["gl_account"] == r.gl_account) & (miss["company_code"] == r.company_code)
                                 & miss["cost_center"].isin([r.cost_center, "all"])).any():
            cause = "Recurring posting missing this month (check C07)"
            action = "Post the missing entry before the close"
        elif not dup.empty and r.gl_account == "6500" and (dup["company_code"] == r.company_code).any() and r.cost_center == "4120":
            cause = f"Includes a duplicate vendor invoice {dup.iloc[0]['reference']} (check C05); the rest is cloud usage above plan"
            action = "Reverse the second invoice and block the payment"
        elif r.gl_account == "6800":
            cause = "Energy prices above the planning assumption"
            action = "Forecast item; review the hedge and tariff assumptions"
        elif r.gl_account == "6000":
            cause = "Headcount below plan"
            action = "Forecast item; confirm hiring timeline with HR"
        rows.append({"cost_center": r.cost_center, "cost_center_name": r.cost_center_name, "account": r.account_group,
                     "var_ytd_eur": r.var_ytd_eur, "var_ytd_pct": r.var_ytd_pct,
                     "direction": direction, "explanation": cause or "To be explained by the cost center owner",
                     "action": action or "Ask the owner"})
    return pd.DataFrame(rows)
