"""A small medallion lakehouse for a fictional B2B distributor, Kestrel Industrial Supply.

bronze   raw ERP exports as JSON lines, kept exactly as received (duplicates, German decimal commas,
         amounts in AED, missing due dates)
silver   typed, de-duplicated, converted to EUR, due dates filled from payment terms
gold     marts the agent may query: open receivables per account, invoice aging, monthly revenue

Locally the files live in lake/ and gold is queried with SQLite. In AWS the same layout sits in S3,
the Glue catalog describes the gold tables and Athena queries them (see infra/terraform and ADR 0005).
Everything is synthetic: company names are invented and contact addresses use reserved example domains.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from .config import SEED

AS_OF = date(2026, 11, 20)
FX_TO_EUR = {"EUR": 1.0, "AED": 0.25}           # fixed rate for the simulation
OWNERS = ["AM01", "AM02", "AM03", "AM04", "AM05", "AM06"]

PREFIX = ["Nordhafen", "Elbtal", "Alpenrand", "Rheinkraft", "Havelstahl", "Isarwerk", "Bodensee", "Weserfeld", "Oderblick",
          "Taunus", "Spreewald", "Ruhrbogen", "Al Noor", "Gulf Crest", "Desert Line", "Marina", "Corniche", "Palm Ridge"]
SUFFIX = ["Maschinenbau GmbH", "Anlagentechnik AG", "Logistik GmbH", "Fertigung GmbH", "Industrieservice KG",
          "Engineering LLC", "Trading LLC", "Facilities FZE", "Contracting LLC"]


def _accounts(rng) -> pd.DataFrame:
    rows, used = [], set()
    for i in range(60):
        gulf = i >= 42
        while True:
            pre = rng.choice(PREFIX[12:] if gulf else PREFIX[:12])
            suf = rng.choice(SUFFIX[5:] if gulf else SUFFIX[:5])
            name = f"{pre} {suf}"
            if name not in used:
                used.add(name)
                break
        seg = rng.choice(["key", "mid", "small"], p=[0.2, 0.45, 0.35])
        rows.append({"account_id": f"A{i + 1:03d}", "name": name, "region": "Gulf" if gulf else "DACH",
                     "segment": seg, "owner": OWNERS[i % 6] if not gulf else OWNERS[4 + i % 2],
                     "payment_terms_days": int(rng.choice([30, 45, 60], p=[0.5, 0.3, 0.2])),
                     "credit_limit_eur": int({"key": 250_000, "mid": 80_000, "small": 25_000}[seg] * rng.uniform(0.8, 1.2) // 1000 * 1000),
                     "currency": "AED" if gulf else "EUR",
                     "contact_email": f"ap@account-{i + 1:03d}.example" + (".ae" if gulf else ".de")})
    return pd.DataFrame(rows)


def generate(seed: int = SEED) -> dict[str, pd.DataFrame]:
    """True, clean source data plus the messy bronze exports derived from it."""
    rng = np.random.default_rng(seed)
    acc = _accounts(rng)
    products = pd.DataFrame({"sku": [f"P{i:03d}" for i in range(1, 31)],
                             "category": rng.choice(["bearings", "hydraulics", "fasteners", "safety", "tools", "electrics"], 30),
                             "unit_price_eur": np.round(rng.lognormal(3.6, 0.8, 30), 2)})
    invoices, lines, payments = [], [], []
    inv_no = 10000
    for a in acc.itertuples():
        scale = {"key": 9, "mid": 4, "small": 1.6}[a.segment]
        late_bias = rng.beta(2, 5)                  # some customers pay late habitually
        d = date(2025, 12, 1)
        while d <= AS_OF:
            d += timedelta(days=int(rng.exponential(30 / scale)) + 1)
            if d > AS_OF:
                break
            inv_no += 1
            n_lines = int(rng.integers(1, 5))
            skus = rng.choice(products["sku"], n_lines, replace=False)
            total = 0.0
            for s in skus:
                qty = int(rng.integers(1, 40) * scale)
                price = float(products.loc[products["sku"] == s, "unit_price_eur"].iloc[0])
                total += qty * price
                lines.append({"invoice_id": f"INV{inv_no}", "sku": s, "qty": qty, "net_eur": round(qty * price, 2)})
            due = d + timedelta(days=a.payment_terms_days)
            # payment behaviour: most on time, some late, recent ones still open
            delay = int(rng.choice([-5, 0, 3, 10, 25, 50, 90], p=[0.15, 0.3, 0.2, 0.15, 0.1, 0.06, 0.04]) * (0.6 + late_bias))
            paid_on = due + timedelta(days=delay)
            invoices.append({"invoice_id": f"INV{inv_no}", "account_id": a.account_id, "issued": d, "due": due,
                             "amount_eur": round(total, 2), "currency": a.currency})
            if paid_on <= AS_OF:
                payments.append({"payment_id": f"PAY{inv_no}", "invoice_id": f"INV{inv_no}", "paid_on": paid_on, "amount_eur": round(total, 2)})
    return {"accounts": acc, "products": products, "invoices": pd.DataFrame(invoices),
            "invoice_lines": pd.DataFrame(lines), "payments": pd.DataFrame(payments)}


# ---------------------------------------------------------------------------------- bronze
def _de_number(x: float) -> str:
    return f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def write_bronze(src: dict[str, pd.DataFrame], lake: Path, seed: int = SEED) -> dict:
    """Export the source the way an ERP would: per-currency amounts, German number formats, re-sent rows."""
    rng = np.random.default_rng(seed + 1)
    b = lake / "bronze"
    b.mkdir(parents=True, exist_ok=True)
    planted = {}
    inv = src["invoices"].copy()
    inv["amount"] = [round(a / FX_TO_EUR[c], 2) for a, c in zip(inv["amount_eur"], inv["currency"])]
    recs = []
    for r in inv.itertuples():
        rec = {"invoice_id": r.invoice_id, "account_id": r.account_id, "issued": r.issued.isoformat(),
               "due": r.due.isoformat(), "amount": r.amount, "currency": r.currency}
        if r.currency == "EUR" and rng.random() < 0.3:
            rec["amount"] = _de_number(r.amount)            # "12.345,60" from the German ERP instance
        if rng.random() < 0.03:
            rec["due"] = None                               # due date missing: silver derives it from terms
        recs.append(rec)
    dups = rng.choice(len(recs), 25, replace=False)
    planted["duplicate_invoices"] = 25
    planted["missing_due_dates"] = sum(1 for r in recs if r["due"] is None)
    for i in dups:
        recs.append(dict(recs[i], _exported_at="2026-11-19T23:10:00"))   # re-sent in a later export
    with open(b / "invoices.jsonl", "w") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")
    for name in ("accounts", "products", "invoice_lines", "payments"):
        df = src[name].copy()
        for c in df.columns:
            if df[c].dtype == object and isinstance(df[c].iloc[0], date):
                df[c] = df[c].map(lambda x: x.isoformat())
        df.to_json(b / f"{name}.jsonl", orient="records", lines=True)
    (b / "_manifest.json").write_text(json.dumps({"source": "ERP export (simulated)", "as_of": AS_OF.isoformat(), "planted": planted}, indent=1))
    return planted


# ---------------------------------------------------------------------------------- silver
def _num(x) -> float:
    if isinstance(x, (int, float)):
        return float(x)
    return float(str(x).replace(".", "").replace(",", "."))


def build_silver(lake: Path) -> dict:
    b, s = lake / "bronze", lake / "silver"
    s.mkdir(parents=True, exist_ok=True)
    acc = pd.read_json(b / "accounts.jsonl", lines=True)
    inv = pd.read_json(b / "invoices.jsonl", lines=True, dtype={"amount": object})
    report = {"bronze_invoice_rows": len(inv)}
    inv = inv.drop(columns=[c for c in inv.columns if c.startswith("_")]).drop_duplicates("invoice_id", keep="first")
    report["duplicates_removed"] = report["bronze_invoice_rows"] - len(inv)
    inv["amount_eur"] = [round(_num(a) * FX_TO_EUR[c], 2) for a, c in zip(inv["amount"], inv["currency"])]
    terms = acc.set_index("account_id")["payment_terms_days"]
    missing = inv["due"].isna()
    inv.loc[missing, "due"] = [(pd.Timestamp(i) + pd.Timedelta(days=int(terms[a]))).date().isoformat()
                               for i, a in zip(inv.loc[missing, "issued"], inv.loc[missing, "account_id"])]
    report["due_dates_derived"] = int(missing.sum())
    inv = inv[["invoice_id", "account_id", "issued", "due", "amount_eur", "currency"]]
    inv.to_csv(s / "invoices.csv", index=False)
    acc.to_csv(s / "accounts.csv", index=False)
    for name in ("products", "invoice_lines", "payments"):
        pd.read_json(b / f"{name}.jsonl", lines=True).to_csv(s / f"{name}.csv", index=False)
    return report


# ---------------------------------------------------------------------------------- gold
def build_gold(lake: Path, as_of: date = AS_OF) -> dict:
    s, g = lake / "silver", lake / "gold"
    g.mkdir(parents=True, exist_ok=True)
    acc = pd.read_csv(s / "accounts.csv")
    inv = pd.read_csv(s / "invoices.csv", parse_dates=["issued", "due"])
    pay = pd.read_csv(s / "payments.csv", parse_dates=["paid_on"])
    lines = pd.read_csv(s / "invoice_lines.csv")
    prod = pd.read_csv(s / "products.csv")
    paid = pay.groupby("invoice_id")["amount_eur"].sum()
    inv["paid_eur"] = inv["invoice_id"].map(paid).fillna(0.0)
    inv["open_eur"] = (inv["amount_eur"] - inv["paid_eur"]).round(2)
    ts = pd.Timestamp(as_of)
    inv["days_past_due"] = (ts - inv["due"]).dt.days
    open_inv = inv[inv["open_eur"] > 0.005].copy()
    open_inv["bucket"] = pd.cut(open_inv["days_past_due"], [-10_000, 0, 30, 60, 90, 10_000],
                                labels=["not_due", "1_30", "31_60", "61_90", "over_90"]).astype(str)
    open_invoices = open_inv.merge(acc[["account_id", "owner", "region"]], on="account_id")[
        ["invoice_id", "account_id", "owner", "region", "issued", "due", "amount_eur", "open_eur", "days_past_due", "bucket"]]
    ar = open_inv.groupby("account_id").agg(open_eur=("open_eur", "sum"),
                                            overdue_eur=("open_eur", lambda x: x[open_inv.loc[x.index, "days_past_due"] > 0].sum()),
                                            oldest_days_past_due=("days_past_due", "max"), open_invoices=("invoice_id", "count"))
    account_ar = acc.merge(ar, on="account_id", how="left").fillna({"open_eur": 0, "overdue_eur": 0, "open_invoices": 0})
    account_ar["oldest_days_past_due"] = account_ar["oldest_days_past_due"].fillna(0).clip(lower=0).astype(int)
    account_ar["credit_used_pct"] = (account_ar["open_eur"] / account_ar["credit_limit_eur"]).round(4)
    account_ar = account_ar[["account_id", "name", "region", "segment", "owner", "payment_terms_days", "credit_limit_eur",
                             "open_eur", "overdue_eur", "oldest_days_past_due", "open_invoices", "credit_used_pct", "contact_email"]]
    rev = lines.merge(inv[["invoice_id", "account_id", "issued"]], on="invoice_id").merge(prod[["sku", "category"]], on="sku")
    rev["month"] = rev["issued"].dt.strftime("%Y-%m")
    revenue_monthly = rev.merge(acc[["account_id", "owner", "region"]], on="account_id").groupby(
        ["month", "account_id", "owner", "region", "category"], as_index=False)["net_eur"].sum().rename(columns={"net_eur": "revenue_eur"})
    for name, df in (("account_ar", account_ar), ("open_invoices", open_invoices), ("revenue_monthly", revenue_monthly)):
        out = df.copy()
        for c in out.columns:
            if pd.api.types.is_datetime64_any_dtype(out[c]):
                out[c] = out[c].dt.strftime("%Y-%m-%d")
        out.round(2).to_csv(g / f"{name}.csv", index=False)
    return {"accounts": len(account_ar), "open_invoices": len(open_invoices), "revenue_rows": len(revenue_monthly),
            "open_eur_total": round(float(account_ar["open_eur"].sum()), 2)}


def quality_checks(src: dict[str, pd.DataFrame], lake: Path) -> pd.DataFrame:
    """Reconcile silver and gold with the true source: the medallion steps must not lose or invent money."""
    s, g = lake / "silver", lake / "gold"
    inv = pd.read_csv(s / "invoices.csv")
    ar = pd.read_csv(g / "account_ar.csv")
    truth = src["invoices"].copy()
    paid = src["payments"].groupby("invoice_id")["amount_eur"].sum()
    truth_open = (truth["amount_eur"] - truth["invoice_id"].map(paid).fillna(0)).clip(lower=0).sum()
    checks = [
        ("silver invoice ids are unique", inv["invoice_id"].is_unique, f"{len(inv)} rows"),
        ("silver keeps every source invoice", len(inv) == len(truth), f"{len(inv)} vs {len(truth)}"),
        ("silver amounts equal source in EUR (to the cent)",
         bool(np.allclose(inv.set_index("invoice_id")["amount_eur"].sort_index(), truth.set_index("invoice_id")["amount_eur"].sort_index(), atol=0.02)), ""),
        ("no missing due dates in silver", inv["due"].notna().all(), ""),
        ("gold open receivables equal source", abs(ar["open_eur"].sum() - truth_open) < 1.0, f"{ar['open_eur'].sum():,.2f} vs {truth_open:,.2f}"),
        ("every account has an owner", ar["owner"].notna().all(), ""),
    ]
    return pd.DataFrame(checks, columns=["check", "passed", "detail"])


def build_all(lake: Path) -> dict:
    src = generate()
    planted = write_bronze(src, lake)
    silver = build_silver(lake)
    gold = build_gold(lake)
    qc = quality_checks(src, lake)
    return {"source": src, "planted": planted, "silver": silver, "gold": gold, "quality": qc}
