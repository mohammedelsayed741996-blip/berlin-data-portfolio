"""Origination pipeline reporting on a Salesforce-style opportunity export.

The export is synthetic: fictional customers (industrial offtakers and renewable developers), products
(solar PPA, wind PPA, BESS tolling, baseload swap), stages with default probabilities, volumes and margins.
The module checks the data, then builds the reports an origination team reviews every week: pipeline by
stage and product, a weighted forecast by quarter against target, win rates and stale deals.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import AS_OF, RAW, SEED

STAGES = {"Prospecting": 0.10, "Qualification": 0.20, "Indicative Offer": 0.35, "Term Sheet": 0.60, "Negotiation": 0.80,
          "Closed Won": 1.0, "Closed Lost": 0.0}
PRODUCTS = {"Solar PPA": (30, 120), "Wind PPA": (60, 250), "BESS Tolling": (10, 40), "Baseload Swap": (20, 150)}   # GWh/yr range
MARGIN = {"Solar PPA": 1.2, "Wind PPA": 1.0, "BESS Tolling": 2.5, "Baseload Swap": 0.4}                          # EUR/MWh
PREFIX = ["Nord", "Spree", "Havel", "Rhein", "Elb", "Main", "Isar", "Ostsee", "Harz", "Lausitz", "Eifel", "Allgaeu"]
KIND = ["Chemie", "Stahlwerk", "Papier", "Rechenzentrum", "Glaswerk", "Solarpark", "Windpark", "Energie", "Logistik", "Zement"]


def generate(seed: int = SEED, n: int = 220) -> pd.DataFrame:
    rng = np.random.default_rng(seed + 2)
    asof = pd.Timestamp(AS_OF)
    rows = []
    for i in range(n):
        product = rng.choice(list(PRODUCTS), p=[0.38, 0.27, 0.15, 0.20])
        created = asof - pd.Timedelta(days=int(rng.integers(5, 700)))
        age = (asof - created).days
        if age > 240 and rng.random() < 0.8:
            stage = "Closed Won" if rng.random() < 0.27 else "Closed Lost"
        else:
            stage = rng.choice(["Prospecting", "Qualification", "Indicative Offer", "Term Sheet", "Negotiation"], p=[.25, .25, .25, .15, .10])
        lo, hi = PRODUCTS[product]
        vol = float(np.round(rng.uniform(lo, hi), 1))
        tenor = int(rng.choice([1, 3, 5, 10], p=[.2, .35, .3, .15]))
        close = created + pd.Timedelta(days=int(rng.integers(60, 360)))
        rows.append({"Opportunity ID": f"006Q{100000 + i}", "Account Name": f"{rng.choice(PREFIX)} {rng.choice(KIND)} GmbH",
                     "Opportunity Owner": f"Originator {rng.integers(1, 6)}", "Product": product, "Stage": stage,
                     "Probability (%)": int(STAGES[stage] * 100), "Volume (GWh/yr)": vol, "Tenor (years)": tenor,
                     "Expected Margin (EUR/MWh)": round(MARGIN[product] * rng.uniform(0.6, 1.5), 2),
                     "Created Date": created.date(), "Close Date": close.date(), "Last Activity Date": (asof - pd.Timedelta(days=int(rng.integers(0, 120)))).date()})
    df = pd.DataFrame(rows)
    # typical CRM data problems, planted
    df.loc[df.sample(6, random_state=1).index, "Close Date"] = None
    idx = df[~df.Stage.str.startswith("Closed")].sample(5, random_state=2).index
    df.loc[idx, "Probability (%)"] = 90                                      # probability not matching the stage
    df.loc[df.sample(4, random_state=3).index, "Volume (GWh/yr)"] = 0.0
    return df


def load(raw=RAW) -> pd.DataFrame:
    df = pd.read_csv(raw / "salesforce_opportunities.csv")
    for c in ["Created Date", "Close Date", "Last Activity Date"]:
        df[c] = pd.to_datetime(df[c])
    return df


def checks(df: pd.DataFrame, asof: str = AS_OF) -> pd.DataFrame:
    asof = pd.Timestamp(asof)
    open_ = ~df.Stage.str.startswith("Closed")
    rules = {
        "Close date missing": df["Close Date"].isna(),
        "Probability does not match stage": df["Probability (%)"] != (df.Stage.map(STAGES) * 100).round().astype(int),
        "Volume is zero": df["Volume (GWh/yr)"] <= 0,
        "Open deal with close date in the past": open_ & (df["Close Date"] < asof),
        "Open deal without activity for 60+ days": open_ & ((asof - df["Last Activity Date"]).dt.days > 60),
    }
    return pd.DataFrame([{"check": k, "opportunities": int(v.sum()), "examples": ", ".join(df.loc[v, "Opportunity ID"].head(3))} for k, v in rules.items()])


def pipeline(df: pd.DataFrame) -> pd.DataFrame:
    """Open pipeline by stage and product: volume, contract margin and probability-weighted margin (EUR)."""
    d = df[~df.Stage.str.startswith("Closed")].copy()
    d["prob"] = d.Stage.map(STAGES)                                            # stage default, not the typed value
    d["margin_eur"] = d["Volume (GWh/yr)"] * 1000 * d["Tenor (years)"] * d["Expected Margin (EUR/MWh)"]
    d["weighted_margin_eur"] = d.margin_eur * d.prob
    order = list(STAGES)[:5]
    t = d.pivot_table(index="Stage", columns="Product", values="weighted_margin_eur", aggfunc="sum", fill_value=0).reindex(order)
    return t


def forecast(df: pd.DataFrame, target_eur: float = 2.5e6) -> pd.DataFrame:
    """Weighted margin expected to close per quarter (next four quarters) against a quarterly target."""
    d = df[~df.Stage.str.startswith("Closed") & df["Close Date"].notna()].copy()
    d["prob"] = d.Stage.map(STAGES)
    d["weighted_margin_eur"] = d["Volume (GWh/yr)"] * 1000 * d["Tenor (years)"] * d["Expected Margin (EUR/MWh)"] * d.prob
    d["quarter"] = d["Close Date"].dt.to_period("Q").astype(str)
    q = d.groupby("quarter").agg(deals=("Opportunity ID", "count"), weighted_margin_eur=("weighted_margin_eur", "sum"))
    q = q[q.index >= pd.Timestamp(AS_OF).to_period("Q").strftime("%YQ%q")].head(4)
    q["target_eur"] = target_eur
    q["coverage"] = q.weighted_margin_eur / q.target_eur
    return q.reset_index()


def win_rates(df: pd.DataFrame) -> pd.DataFrame:
    c = df[df.Stage.str.startswith("Closed")]
    w = c.groupby("Product").agg(closed=("Stage", "count"), won=("Stage", lambda s: int((s == "Closed Won").sum())))
    w["win_rate"] = w.won / w.closed
    return w.reset_index()


def write(raw=RAW, seed: int = SEED) -> pd.DataFrame:
    df = generate(seed)
    df.to_csv(raw / "salesforce_opportunities.csv", index=False)
    return df
