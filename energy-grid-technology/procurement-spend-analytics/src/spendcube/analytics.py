"""Spend and supplier analytics on top of the cube."""

from __future__ import annotations

import sqlite3

import numpy as np
import pandas as pd

from .config import CATEGORIES


def q(con: sqlite3.Connection, sql: str) -> pd.DataFrame:
    return pd.read_sql_query(sql, con)


def headline(con) -> dict:
    total = q(con, "SELECT SUM(spend_eur) s, SUM(CASE WHEN on_contract=1 THEN spend_eur END) c, SUM(CASE WHEN maverick=1 THEN spend_eur END) m, "
                   "COUNT(DISTINCT supplier_id) n FROM fact_po_line WHERE is_return=0").iloc[0]
    returns = q(con, "SELECT -SUM(spend_eur) r FROM fact_po_line WHERE is_return=1").iloc[0, 0]
    p = q(con, "SELECT * FROM v_supplier_pareto")
    n80 = int((p.cumulative_share < 0.8).sum() + 1)
    tail = p[p.cumulative_share > 0.95]
    mav = q(con, "SELECT contract_status, SUM(spend_eur) s FROM fact_po_line WHERE maverick=1 GROUP BY contract_status").set_index("contract_status").s
    otd = q(con, "SELECT AVG(on_time) FROM fact_po_line WHERE on_time IS NOT NULL").iloc[0, 0]
    return {"spend_eur": float(total.s), "suppliers": int(total.n), "on_contract_share": float(total.c / total.s),
            "maverick_eur": float(total.m), "maverick_share": float(total.m / total.s),
            "maverick_expired_contract_eur": float(mav.get("expired", 0)), "maverick_no_contract_eur": float(mav.get("none", 0)), "returns_eur": float(returns or 0),
            "suppliers_for_80pct": n80, "tail_suppliers": len(tail), "tail_spend_share": float(tail.spend_eur.sum() / p.spend_eur.sum()),
            "on_time_rate": float(otd)}


def supplier_scorecard(con) -> pd.DataFrame:
    """Score 0-100 per supplier from delivery, quality and country risk; spend-weighted view for buyers."""
    perf = q(con, "SELECT * FROM v_supplier_performance WHERE supplier_id <> 'S9999' AND receipts >= 10")
    perf["delivery_score"] = (perf.on_time_rate.clip(0.5, 1) - 0.5) / 0.5 * 100
    perf["quality_score"] = (1 - (perf.defect_rate / 0.05).clip(0, 1)) * 100
    perf["risk_score"] = perf.country_risk.map({1: 100, 2: 60, 3: 20})
    perf["score"] = (0.45 * perf.delivery_score + 0.35 * perf.quality_score + 0.20 * perf.risk_score).round(1)
    perf["grade"] = pd.cut(perf.score, [-1, 60, 75, 90, 101], labels=["D", "C", "B", "A"])
    return perf.sort_values("spend_eur", ascending=False)


def kraljic(con, volatility: dict[str, float]) -> pd.DataFrame:
    """Place each category in the Kraljic matrix.

    Profit impact = share of spend. Supply risk = mean of four 0-1 signals: few suppliers, concentration (HHI),
    spend-weighted country risk and price volatility of the linked commodity index.
    """
    cat = q(con, "SELECT * FROM v_spend_by_category").merge(q(con, "SELECT * FROM v_category_concentration"), on="category", suffixes=("", "_c"))
    risk = q(con, """SELECT f.category, SUM(f.spend_eur * d.country_risk) / SUM(f.spend_eur) AS country_risk
                     FROM fact_po_line f JOIN dim_supplier d USING (supplier_id) WHERE f.is_return = 0 GROUP BY f.category""")
    cat = cat.merge(risk, on="category")
    cat["vol"] = cat.category.map(lambda c: volatility.get(CATEGORIES[c]["index"] or "", 0.0))
    signals = pd.DataFrame({
        "few_suppliers": (1 - (cat.suppliers - 2) / 18).clip(0, 1),
        "concentration": (cat.hhi / 5000).clip(0, 1),
        "country_risk": ((cat.country_risk - 1) / 2).clip(0, 1),
        "price_volatility": (cat.vol / 0.08).clip(0, 1),
    })
    cat = pd.concat([cat, signals], axis=1)
    cat["supply_risk"] = signals.mean(axis=1).round(3)
    cat["profit_impact"] = (cat.share_pct / 100).round(3)
    hi_impact, hi_risk = cat.profit_impact >= 0.08, cat.supply_risk >= 0.40
    cat["quadrant"] = np.select([hi_impact & hi_risk, hi_impact & ~hi_risk, ~hi_impact & hi_risk], ["Strategic", "Leverage", "Bottleneck"], "Non-critical")
    return cat.sort_values("spend_eur", ascending=False)
