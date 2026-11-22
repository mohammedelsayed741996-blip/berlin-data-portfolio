"""Clean the harmonised lines and build the spend cube as a star schema.

Tables (also exported as CSV for Power BI, see powerbi/):
  fact_po_line   one row per order line, spend in EUR, delivery and quality flags
  dim_supplier   golden supplier records
  dim_material   one row per material across both ERPs
  dim_category   category with the commodity index it follows
  dim_plant, dim_month
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

from .config import CATEGORIES, COUNTRY_RISK, MODEL, PLANTS, ROOT

SQL_DIR = ROOT / "sql"


def clean(lines: pd.DataFrame, recs: pd.DataFrame, raw: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, dict]:
    log = {}
    n0 = len(lines)
    lines = lines.drop_duplicates(["source", "line_ref"]).copy()
    log["duplicate_lines_removed"] = n0 - len(lines)

    med = lines.groupby("description").unit_price_eur.transform("median")
    per_tonne = (lines.unit_price_eur / med).between(300, 3000)
    lines.loc[per_tonne, "unit_price_eur"] /= 1000
    lines["price_corrected"] = per_tonne
    log["prices_corrected_per_tonne"] = int(per_tonne.sum())

    golden = dict(zip(recs.supplier_ref, recs.golden_id))
    lines["supplier_id"] = lines.supplier_ref.map(golden).fillna("S9999")
    log["lines_unknown_supplier"] = int((lines.supplier_id == "S9999").sum())

    lines["is_return"] = lines.quantity < 0
    lines["spend_eur"] = (lines.quantity * lines.unit_price_eur).round(2)

    c = raw["contracts"].copy()
    c["supplier_id"] = c.supplier_ref.map(golden)
    c["valid_from"], c["valid_to"] = pd.to_datetime(c.valid_from), pd.to_datetime(c.valid_to)
    m = lines[["source", "line_ref", "supplier_id", "category", "order_date"]].merge(
        c[["supplier_id", "category", "valid_from", "valid_to", "contract_id"]], on=["supplier_id", "category"], how="left")
    m["valid"] = (m.order_date >= m.valid_from) & (m.order_date <= m.valid_to)
    covered = m[m.valid].drop_duplicates(["source", "line_ref"]).set_index(["source", "line_ref"]).contract_id
    lines = lines.set_index(["source", "line_ref"])
    lines["contract_id"] = covered.reindex(lines.index)
    lines = lines.reset_index()
    cat_has_contract = set(c.category)
    lines["on_contract"] = lines.contract_id.notna()
    had = set(zip(c.supplier_id, c.category))
    lines["contract_status"] = np.where(lines.on_contract, "active",
                                        np.where([(s_, k) in had for s_, k in zip(lines.supplier_id, lines.category)], "expired", "none"))
    lines["maverick"] = ~lines.on_contract & lines.category.isin(cat_has_contract) & ~lines.is_return

    gr = raw["goods_receipts"].assign(line_ref=lambda d: d.line_id.astype(int), receipt_date=lambda d: pd.to_datetime(d.receipt_date))
    lines = lines.merge(gr[["line_ref", "receipt_date"]], on="line_ref", how="left")
    lines.loc[lines.receipt_date < lines.order_date, "receipt_date"] = pd.NaT          # DQ09: unusable receipt
    lines["days_late"] = (lines.receipt_date - lines.due_date).dt.days
    lines["on_time"] = np.where(lines.receipt_date.notna(), lines.days_late <= 2, np.nan)
    qn = raw["quality_notifications"].assign(line_ref=lambda d: d.line_id.astype(int))
    lines["defect"] = lines.line_ref.isin(qn.line_ref)
    lines["month"] = lines.order_date.dt.to_period("M").dt.to_timestamp()
    return lines, log


def build_dims(lines: pd.DataFrame, gold: pd.DataFrame) -> dict[str, pd.DataFrame]:
    gold = gold.copy()
    vat_country = gold.vat_id.str[:2].where(gold.vat_id.str.len() > 2, "")
    gold["country_filled_from_vat"] = gold.country.eq("") & vat_country.ne("")
    gold["country"] = gold.country.where(gold.country.ne(""), vat_country)
    gold["country_risk"] = gold.country.map(COUNTRY_RISK).fillna(2).astype(int)
    unknown = pd.DataFrame([{"golden_id": "S9999", "supplier_name": "Unknown supplier (not in master)", "country": "", "vat_id": "",
                             "terms_days": np.nan, "blocked": False, "source_records": 0, "systems": "", "country_filled_from_vat": False,
                             "country_risk": 3}])
    dim_supplier = pd.concat([gold, unknown], ignore_index=True).rename(columns={"golden_id": "supplier_id"})
    mats = lines.groupby("description").agg(category=("category", "first"), uom=("uom", "first")).reset_index()
    mats.insert(0, "material_id", [f"M{k + 1:03d}" for k in range(len(mats))])
    dim_category = pd.DataFrame([{"category": k, "category_name": v["name"], "commodity_index": v["index"] or "", "spend_type": v["type"]}
                                 for k, v in CATEGORIES.items()])
    dim_plant = pd.DataFrame([{"plant": k, "plant_name": v["name"], "country": v["country"], "source_system": v["system"]} for k, v in PLANTS.items()])
    months = pd.date_range(lines.month.min(), lines.month.max(), freq="MS")
    dim_month = pd.DataFrame({"month": months, "year": months.year, "quarter": "Q" + months.quarter.astype(str), "month_name": months.strftime("%b %Y")})
    return {"dim_supplier": dim_supplier, "dim_material": mats, "dim_category": dim_category, "dim_plant": dim_plant, "dim_month": dim_month}


FACT_COLUMNS = ["source", "line_ref", "order_no", "order_date", "month", "plant", "supplier_id", "material_id", "category", "quantity", "uom",
                "unit_price_eur", "spend_eur", "is_return", "on_contract", "contract_status", "maverick", "contract_id", "due_date", "receipt_date", "days_late",
                "on_time", "defect", "category_was_blank", "price_corrected"]


def build(lines: pd.DataFrame, gold: pd.DataFrame, out: Path = MODEL) -> dict[str, pd.DataFrame]:
    dims = build_dims(lines, gold)
    mid = dict(zip(dims["dim_material"].description, dims["dim_material"].material_id))
    fact = lines.assign(material_id=lines.description.map(mid))[FACT_COLUMNS].sort_values(["order_date", "source", "line_ref"]).reset_index(drop=True)
    tables = {"fact_po_line": fact, **dims}
    out.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        df.to_csv(out / f"{name}.csv", index=False, date_format="%Y-%m-%d")
    return tables


def to_sqlite(tables: dict[str, pd.DataFrame], path: Path | str = ":memory:") -> sqlite3.Connection:
    con = sqlite3.connect(str(path))
    for name, df in tables.items():
        d = df.copy()
        for col in d.columns:
            if pd.api.types.is_datetime64_any_dtype(d[col]):
                d[col] = d[col].dt.strftime("%Y-%m-%d")
            elif d[col].dtype == bool:
                d[col] = d[col].astype(int)
        d.to_sql(name, con, index=False, if_exists="replace")
    con.executescript((SQL_DIR / "views.sql").read_text())
    return con
