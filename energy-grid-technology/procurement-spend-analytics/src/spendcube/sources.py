"""Read the raw exports and bring them into one harmonised shape.

Reading is deliberately literal: every column arrives as text, and each conversion (German number
format, SAP price units, PLN to EUR, date formats) is a named step, so the profiling and the quality
rules can report exactly what was wrong before it was fixed.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

from .config import PLN_PER_EUR, RAW

FILES = {
    "erp_a_ekpo": ("erp_a_ekpo.csv", ";"), "erp_a_lfa1": ("erp_a_lfa1.csv", ";"), "erp_b_orders": ("erp_b_orders.csv", ","),
    "erp_b_suppliers": ("erp_b_suppliers.csv", ","), "goods_receipts": ("goods_receipts.csv", ","),
    "quality_notifications": ("quality_notifications.csv", ","), "contracts": ("contracts.csv", ","),
    "commodity_indices": ("commodity_indices.csv", ","),
}

# Keyword rules that classify unlabelled lines from their description, checked in this order
CLASSIFIER = [
    ("CU", r"\bcopper\b"), ("ES", r"electrical steel|goes|core lamination"), ("AL", r"\balumin"), ("OI", r"\boil\b|ester|fluid"),
    ("IN", r"pressboard|bushing|insulat|epoxy|crepe"), ("EL", r"tap changer|sensor|cabinet|relay|terminal|pt100"),
    ("ST", r"steel|tank|radiator|heb"), ("LG", r"freight|haulage|transport|container"), ("SV", r"service|licence|cleaning|staff|lab"),
]


def read_raw(raw: Path = RAW) -> dict[str, pd.DataFrame]:
    return {k: pd.read_csv(raw / f, sep=sep, dtype=str, keep_default_na=False) for k, (f, sep) in FILES.items()}


def de_number(s: pd.Series) -> pd.Series:
    """'1.234,50' -> 1234.5"""
    return pd.to_numeric(s.str.replace(".", "", regex=False).str.replace(",", ".", regex=False), errors="coerce")


def classify(description: str) -> str:
    d = description.lower()
    for cat, pattern in CLASSIFIER:
        if re.search(pattern, d):
            return cat
    return "SV"


def terms_days(text: str) -> float:
    """Payment terms in any of the formats found in the masters -> net days."""
    t = str(text).strip().upper()
    if not t:
        return np.nan
    if re.fullmatch(r"\d+", t):
        return float(t)
    m = re.search(r"(\d+)\s*(TAGE NETTO|DAYS NET)", t) or re.fullmatch(r"(?:ZB|Z0|NET)(\d+)", t)
    return float(m.group(1)) if m else np.nan


def harmonise(raw: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """One row per order line from both ERPs, in EUR, with the source issues still visible as flags."""
    a = raw["erp_a_ekpo"]
    per = pd.to_numeric(a.PEINH, errors="coerce").fillna(1)
    la = pd.DataFrame({
        "source": "ERP_A", "line_ref": a.ZLINE.astype(int), "order_no": a.EBELN, "order_date": pd.to_datetime(a.BEDAT, format="%d.%m.%Y"),
        "plant": a.WERKS, "supplier_ref": a.LIFNR, "material_ref": a.MATNR, "description": a.TXZ01, "category_src": a.MATKL,
        "quantity": de_number(a.MENGE), "uom": a.MEINS, "unit_price_eur": de_number(a.NETPR) / per,
        "due_date": pd.to_datetime(a.EINDT, format="%d.%m.%Y")})
    b = raw["erp_b_orders"]
    lb = pd.DataFrame({
        "source": "ERP_B", "line_ref": b.line_ref.astype(int), "order_no": b.order_no, "order_date": pd.to_datetime(b.order_date, format="%Y-%m-%d"),
        "plant": b.plant, "supplier_ref": b.supplier_code, "material_ref": b.material_no, "description": b.description,
        "category_src": b.category, "quantity": pd.to_numeric(b.quantity), "uom": b.uom,
        "unit_price_eur": pd.to_numeric(b.unit_price) / np.where(b.currency == "PLN", PLN_PER_EUR, 1.0),
        "due_date": pd.to_datetime(b.delivery_date, format="%Y-%m-%d")})
    lines = pd.concat([la, lb], ignore_index=True)
    lines["category_inferred"] = lines.description.map(classify)
    lines["category"] = np.where(lines.category_src.eq(""), lines.category_inferred, lines.category_src)
    lines["category_was_blank"] = lines.category_src.eq("")
    return lines
