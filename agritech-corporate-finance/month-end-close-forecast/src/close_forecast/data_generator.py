"""Generate a synthetic ledger that looks like an SAP line-item export.

Output tables (all EUR, debit positive and credit negative, as in ACDOCA):

    gl_items           every posted line, July 2024 to the closing month
    budget             cost budget by cost center, account and month
    revenue_budget     units, price and revenue by entity, crop and month
    sales              billed units and net revenue (the billing extract)
    headcount          actual and planned FTE by cost center and month
    capex_plan         approved phasing per capital project
    capex_commitments  open purchase orders per project at month end
    recurring_register postings the close expects every month
    cost_centers, gl_accounts, entities   master data

The expected value of every cost line comes from one function. The budget uses
it with the planning assumptions; actuals use it with noise and with what
really happened (energy prices, hiring delays, a dry autumn). The planted
close errors in config.PLANTED_CLOSE_ISSUES are added on top, in the closing
month only.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import config as C
from .fiscal import (cutoff_date, fiscal_period, fiscal_year, fy_index, month_end, month_range,
                     next_month, working_day)

# What happened in FY 2025/26 against its budget, so the forecast backtest has something to learn.
DRIFT_FY26 = {"energy": 1.10, "materials": 0.96, "selling_services": 1.07,
              "volume": {"sugarbeet": 1.02, "corn": 0.95, "cereals": 1.03, "vegetables": 0.98},
              "price": {"sugarbeet": 1.01, "corn": 0.99, "cereals": 1.00, "vegetables": 1.01}}

VOLUME_GROWTH = 0.04
FTE_GROWTH = 0.02
PRICE_GROWTH = 0.025


@dataclass
class Ledger:
    rows: list = field(default_factory=list)
    counters: dict = field(default_factory=dict)
    balances: dict = field(default_factory=dict)

    def post(self, entity: str, month: str, doc_type: str, posting_date: dt.date, entry_date: dt.date,
             user: str, lines: list[dict], text: str = "") -> str:
        n = self.counters.get(entity, 0) + 1
        self.counters[entity] = n
        prefix = {"DE10": 1, "AT10": 2, "FR10": 3}[entity]
        doc_no = f"{prefix}{n:09d}"
        for i, line in enumerate(lines, start=1):
            acct = line["gl_account"]
            cc = line.get("cost_center", "")
            fa = line.get("functional_area")
            if fa is None:
                fa = (C.COST_CENTERS.get(cc) or C.BLOCKED_COST_CENTERS.get(cc) or (None, ""))[1] if cc else ""
            key = (entity, acct)
            self.balances[key] = self.balances.get(key, 0.0) + float(line["amount"])
            self.rows.append({
                "company_code": entity,
                "fiscal_year": fiscal_year(month),
                "period": fiscal_period(month),
                "month": month,
                "doc_no": doc_no,
                "line_no": i,
                "doc_type": doc_type,
                "posting_date": posting_date.isoformat(),
                "entry_date": entry_date.isoformat(),
                "gl_account": acct,
                "cost_center": cc,
                "functional_area": fa,
                "wbs": line.get("wbs", ""),
                "partner_company": line.get("partner_company", ""),
                "vendor": line.get("vendor", ""),
                "reference": line.get("reference", ""),
                "po_number": line.get("po_number", ""),
                "crop": line.get("crop", ""),
                "quantity": line.get("quantity", 0.0),
                "amount_eur": round(float(line["amount"]), 2),
                "text": line.get("text", text),
                "user_id": user,
            })
        return doc_no

    def frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.rows)


class Generator:
    def __init__(self, seed: int = C.SEED):
        self.rng = np.random.default_rng(seed)
        self.ledger = Ledger()
        self.months = month_range(C.FIRST_PERIOD, C.CLOSE_PERIOD)
        self.budget_months = month_range("2024-07", "2027-06")
        self.vendors = [f"V{n:04d}" for n in range(100, 400)]
        self.users = [f"U{n:02d}" for n in range(1, 13)]
        self._ref = 10_000
        self._po = 4_500_000_000
        # Per cost center headcount drift: a slow random walk around plan.
        self.fte_walk = {cc: np.cumprod(1 + self.rng.normal(0, 0.006, len(self.budget_months)))
                         for cc in C.COST_CENTERS}

    # ------------------------------------------------------------------ expected values
    def fte(self, cc: str, month: str, plan: bool) -> float:
        fte0 = C.COST_CENTERS[cc][3]
        i = self.budget_months.index(month)
        value = fte0 * (1 + FTE_GROWTH) ** (i / 12)
        if plan:
            return round(value, 1)
        value *= self.fte_walk[cc][i]
        if fiscal_year(month) == "2026/27" and C.COST_CENTERS[cc][1] == "RND":
            value *= C.ACTUAL_DRIFT_FY27["fte_hiring_delay"]
        return round(value, 1)

    def personnel_cost(self, cc: str, month: str, plan: bool) -> float:
        cost_per_fte = C.COST_CENTERS[cc][4] * (1 + C.ANNUAL_PAY_RAISE) ** fy_index(month)
        bonus = 1.5 if int(month[5:]) == C.THIRTEENTH_SALARY_MONTH else 1.0
        return self.fte(cc, month, plan) * cost_per_fte * bonus

    def other_cost(self, cc: str, account: str, month: str, plan: bool) -> float:
        _, fa, _, _, _, base = C.COST_CENTERS[cc]
        share = C.COST_MIX[fa].get(account, 0.0)
        i = fy_index(month)
        value = base * share * (1 + C.NON_PERSONNEL_INFLATION) ** i
        if account not in C.FLAT_ACCOUNTS:
            value *= C.SEASON[fa][int(month[5:]) - 1]
        if account in ("5000", "6800") and fa == "COS":
            value *= (1 + VOLUME_GROWTH) ** i
        if not plan:
            fy = fiscal_year(month)
            if fy == "2025/26":
                if account == "6800":
                    value *= DRIFT_FY26["energy"]
                if account == "5000":
                    value *= DRIFT_FY26["materials"]
                if account == "6500" and fa == "SEL":
                    value *= DRIFT_FY26["selling_services"]
            elif fy == "2026/27":
                if account == "6800":
                    value *= C.ACTUAL_DRIFT_FY27["energy"]
        return value

    def units(self, entity: str, crop: str, month: str, plan: bool) -> float:
        annual = C.CROPS[crop][3] * C.ENTITIES[entity]["revenue_share"]
        season = C.CROP_SEASON[crop]
        value = annual * (1 + VOLUME_GROWTH) ** fy_index(month) * season[int(month[5:]) - 1] / sum(season)
        if not plan:
            fy = fiscal_year(month)
            if fy == "2025/26":
                value *= DRIFT_FY26["volume"][crop]
            elif fy == "2026/27":
                value *= C.ACTUAL_DRIFT_FY27["volume"][crop]
        return value

    def price(self, crop: str, month: str, plan: bool) -> float:
        value = C.CROPS[crop][2] * (1 + PRICE_GROWTH) ** fy_index(month)
        if not plan:
            fy = fiscal_year(month)
            if fy == "2025/26":
                value *= DRIFT_FY26["price"][crop]
            elif fy == "2026/27":
                value *= C.ACTUAL_DRIFT_FY27["price"][crop]
        return value

    # ------------------------------------------------------------------ helpers
    def noise(self, sd: float) -> float:
        return float(max(0.5, self.rng.normal(1.0, sd)))

    def split(self, total: float, n: int) -> list[float]:
        weights = self.rng.dirichlet(np.ones(n) * 2)
        parts = [round(total * w, 2) for w in weights]
        parts[-1] = round(total - sum(parts[:-1]), 2)
        return parts

    def invoice_dates(self, month: str) -> tuple[dt.date, dt.date]:
        start = pd.Period(month, freq="M").start_time.date()
        posting = start + dt.timedelta(days=int(self.rng.integers(0, month_end(month).day)))
        entry = posting + dt.timedelta(days=int(self.rng.integers(0, 5)))
        return posting, min(entry, cutoff_date(month, C.CUTOFF_WORKING_DAY))

    def month_end_entry(self, month: str) -> dt.date:
        return working_day(next_month(month), int(self.rng.integers(1, 3)))

    def ref(self) -> str:
        self._ref += 1
        return f"RE-{self._ref}"

    def po(self) -> str:
        self._po += 1
        return str(self._po)

    # ------------------------------------------------------------------ postings
    def run(self) -> dict[str, pd.DataFrame]:
        pending_invoices: dict[str, list] = {}
        self.post_opening_balances(self.months[0])
        for month in self.months:
            self.post_payroll(month)
            self.post_depreciation(month)
            self.post_rent(month)
            self.post_vendor_costs(month, pending_invoices)
            self.post_revenue(month)
            self.post_intercompany(month)
            self.post_capex(month)
            self.capitalise_finished_projects(month)
            self.post_cash(month)
        self.plant_close_issues(C.CLOSE_PERIOD)

        gl = self.ledger.frame()
        return {
            "gl_items": gl,
            "budget": self.build_budget(),
            "revenue_budget": self.build_revenue_budget(),
            "sales": self.sales_extract(gl),
            "headcount": self.build_headcount(),
            "capex_plan": self.build_capex_plan(),
            "capex_commitments": self.build_commitments(gl),
            "recurring_register": self.build_recurring_register(),
            "cost_centers": self.master_cost_centers(),
            "gl_accounts": pd.DataFrame([{"gl_account": k, "account_name": v[0], "account_type": v[1],
                                          "account_group": C.ACCOUNT_GROUPS.get(k, v[0])}
                                         for k, v in C.GL_ACCOUNTS.items()]),
            "entities": pd.DataFrame([{"company_code": k, **v} for k, v in C.ENTITIES.items()]),
        }

    def post_opening_balances(self, month: str) -> None:
        """Fixed assets and equity carried in from before the extract starts."""
        start = pd.Period(month, freq="M").start_time.date()
        for entity in C.ENTITIES:
            annual_dep = sum(self.other_cost(cc, "6200", month, plan=True) * 12 for cc, v in C.COST_CENTERS.items()
                             if v[0] == entity and "6200" in C.COST_MIX[v[1]])
            assets = round(annual_dep * 9, 2)
            cash = round(annual_dep * 2, 2)
            self.ledger.post(entity, month, "OB", start, start, "BATCH", [
                {"gl_account": "0400", "amount": assets}, {"gl_account": "1200", "amount": cash},
                {"gl_account": "2900", "amount": -(assets + cash)},
            ], "Opening balance carried forward")

    def capitalise_finished_projects(self, month: str) -> None:
        for wbs, (entity, desc, budget, start, end) in C.CAPEX_PROJECTS.items():
            if end != month:
                continue
            auc = sum(r["amount_eur"] for r in self.ledger.rows if r["wbs"] == wbs and r["gl_account"] == "0900")
            self.ledger.post(entity, month, "AA", month_end(month), self.month_end_entry(month), "U06", [
                {"gl_account": "0400", "amount": round(auc, 2), "wbs": ""},
                {"gl_account": "0900", "amount": -round(auc, 2), "wbs": ""},
            ], f"Capitalisation {wbs} {desc}")

    def post_payroll(self, month: str) -> None:
        for entity in C.ENTITIES:
            ccs = [cc for cc, v in C.COST_CENTERS.items() if v[0] == entity]
            lines, total = [], 0.0
            for cc in ccs:
                amount = round(self.personnel_cost(cc, month, plan=False) * self.noise(0.01), 2)
                lines.append({"gl_account": "6000", "cost_center": cc, "amount": amount})
                total += amount
            lines.append({"gl_account": "3700", "amount": -round(total, 2)})
            self.ledger.post(entity, month, "SA", month_end(month), self.month_end_entry(month), "BATCH",
                             lines, f"Payroll {month}")

    def post_depreciation(self, month: str, skip_entity: str | None = None) -> None:
        for entity in C.ENTITIES:
            if entity == skip_entity:
                continue
            lines, total = [], 0.0
            for cc, v in C.COST_CENTERS.items():
                if v[0] != entity or "6200" not in C.COST_MIX[v[1]]:
                    continue
                amount = round(self.other_cost(cc, "6200", month, plan=False), 2)
                lines.append({"gl_account": "6200", "cost_center": cc, "amount": amount})
                total += amount
            lines.append({"gl_account": "0400", "amount": -round(total, 2)})
            self.ledger.post(entity, month, "AA", month_end(month), self.month_end_entry(month), "BATCH",
                             lines, f"Depreciation run {month}")

    def post_rent(self, month: str, skip_cc: str | None = None) -> None:
        for cc, v in C.COST_CENTERS.items():
            if "6600" not in C.COST_MIX[v[1]] or cc == skip_cc:
                continue
            amount = round(self.other_cost(cc, "6600", month, plan=False), 2)
            vendor = f"V09{int(cc) % 100:02d}"
            self.ledger.post(v[0], month, "KR", month_end(month), self.month_end_entry(month), "BATCH", [
                {"gl_account": "6600", "cost_center": cc, "amount": amount, "vendor": vendor},
                {"gl_account": "3300", "amount": -amount, "vendor": vendor},
            ], f"Rent and facilities {month}")

    def post_vendor_costs(self, month: str, pending: dict) -> None:
        # Invoices for goods received last month arrive now.
        for entity, cc, po, amount, vendor, gr_month in pending.pop(month, []):
            posting, entry = self.invoice_dates(month)
            self.ledger.post(entity, month, "RE", posting, entry, self.rng.choice(self.users), [
                {"gl_account": "3310", "amount": amount, "po_number": po, "vendor": vendor, "reference": self.ref()},
                {"gl_account": "3300", "amount": -amount, "vendor": vendor},
            ], f"Invoice for PO {po}")

        for cc, v in C.COST_CENTERS.items():
            entity, fa = v[0], v[1]
            for account in C.COST_MIX[fa]:
                if account in C.FLAT_ACCOUNTS:
                    continue
                total = self.other_cost(cc, account, month, plan=False) * self.noise(0.07)
                n = int(self.rng.integers(2, 7))
                for amount in self.split(total, n):
                    vendor = str(self.rng.choice(self.vendors))
                    posting, entry = self.invoice_dates(month)
                    user = str(self.rng.choice(self.users))
                    if account == "5000":
                        po = self.po()
                        self.ledger.post(entity, month, "WE", posting, entry, user, [
                            {"gl_account": "5000", "cost_center": cc, "amount": amount, "po_number": po},
                            {"gl_account": "3310", "amount": -amount, "po_number": po},
                        ], f"Goods receipt PO {po}")
                        if self.rng.random() < 0.8:
                            p2, e2 = self.invoice_dates(month)
                            self.ledger.post(entity, month, "RE", p2, e2, user, [
                                {"gl_account": "3310", "amount": amount, "po_number": po, "vendor": vendor,
                                 "reference": self.ref()},
                                {"gl_account": "3300", "amount": -amount, "vendor": vendor},
                            ], f"Invoice for PO {po}")
                        else:
                            pending.setdefault(next_month(month), []).append((entity, cc, po, amount, vendor, month))
                    else:
                        reference = self.ref()
                        self.ledger.post(entity, month, "KR", posting, entry, user, [
                            {"gl_account": account, "cost_center": cc, "amount": amount, "vendor": vendor,
                             "reference": reference},
                            {"gl_account": "3300", "amount": -amount, "vendor": vendor, "reference": reference},
                        ], C.GL_ACCOUNTS[account][0])
        # Budgeted Q1 corn campaign: in the closing month it is booked (wrongly) in the planted issues.
        if month != C.CLOSE_PERIOD and month == "2025-09":
            amount = round(C.PLANTED_CLOSE_ISSUES["misallocated_journal"]["amount"] * 0.92, 2)
            posting, entry = self.invoice_dates(month)
            self.ledger.post("DE10", month, "KR", posting, entry, "U04", [
                {"gl_account": "6500", "cost_center": "2110", "amount": amount, "vendor": "V0212", "reference": self.ref()},
                {"gl_account": "3300", "amount": -amount, "vendor": "V0212"},
            ], "Corn launch campaign - agency invoice")

    def post_revenue(self, month: str) -> None:
        for entity in C.ENTITIES:
            for crop, (account, _, _, _) in C.CROPS.items():
                units = self.units(entity, crop, month, plan=False) * self.noise(0.05)
                price = self.price(crop, month, plan=False) * self.noise(0.01)
                if units < 1:
                    continue
                n = int(np.clip(units / 3000, 1, 8))
                for q in self.split(units, n):
                    q = max(round(q, 0), 1.0)
                    amount = round(q * price, 2)
                    posting, entry = self.invoice_dates(month)
                    self.ledger.post(entity, month, "RV", posting, entry, "BATCH", [
                        {"gl_account": "1100", "amount": amount},
                        {"gl_account": account, "amount": -amount, "crop": crop, "quantity": q},
                    ], f"Billing {crop} seed")

    def post_intercompany(self, month: str, skip: tuple | None = None) -> None:
        for partner, charges in C.IC_CHARGES.items():
            admin_cc = {"AT10": "4200", "FR10": "4300"}[partner]
            for charge, amount in charges.items():
                amount = round(amount * (1 + C.NON_PERSONNEL_INFLATION) ** fy_index(month), 2)
                pdate, edate = month_end(month), self.month_end_entry(month)
                text = f"IC {charge} {month}"
                self.ledger.post("DE10", month, "DR", pdate, edate, "BATCH", [
                    {"gl_account": "1400", "amount": amount, "partner_company": partner},
                    {"gl_account": "4800", "amount": -amount, "partner_company": partner, "cost_center": "4100"},
                ], text)
                if skip == (partner, charge):
                    continue
                self.ledger.post(partner, month, "KR", pdate, edate, "BATCH", [
                    {"gl_account": "6950", "amount": amount, "partner_company": "DE10", "cost_center": admin_cc},
                    {"gl_account": "3400", "amount": -amount, "partner_company": "DE10"},
                ], text)

    def post_cash(self, month: str) -> None:
        """Customer receipts and vendor payments at month end (keeps receivables and payables realistic)."""
        for entity in C.ENTITIES:
            ar = self.ledger.balances.get((entity, "1100"), 0.0)
            ap = self.ledger.balances.get((entity, "3300"), 0.0)
            pdate, edate = month_end(month), self.month_end_entry(month)
            receipts = round(ar * 0.55, 2)
            payments = round(-ap * 0.75, 2)
            if receipts > 0:
                self.ledger.post(entity, month, "DZ", pdate, edate, "BATCH", [
                    {"gl_account": "1200", "amount": receipts}, {"gl_account": "1100", "amount": -receipts},
                ], "Customer receipts (bank statement)")
            payroll = round(-self.ledger.balances.get((entity, "3700"), 0.0), 2)
            if payroll > 0:
                self.ledger.post(entity, month, "ZP", pdate, edate, "BATCH", [
                    {"gl_account": "3700", "amount": payroll}, {"gl_account": "1200", "amount": -payroll},
                ], "Salary payment")
            if payments > 0:
                self.ledger.post(entity, month, "ZP", pdate, edate, "BATCH", [
                    {"gl_account": "3300", "amount": payments}, {"gl_account": "1200", "amount": -payments},
                ], "Payment run")
        # Intercompany settled each quarter end for the amount the partner has booked.
        if month[5:] in ("03", "06", "09", "12") and month != C.CLOSE_PERIOD:
            for partner in C.IC_CHARGES:
                due = -self.ledger.balances.get((partner, "3400"), 0.0)
                if due <= 0:
                    continue
                due = round(due, 2)
                pdate, edate = month_end(month), self.month_end_entry(month)
                self.ledger.post(partner, month, "ZP", pdate, edate, "BATCH", [
                    {"gl_account": "3400", "amount": due, "partner_company": "DE10"},
                    {"gl_account": "1200", "amount": -due},
                ], "Intercompany settlement")
                self.ledger.post("DE10", month, "DZ", pdate, edate, "BATCH", [
                    {"gl_account": "1200", "amount": due},
                    {"gl_account": "1400", "amount": -due, "partner_company": partner},
                ], "Intercompany settlement")

    def capex_phasing(self, wbs: str) -> dict[str, float]:
        entity, _, budget, start, end = C.CAPEX_PROJECTS[wbs]
        months = month_range(start, end)
        x = np.linspace(0.05, 0.95, len(months))
        w = np.sin(np.pi * x) ** 1.5
        w = w / w.sum()
        return {m: budget * 0.97 * wi for m, wi in zip(months, w)}

    def post_capex(self, month: str) -> None:
        for wbs, (entity, desc, *_rest) in C.CAPEX_PROJECTS.items():
            plan = self.capex_phasing(wbs).get(month)
            if not plan:
                continue
            hot = 1.30 if wbs == C.PLANTED_CLOSE_ISSUES["capex_overrun"]["wbs"] else 1.0
            amount = round(plan * hot * self.noise(0.12), 2)
            vendor = str(self.rng.choice(self.vendors))
            posting, entry = self.invoice_dates(month)
            self.ledger.post(entity, month, "KR", posting, entry, str(self.rng.choice(self.users)), [
                {"gl_account": "0900", "amount": amount, "wbs": wbs, "vendor": vendor, "reference": self.ref()},
                {"gl_account": "3300", "amount": -amount, "vendor": vendor},
            ], desc)

    # ------------------------------------------------------------------ planted close errors
    def plant_close_issues(self, month: str) -> None:
        P = C.PLANTED_CLOSE_ISSUES
        L = self.ledger
        rows_before = len(L.rows)
        # Take out the AT10 depreciation run and the rent for 2300, which were posted with the month.
        drop_docs = set()
        for r in L.rows:
            if r["month"] != month:
                continue
            if r["company_code"] == P["missing_depreciation_run"]["entity"] and r["doc_type"] == "AA":
                drop_docs.add((r["company_code"], r["doc_no"]))
            if r["gl_account"] == "6600" and r["cost_center"] == P["missing_rent"]["cost_center"]:
                drop_docs.add((r["company_code"], r["doc_no"]))
            if (r["company_code"] == P["intercompany_gap"]["partner"] and r["gl_account"] == "6950"
                    and P["intercompany_gap"]["charge"] in r["text"]):
                drop_docs.add((r["company_code"], r["doc_no"]))
        L.rows = [r for r in L.rows if (r["company_code"], r["doc_no"]) not in drop_docs]
        assert len(L.rows) < rows_before

        cutoff = cutoff_date(month, C.CUTOFF_WORKING_DAY)
        me = month_end(month)
        d = lambda days: cutoff - dt.timedelta(days=days)  # noqa: E731

        x = P["unbalanced_document"]
        L.post(x["entity"], month, "SA", me, d(1), "U07", [
            {"gl_account": "6900", "cost_center": "4100", "amount": 15_250.00},
            {"gl_account": "3900", "amount": -15_250.00 + x["difference"]},
        ], "Upload from consolidation feeder: audit fee accrual")

        x = P["blocked_cost_center"]
        L.post(x["entity"], month, "KR", me - dt.timedelta(days=9), d(4), "U03", [
            {"gl_account": "6500", "cost_center": x["cost_center"], "amount": x["amount"], "vendor": "V0188", "reference": self.ref()},
            {"gl_account": "3300", "amount": -x["amount"], "vendor": "V0188"},
        ], "Reporting tool licence")

        x = P["wrong_entity_cost_center"]
        L.post(x["entity"], month, "KR", me - dt.timedelta(days=12), d(5), "U05", [
            {"gl_account": "6400", "cost_center": x["cost_center"], "amount": x["amount"], "vendor": "V0233", "reference": self.ref()},
            {"gl_account": "3300", "amount": -x["amount"], "vendor": "V0233"},
        ], "Trade fair travel Paris")

        x = P["missing_cost_center"]
        L.post(x["entity"], month, "KR", me - dt.timedelta(days=6), d(3), "U09", [
            {"gl_account": x["account"], "cost_center": "", "amount": x["amount"], "vendor": "V0301", "reference": self.ref()},
            {"gl_account": "3300", "amount": -x["amount"], "vendor": "V0301"},
        ], "Legal advice")

        x = P["duplicate_invoice"]
        for days in (14, 3):
            L.post(x["entity"], month, "KR", me - dt.timedelta(days=days), me - dt.timedelta(days=days - 1), "U02", [
                {"gl_account": "6500", "cost_center": "4120", "amount": x["amount"], "vendor": x["vendor"], "reference": x["reference"]},
                {"gl_account": "3300", "amount": -x["amount"], "vendor": x["vendor"], "reference": x["reference"]},
            ], "Cloud hosting Q3")

        x = P["suspense_balance"]
        L.post(x["entity"], month, "SA", me - dt.timedelta(days=2), d(2), "U10", [
            {"gl_account": "1990", "amount": x["amount"]},
            {"gl_account": "1200", "amount": -x["amount"]},
        ], "Unidentified bank debit, to be cleared")

        late = working_day(next_month(month), C.CUTOFF_WORKING_DAY + 2)
        for k in range(P["late_postings"]["count"]):
            cc = ["2100", "3100", "1100", "4120", "2300", "1200"][k]
            entity = C.COST_CENTERS[cc][0]
            amount = round(float(self.rng.uniform(2_000, 14_000)), 2)
            vendor = str(self.rng.choice(self.vendors))
            L.post(entity, month, "KR", me - dt.timedelta(days=int(self.rng.integers(0, 10))), late, "U11", [
                {"gl_account": "6500", "cost_center": cc, "amount": amount, "vendor": vendor, "reference": self.ref()},
                {"gl_account": "3300", "amount": -amount, "vendor": vendor},
            ], "Late invoice entered after cut-off")

        for k in range(P["aged_grir"]["count"]):
            gr_month = ["2026-05", "2026-05", "2026-06", "2026-06"][k]
            cc = ["1100", "1110", "1300", "3100"][k]
            entity = C.COST_CENTERS[cc][0]
            amount = round(float(self.rng.uniform(9_000, 38_000)), 2)
            po = self.po()
            posting = pd.Period(gr_month, freq="M").start_time.date() + dt.timedelta(days=4 + 5 * k)
            L.post(entity, gr_month, "WE", posting, posting + dt.timedelta(days=1), "U06", [
                {"gl_account": "5000", "cost_center": cc, "amount": amount, "po_number": po},
                {"gl_account": "3310", "amount": -amount, "po_number": po},
            ], f"Goods receipt PO {po}")

        x = P["misallocated_journal"]
        L.post("DE10", month, "KR", me - dt.timedelta(days=8), d(2), "U04", [
            {"gl_account": "6500", "cost_center": x["booked_on"], "amount": x["amount"], "vendor": "V0212", "reference": self.ref()},
            {"gl_account": "3300", "amount": -x["amount"], "vendor": "V0212"},
        ], x["text"])

    # ------------------------------------------------------------------ plans and master data
    def build_budget(self) -> pd.DataFrame:
        rows = []
        for month in self.budget_months:
            for cc, v in C.COST_CENTERS.items():
                entity, fa = v[0], v[1]
                rows.append((entity, cc, fa, "6000", month, self.personnel_cost(cc, month, plan=True)))
                for account in C.COST_MIX[fa]:
                    rows.append((entity, cc, fa, account, month, self.other_cost(cc, account, month, plan=True)))
            for partner, charges in C.IC_CHARGES.items():
                admin_cc = {"AT10": "4200", "FR10": "4300"}[partner]
                rows.append((partner, admin_cc, "GNA", "6950", month,
                             sum(charges.values()) * (1 + C.NON_PERSONNEL_INFLATION) ** fy_index(month)))
            if month in ("2025-09", "2026-09"):
                rows.append(("DE10", "2110", "SEL", "6500", month, C.PLANTED_CLOSE_ISSUES["misallocated_journal"]["amount"]))
        df = pd.DataFrame(rows, columns=["company_code", "cost_center", "functional_area", "gl_account", "month", "budget_eur"])
        df["budget_eur"] = df["budget_eur"].round(2)
        df["fiscal_year"] = df["month"].map(fiscal_year)
        df["period"] = df["month"].map(fiscal_period)
        return df.groupby(["fiscal_year", "period", "month", "company_code", "cost_center", "functional_area", "gl_account"],
                          as_index=False)["budget_eur"].sum()

    def build_revenue_budget(self) -> pd.DataFrame:
        rows = []
        for month in self.budget_months:
            for entity in C.ENTITIES:
                for crop, (account, unit, _, _) in C.CROPS.items():
                    q = self.units(entity, crop, month, plan=True)
                    p = self.price(crop, month, plan=True)
                    rows.append({"fiscal_year": fiscal_year(month), "period": fiscal_period(month), "month": month,
                                 "company_code": entity, "crop": crop, "gl_account": account, "unit": unit,
                                 "units": round(q, 0), "price_eur": round(p, 2), "revenue_eur": round(round(q, 0) * p, 2)})
        return pd.DataFrame(rows)

    def sales_extract(self, gl: pd.DataFrame) -> pd.DataFrame:
        rev = gl[gl["crop"] != ""]
        out = (rev.groupby(["fiscal_year", "period", "month", "company_code", "crop", "gl_account"], as_index=False)
               .agg(units=("quantity", "sum"), revenue_eur=("amount_eur", lambda s: -s.sum())))
        out["revenue_eur"] = out["revenue_eur"].round(2)
        return out

    def build_headcount(self) -> pd.DataFrame:
        rows = []
        for month in self.budget_months:
            for cc in C.COST_CENTERS:
                rows.append({"month": month, "fiscal_year": fiscal_year(month), "period": fiscal_period(month),
                             "cost_center": cc, "fte_plan": self.fte(cc, month, plan=True),
                             "fte_actual": self.fte(cc, month, plan=False) if month <= C.CLOSE_PERIOD else np.nan})
        return pd.DataFrame(rows)

    def build_capex_plan(self) -> pd.DataFrame:
        rows = []
        for wbs, (entity, desc, budget, start, end) in C.CAPEX_PROJECTS.items():
            for month, amount in self.capex_phasing(wbs).items():
                rows.append({"wbs": wbs, "company_code": entity, "description": desc, "approved_budget_eur": budget,
                             "month": month, "fiscal_year": fiscal_year(month), "planned_eur": round(amount, 2)})
        return pd.DataFrame(rows)

    def build_commitments(self, gl: pd.DataFrame) -> pd.DataFrame:
        actual = gl[gl["wbs"] != ""].groupby("wbs")["amount_eur"].sum()
        rows = []
        for wbs, (entity, desc, budget, start, end) in C.CAPEX_PROJECTS.items():
            phasing = self.capex_phasing(wbs)
            upcoming = [m for m in sorted(phasing) if m > C.CLOSE_PERIOD][:3]
            open_po = 0.8 * sum(phasing[m] for m in upcoming)
            if wbs == C.PLANTED_CLOSE_ISSUES["capex_overrun"]["wbs"]:
                open_po = max(open_po, 1.16 * budget - actual.get(wbs, 0.0))
            rows.append({"wbs": wbs, "company_code": entity, "as_of": C.CLOSE_PERIOD,
                         "open_po_eur": round(open_po, 2)})
        return pd.DataFrame(rows)

    def build_recurring_register(self) -> pd.DataFrame:
        rows = []
        for entity in C.ENTITIES:
            rows.append({"company_code": entity, "kind": "payroll", "doc_type": "SA", "gl_account": "6000", "cost_center": "*"})
            rows.append({"company_code": entity, "kind": "depreciation run", "doc_type": "AA", "gl_account": "6200", "cost_center": "*"})
        for cc, v in C.COST_CENTERS.items():
            if "6600" in C.COST_MIX[v[1]]:
                rows.append({"company_code": v[0], "kind": "rent", "doc_type": "KR", "gl_account": "6600", "cost_center": cc})
        for partner, charges in C.IC_CHARGES.items():
            for charge in charges:
                rows.append({"company_code": partner, "kind": f"IC {charge}", "doc_type": "KR", "gl_account": "6950", "cost_center": "*"})
                rows.append({"company_code": "DE10", "kind": f"IC {charge} to {partner}", "doc_type": "DR", "gl_account": "4800", "cost_center": "*"})
        return pd.DataFrame(rows)

    def master_cost_centers(self) -> pd.DataFrame:
        rows = [{"cost_center": cc, "company_code": v[0], "functional_area": v[1], "cost_center_name": v[2], "blocked": False}
                for cc, v in C.COST_CENTERS.items()]
        rows += [{"cost_center": cc, "company_code": v[0], "functional_area": v[1], "cost_center_name": v[2], "blocked": True}
                 for cc, v in C.BLOCKED_COST_CENTERS.items()]
        return pd.DataFrame(rows)


def generate(seed: int = C.SEED) -> dict[str, pd.DataFrame]:
    return Generator(seed).run()


DTYPES = {"cost_center": str, "gl_account": str, "doc_no": str, "po_number": str, "wbs": str,
          "partner_company": str, "vendor": str, "reference": str, "crop": str, "company_code": str}


def save(tables: dict[str, pd.DataFrame], folder) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        suffix = ".csv.gz" if name == "gl_items" else ".csv"
        df.to_csv(folder / f"{name}{suffix}", index=False)


def load(folder) -> dict[str, pd.DataFrame]:
    tables = {}
    for path in sorted(folder.glob("*.csv*")):
        name = path.name.split(".")[0]
        df = pd.read_csv(path, dtype=DTYPES, keep_default_na=False, na_values={"fte_actual": [""]})
        tables[name] = df
    return tables
