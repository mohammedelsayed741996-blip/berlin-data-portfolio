"""Run the data quality rules in config/dq_rules.yaml and score each dataset by dimension."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

from .config import ROOT

RULES_FILE = ROOT / "config" / "dq_rules.yaml"


def load_rules(path: Path = RULES_FILE) -> list[dict]:
    return yaml.safe_load(path.read_text())


def run(raw: dict[str, pd.DataFrame], lines: pd.DataFrame, recs: pd.DataFrame, review: pd.DataFrame) -> pd.DataFrame:
    """Return one row per rule with rows checked, rows failing and a few example references."""
    a, b = raw["erp_a_ekpo"], raw["erp_b_orders"]
    known = set(recs.supplier_ref)
    med = lines.groupby("description").unit_price_eur.transform("median")
    ratio = lines.unit_price_eur / med
    gr = raw["goods_receipts"].merge(lines[["line_ref", "order_date"]].drop_duplicates("line_ref"), left_on=raw["goods_receipts"].line_id.astype(int),
                                     right_on="line_ref", how="left")
    blocked = set(recs.supplier_ref[recs.blocked])
    a_lines = lines[lines.source == "ERP_A"]
    fails = {
        "DQ01": (len(a), a[a.duplicated(keep="first")].EBELN),
        "DQ02": (len(lines), lines[~lines.supplier_ref.isin(known)].order_no),
        "DQ03": (len(b), b[b.category.eq("")].order_no),
        "DQ04": (len(lines), lines[(ratio > 20) | (ratio < 0.05)].order_no),
        "DQ05": (len(b), b[pd.to_numeric(b.quantity) < 0].order_no),
        "DQ06": (len(recs), recs[recs.country.eq("")].supplier_ref),
        "DQ07": (len(recs), recs[recs.duplicated("golden_id", keep="first")].supplier_ref),
        "DQ08": (len(recs), recs[recs.source.eq("ERP_A") & ~recs.terms_raw.str.fullmatch(r"ZB\d+")].supplier_ref),
        "DQ09": (len(gr), gr[pd.to_datetime(gr.receipt_date) < gr.order_date].line_id),
        "DQ10": (len(lines), lines[lines.supplier_ref.isin(blocked)].order_no),
        "DQ11": (len(recs), recs[recs.vat_id.eq("")].supplier_ref),
        "DQ12": (len(a_lines), a_lines[a_lines.category_src != a_lines.category_inferred].order_no),
    }
    out = []
    for r in load_rules():
        checked, bad = fails[r["id"]]
        out.append({**r, "checked": checked, "failing": len(bad), "pass_rate": 1 - len(bad) / max(checked, 1),
                    "examples": ", ".join(map(str, list(dict.fromkeys(bad))[:3]))})
    return pd.DataFrame(out)


def scorecard(results: pd.DataFrame) -> pd.DataFrame:
    """Pass rate by dataset and dimension (rows passing / rows checked), the view a data owner signs off."""
    g = results.groupby(["dataset", "dimension"]).agg(checked=("checked", "sum"), failing=("failing", "sum")).reset_index()
    g["score"] = 1 - g.failing / g.checked
    return g.pivot(index="dataset", columns="dimension", values="score").round(4)


def score_against_key(results: pd.DataFrame, key: dict, merges_ok: dict) -> pd.DataFrame:
    """Planted problems vs what the rules found."""
    f = results.set_index("id").failing
    rows = [
        ("Duplicate order lines in the ERP_A export", key["duplicate_po_lines_erp_a"], f["DQ01"]),
        ("Order lines with a supplier missing from the master", key["orphan_supplier_lines_erp_a"], f["DQ02"]),
        ("ERP_B lines without a category", key["unclassified_lines_erp_b"], f["DQ03"]),
        ("Copper lines priced per tonne on a per-kg line", len(key["price_per_tonne_on_kg_lines_erp_b"]), f["DQ04"]),
        ("Returns booked as negative quantities", key["negative_quantity_lines_erp_b"], f["DQ05"]),
        ("Suppliers without a country", key["missing_supplier_country"], f["DQ06"]),
        ("Goods receipts dated before the order", key["receipt_before_order"], f["DQ09"]),
        ("Duplicate supplier pairs (within and across ERPs)", merges_ok["true_pairs"], merges_ok["found"]),
    ]
    return pd.DataFrame(rows, columns=["planted_problem", "planted", "found"])
