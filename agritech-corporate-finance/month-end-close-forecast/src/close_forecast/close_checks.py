"""Month-end close checks on the ledger extract.

Each check returns a CheckResult with the offending lines, so the close
checklist in the Excel pack and the notebook can show exactly what to fix.
The checks only read data; corrections are left to the accountant, as they
would be in a real close.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from . import config as C
from .fiscal import cutoff_date, month_end

EXPENSE_TYPES = {"EXP", "EXP_IC"}


@dataclass
class CheckResult:
    check_id: str
    name: str
    area: str
    owner: str
    severity: str           # high, medium, low
    exceptions: pd.DataFrame
    amount_eur: float = 0.0
    note: str = ""

    @property
    def status(self) -> str:
        if self.exceptions.empty:
            return "PASS"
        return "FAIL" if self.severity == "high" else "WARN"

    def summary(self) -> dict:
        return {"check_id": self.check_id, "check": self.name, "area": self.area, "owner": self.owner,
                "severity": self.severity, "status": self.status, "exceptions": len(self.exceptions),
                "amount_eur": round(self.amount_eur, 2), "note": self.note}


def _account_type(tables) -> dict:
    return dict(zip(tables["gl_accounts"]["gl_account"], tables["gl_accounts"]["account_type"]))


def month_lines(tables, month: str) -> pd.DataFrame:
    gl = tables["gl_items"]
    return gl[gl["month"] == month].copy()


# ---------------------------------------------------------------------------- checks
def check_balanced_documents(tables, month) -> CheckResult:
    lines = month_lines(tables, month)
    sums = lines.groupby(["company_code", "doc_no", "doc_type", "text"], as_index=False)["amount_eur"].sum()
    bad = sums[sums["amount_eur"].round(2) != 0].rename(columns={"amount_eur": "difference_eur"})
    return CheckResult("C01", "Every document balances (debit = credit)", "Ledger integrity", "General ledger",
                       "high", bad, float(bad["difference_eur"].abs().sum()))


def check_blocked_cost_centers(tables, month) -> CheckResult:
    cc = tables["cost_centers"]
    blocked = set(cc.loc[cc["blocked"].astype(str) == "True", "cost_center"])
    lines = month_lines(tables, month)
    bad = lines[lines["cost_center"].isin(blocked)]
    return CheckResult("C02", "No postings on blocked cost centers", "Cost accounting", "Controlling",
                       "high", bad[["company_code", "doc_no", "gl_account", "cost_center", "amount_eur", "text"]],
                       float(bad["amount_eur"].abs().sum()))


def check_cost_center_entity(tables, month) -> CheckResult:
    owner = dict(zip(tables["cost_centers"]["cost_center"], tables["cost_centers"]["company_code"]))
    lines = month_lines(tables, month)
    lines = lines[lines["cost_center"] != ""]
    lines = lines.assign(cost_center_entity=lines["cost_center"].map(owner))
    bad = lines[lines["cost_center_entity"] != lines["company_code"]]
    return CheckResult("C03", "Cost center belongs to the posting company", "Cost accounting", "Controlling",
                       "high", bad[["company_code", "doc_no", "gl_account", "cost_center", "cost_center_entity",
                                    "amount_eur", "text"]], float(bad["amount_eur"].abs().sum()))


def check_missing_cost_center(tables, month) -> CheckResult:
    types = _account_type(tables)
    lines = month_lines(tables, month)
    bad = lines[lines["gl_account"].map(types).isin(EXPENSE_TYPES) & (lines["cost_center"] == "")]
    return CheckResult("C04", "Expense lines carry a cost center", "Cost accounting", "Controlling",
                       "high", bad[["company_code", "doc_no", "gl_account", "amount_eur", "vendor", "text"]],
                       float(bad["amount_eur"].abs().sum()))


def check_duplicate_invoices(tables, month) -> CheckResult:
    gl = tables["gl_items"]
    ap = gl[(gl["gl_account"] == "3300") & (gl["reference"] != "") & (gl["doc_type"] == "KR")]
    keys = ["company_code", "vendor", "reference", "amount_eur"]
    dup = ap[ap.duplicated(keys, keep=False)]
    dup = dup[dup.groupby(keys)["month"].transform("max") == month]
    out = dup[["company_code", "doc_no", "vendor", "reference", "posting_date", "amount_eur", "text"]].assign(
        amount_eur=lambda d: -d["amount_eur"])
    # Exposure is every copy after the first one.
    exposure = float(out.groupby(["company_code", "vendor", "reference"])["amount_eur"].apply(lambda s: s.sum() - s.iloc[0]).sum()) if not out.empty else 0.0
    return CheckResult("C05", "No duplicate vendor invoices", "Accounts payable", "Accounts payable",
                       "high", out, exposure, "Same vendor, invoice reference and amount")


def check_cutoff(tables, month) -> CheckResult:
    limit = cutoff_date(month, C.CUTOFF_WORKING_DAY).isoformat()
    lines = month_lines(tables, month)
    docs = lines.groupby(["company_code", "doc_no", "doc_type", "entry_date", "text"], as_index=False)["amount_eur"].apply(
        lambda s: s[s > 0].sum())
    bad = docs[docs["entry_date"] > limit]
    return CheckResult("C06", f"Entries made by working day {C.CUTOFF_WORKING_DAY} ({limit})", "Close calendar",
                       "General ledger", "medium", bad, float(bad["amount_eur"].sum()),
                       "Posted into the closed month after the cut-off; move to next period or reopen with approval")


def check_recurring_postings(tables, month) -> CheckResult:
    reg = tables["recurring_register"]
    lines = month_lines(tables, month)
    missing = []
    for r in reg.itertuples():
        hit = lines[(lines["company_code"] == r.company_code) & (lines["gl_account"] == r.gl_account)
                    & (lines["doc_type"] == r.doc_type)]
        if r.cost_center != "*":
            hit = hit[hit["cost_center"] == r.cost_center]
        if r.kind.startswith("IC "):
            charge = r.kind[3:].split(" to ")[0]
            hit = hit[hit["text"].str.contains(charge, regex=False)]
            if " to " in r.kind:
                hit = hit[hit["partner_company"] == r.kind.split(" to ")[1]]
        if hit.empty:
            missing.append({"company_code": r.company_code, "posting": r.kind, "gl_account": r.gl_account,
                            "cost_center": r.cost_center if r.cost_center != "*" else "all"})
    bad = pd.DataFrame(missing, columns=["company_code", "posting", "gl_account", "cost_center"])
    # Rough size of what is missing: last month's amount for the same posting.
    est = 0.0
    if not bad.empty:
        prev = tables["gl_items"]
        prev_month = (pd.Period(month, freq="M") - 1).strftime("%Y-%m")
        prev = prev[prev["month"] == prev_month]
        amounts = []
        for r in bad.itertuples():
            p = prev[(prev["company_code"] == r.company_code) & (prev["gl_account"] == r.gl_account)]
            if r.cost_center != "all":
                p = p[p["cost_center"] == r.cost_center]
            if r.posting.startswith("IC "):
                p = p[p["text"].str.contains(r.posting[3:].split(" to ")[0], regex=False)]
            amounts.append(round(float(p["amount_eur"].abs().sum()), 2))
        bad["last_month_eur"] = amounts
        est = float(sum(amounts))
    return CheckResult("C07", "Recurring postings complete (payroll, depreciation, rent, IC)", "Close calendar",
                       "General ledger", "high", bad, est, "Estimated from last month")


def intercompany_matrix(tables, month) -> pd.DataFrame:
    """Cumulative IC balances by pair: DE10 receivable vs partner payable, and income vs charges this month."""
    gl = tables["gl_items"]
    gl = gl[gl["month"] <= month]
    rows = []
    for partner in C.IC_CHARGES:
        recv = gl[(gl["company_code"] == "DE10") & (gl["gl_account"] == "1400") & (gl["partner_company"] == partner)]["amount_eur"].sum()
        pay = gl[(gl["company_code"] == partner) & (gl["gl_account"] == "3400") & (gl["partner_company"] == "DE10")]["amount_eur"].sum()
        inc = gl[(gl["month"] == month) & (gl["company_code"] == "DE10") & (gl["gl_account"] == "4800") & (gl["partner_company"] == partner)]["amount_eur"].sum()
        chg = gl[(gl["month"] == month) & (gl["company_code"] == partner) & (gl["gl_account"] == "6950") & (gl["partner_company"] == "DE10")]["amount_eur"].sum()
        rows.append({"pair": f"DE10-{partner}", "DE10_receivable_eur": round(recv, 2), f"partner_payable_eur": round(-pay, 2),
                     "balance_difference_eur": round(recv + pay, 2), "month_income_eur": round(-inc, 2),
                     "month_charge_eur": round(chg, 2), "month_difference_eur": round(-inc - chg, 2)})
    return pd.DataFrame(rows)


def check_intercompany(tables, month) -> CheckResult:
    m = intercompany_matrix(tables, month)
    bad = m[m["balance_difference_eur"].abs() > 0.01]
    return CheckResult("C08", "Intercompany balances agree by partner", "Intercompany", "Group accounting",
                       "high", bad, float(bad["balance_difference_eur"].abs().sum()))


def grir_open_items(tables, month) -> pd.DataFrame:
    gl = tables["gl_items"]
    g = gl[(gl["gl_account"] == "3310") & (gl["month"] <= month) & (gl["po_number"] != "")]
    agg = g.groupby(["company_code", "po_number"], as_index=False).agg(
        open_eur=("amount_eur", "sum"), first_receipt=("posting_date", "min"))
    agg = agg[agg["open_eur"].round(2) != 0].copy()
    agg["open_eur"] = -agg["open_eur"]
    agg["age_days"] = (pd.Timestamp(month_end(month)) - pd.to_datetime(agg["first_receipt"])).dt.days
    return agg.sort_values("age_days", ascending=False)


def check_grir(tables, month, max_age_days: int = 60) -> CheckResult:
    items = grir_open_items(tables, month)
    bad = items[items["age_days"] > max_age_days]
    return CheckResult("C09", f"GR/IR items older than {max_age_days} days", "Accounts payable", "Procurement / AP",
                       "medium", bad, float(bad["open_eur"].sum()),
                       f"{len(items)} open receipts in total; older ones need an invoice chase or an accrual review")


def check_suspense(tables, month) -> CheckResult:
    gl = tables["gl_items"]
    g = gl[(gl["gl_account"] == "1990") & (gl["month"] <= month)]
    bal = g.groupby("company_code", as_index=False)["amount_eur"].sum()
    bad = bal[bal["amount_eur"].round(2) != 0].rename(columns={"amount_eur": "balance_eur"})
    return CheckResult("C10", "Suspense account cleared to zero", "Ledger integrity", "General ledger",
                       "medium", bad, float(bad["balance_eur"].abs().sum()))


def check_billing_vs_gl(tables, month) -> CheckResult:
    s = tables["sales"]
    s = s[s["month"] == month].groupby(["company_code", "gl_account"], as_index=False)["revenue_eur"].sum()
    gl = month_lines(tables, month)
    g = gl[gl["gl_account"].isin(s["gl_account"].unique())].groupby(["company_code", "gl_account"], as_index=False)["amount_eur"].sum()
    g["gl_revenue_eur"] = -g["amount_eur"]
    m = s.merge(g[["company_code", "gl_account", "gl_revenue_eur"]], how="outer").fillna(0)
    m["difference_eur"] = (m["revenue_eur"] - m["gl_revenue_eur"]).round(2)
    bad = m[m["difference_eur"].abs() > 0.01]
    return CheckResult("C11", "Billing extract agrees with revenue in the ledger", "Revenue", "Controlling",
                       "high", bad, float(bad["difference_eur"].abs().sum()))


def capex_status(tables, month) -> pd.DataFrame:
    gl = tables["gl_items"]
    actual = gl[(gl["wbs"] != "") & (gl["month"] <= month)].groupby("wbs")["amount_eur"].sum()
    plan = tables["capex_plan"]
    plan_to_date = plan[plan["month"] <= month].groupby("wbs")["planned_eur"].sum()
    budget = plan.groupby("wbs")["approved_budget_eur"].first()
    desc = plan.groupby("wbs")["description"].first()
    com = tables["capex_commitments"].set_index("wbs")["open_po_eur"]
    df = pd.DataFrame({"description": desc, "approved_budget_eur": budget, "plan_to_date_eur": plan_to_date,
                       "actual_to_date_eur": actual, "open_commitments_eur": com}).fillna(0)
    df["actual_plus_committed_eur"] = df["actual_to_date_eur"] + df["open_commitments_eur"]
    df["share_of_budget"] = (df["actual_plus_committed_eur"] / df["approved_budget_eur"]).round(3)
    return df.round(2).reset_index().rename(columns={"index": "wbs"})


def check_capex(tables, month) -> CheckResult:
    st = capex_status(tables, month)
    bad = st[st["share_of_budget"] > C.CAPEX_OVERRUN_LIMIT]
    over = float((bad["actual_plus_committed_eur"] - bad["approved_budget_eur"]).sum())
    return CheckResult("C12", f"Capex projects within {C.CAPEX_OVERRUN_LIMIT:.0%} of approved budget", "Investments",
                       "Controlling", "medium", bad, over, "Needs a budget supplement request before new orders")


ALL_CHECKS = [check_balanced_documents, check_blocked_cost_centers, check_cost_center_entity, check_missing_cost_center,
              check_duplicate_invoices, check_cutoff, check_recurring_postings, check_intercompany, check_grir,
              check_suspense, check_billing_vs_gl, check_capex]


def run_close_checks(tables, month: str = C.CLOSE_PERIOD) -> list[CheckResult]:
    return [check(tables, month) for check in ALL_CHECKS]


def checklist(results: list[CheckResult]) -> pd.DataFrame:
    return pd.DataFrame([r.summary() for r in results])


def trial_balance(tables, month: str = C.CLOSE_PERIOD) -> pd.DataFrame:
    """Balance sheet cumulative, P&L fiscal year to date, by entity and account."""
    from .fiscal import fiscal_year
    gl = tables["gl_items"]
    types = _account_type(tables)
    fy = fiscal_year(month)
    gl = gl[gl["month"] <= month]
    is_bs = gl["gl_account"].map(types) == "BS"
    scope = gl[is_bs | (gl["fiscal_year"] == fy)]
    tb = scope.groupby(["company_code", "gl_account"], as_index=False)["amount_eur"].sum()
    # Prior years' profit and loss sits in retained earnings once those years are closed.
    prior = gl[~is_bs & (gl["fiscal_year"] < fy)].groupby("company_code", as_index=False)["amount_eur"].sum()
    prior["gl_account"] = "2970"
    tb = pd.concat([tb, prior], ignore_index=True).sort_values(["company_code", "gl_account"])
    names = dict(zip(tables["gl_accounts"]["gl_account"], tables["gl_accounts"]["account_name"]))
    names["2970"] = "Retained earnings (prior years)"
    tb.insert(2, "account_name", tb["gl_account"].map(names))
    tb["amount_eur"] = tb["amount_eur"].round(2)
    return tb


def proposed_adjustments(tables, results: list[CheckResult] | None = None, month: str = C.CLOSE_PERIOD) -> pd.DataFrame:
    """Correcting entries the checks suggest, P&L side only (cost center and account).

    These are proposals for the accountant, not postings. The forecast is built on
    actuals after these corrections, so known close errors do not leak into the outlook.
    """
    from .variance import find_misallocations
    results = results if results is not None else run_close_checks(tables, month)
    by_id = {r.check_id: r for r in results}
    gl = tables["gl_items"]
    cc_master = tables["cost_centers"].set_index("cost_center")
    prev_month = (pd.Period(month, freq="M") - 1).strftime("%Y-%m")
    prev = gl[gl["month"] == prev_month]
    rows = []

    def add(check_id, entity, cc, account, amount, text):
        fa = cc_master.loc[cc, "functional_area"] if cc in cc_master.index else ""
        rows.append({"check_id": check_id, "company_code": entity, "cost_center": cc, "functional_area": fa,
                     "gl_account": account, "amount_eur": round(float(amount), 2), "description": text})

    for r in by_id["C07"].exceptions.itertuples():
        p = prev[(prev["company_code"] == r.company_code) & (prev["gl_account"] == r.gl_account) & (prev["cost_center"] != "")]
        if r.cost_center != "all":
            p = p[p["cost_center"] == r.cost_center]
        if r.posting.startswith("IC "):
            p = p[p["text"].str.contains(r.posting[3:].split(" to ")[0], regex=False)]
        for (cc, acct), amt in p.groupby(["cost_center", "gl_account"])["amount_eur"].sum().items():
            add("C07", r.company_code, cc, acct, amt, f"Post missing {r.posting} (estimate: last month)")

    dup = by_id["C05"].exceptions
    if not dup.empty:
        second = dup.sort_values("posting_date").iloc[1:]
        for d in second.itertuples():
            line = gl[(gl["doc_no"] == d.doc_no) & (gl["company_code"] == d.company_code) & (gl["cost_center"] != "")].iloc[0]
            add("C05", d.company_code, line["cost_center"], line["gl_account"], -line["amount_eur"],
                f"Reverse duplicate invoice {d.reference}")

    for d in by_id["C02"].exceptions.itertuples():
        add("C02", d.company_code, d.cost_center, d.gl_account, -d.amount_eur, "Move off blocked cost center")
        add("C02", d.company_code, "4100", d.gl_account, d.amount_eur, "Rebook on successor cost center 4100")

    for d in by_id["C03"].exceptions.itertuples():
        own = cc_master[(cc_master["company_code"] == d.company_code) & (cc_master["functional_area"] == "SEL") & (~cc_master["blocked"].astype(str).eq("True"))]
        target = "2120" if "2120" in own.index else own.index[0]
        add("C03", d.company_code, d.cost_center, d.gl_account, -d.amount_eur, f"Remove {d.cost_center_entity} cost center from {d.company_code} posting")
        add("C03", d.company_code, target, d.gl_account, d.amount_eur, "Rebook on own selling cost center")

    default_gna = {"DE10": "4100", "AT10": "4200", "FR10": "4300"}
    for d in by_id["C04"].exceptions.itertuples():
        add("C04", d.company_code, default_gna[d.company_code], d.gl_account, d.amount_eur,
            "Assign cost center (pending confirmation from requester)")
        # The original line had no cost center; the negative side clears the unassigned bucket.
        rows.append({"check_id": "C04", "company_code": d.company_code, "cost_center": "", "functional_area": "",
                     "gl_account": d.gl_account, "amount_eur": -d.amount_eur, "description": "Clear unassigned line"})

    mis = find_misallocations(tables, month)
    for m in mis.itertuples():
        add("VAR", "DE10", m.booked_cost_center.split()[0], m.gl_account, -m.amount_eur, f"Reclass {m.text}")
        add("VAR", "DE10", m.proposed_cost_center.split()[0], m.gl_account, m.amount_eur, f"Reclass {m.text}")

    df = pd.DataFrame(rows)
    df.insert(0, "month", month)
    return df
