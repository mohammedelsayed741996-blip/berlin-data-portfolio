"""Generate the raw exports a procurement data team would actually receive.

Two ERP systems (ERP_A for the German plants, ERP_B for the Polish plant) export purchase order lines,
goods receipts and supplier masters in their own formats. A contracts list, quality notifications and
monthly commodity price indices complete the picture.

Data problems are planted on purpose and written to an answer key (raw/_answer_key.json) so the data
quality checks can be scored. The pipeline never reads the answer key; only tests and the evaluation do.
"""

from __future__ import annotations

import json
from datetime import date, timedelta

import numpy as np
import pandas as pd

from .config import CATEGORIES, END, INDEX_START, INDICES, PLANTS, PLN_PER_EUR, RAW, SEED, START

CAT_SHARE = {"CU": 0.30, "ES": 0.19, "ST": 0.10, "AL": 0.05, "OI": 0.05, "IN": 0.11, "EL": 0.10, "LG": 0.05, "SV": 0.05}

MATERIALS = {
    "CU": [("Copper flat wire 10x2 mm, enamelled", "KG", 11.5), ("Copper winding wire CTC 40 strands", "KG", 13.2),
           ("Copper busbar 60x10 mm", "KG", 10.4), ("Copper round wire 3.0 mm", "KG", 10.9), ("Copper strip 100x3 mm", "KG", 10.6),
           ("Copper lead cable 240 mm2", "KG", 12.1)],
    "ES": [("Grain-oriented electrical steel 0.27 mm", "KG", 3.4), ("Grain-oriented electrical steel 0.23 mm Hi-B", "KG", 3.9),
           ("Laser-scribed GOES 0.23 mm", "KG", 4.4), ("Core lamination stack, cut", "KG", 4.9)],
    "ST": [("Steel plate S355 12 mm", "KG", 1.15), ("Steel plate S235 8 mm", "KG", 1.05), ("Tank cover, welded", "PC", 2350.0),
           ("Steel profile HEB 200", "KG", 1.25), ("Radiator panel 520 mm", "PC", 410.0)],
    "AL": [("Aluminium busbar 80x10 mm", "KG", 4.8), ("Aluminium foil winding 1.0 mm", "KG", 5.6), ("Aluminium cast housing", "PC", 185.0)],
    "OI": [("Mineral transformer oil, inhibited", "L", 1.45), ("Natural ester transformer fluid", "L", 4.10)],
    "IN": [("Pressboard 3 mm", "KG", 6.8), ("Condenser bushing 145 kV", "PC", 5200.0), ("Condenser bushing 36 kV", "PC", 980.0),
           ("Insulating paper crepe", "KG", 9.5), ("Epoxy spacer", "PC", 38.0), ("Composite insulator 110 kV", "PC", 640.0)],
    "EL": [("Tap changer motor drive", "PC", 7400.0), ("Monitoring sensor DGA", "PC", 3100.0), ("Control cabinet, wired", "PC", 4600.0),
           ("Temperature sensor PT100", "PC", 42.0), ("Relay protection unit", "PC", 2650.0), ("Terminal block set", "PC", 3.2)],
    "LG": [("Heavy haulage transport", "EA", 18500.0), ("Sea freight container", "EA", 3200.0), ("Road freight, full truck", "EA", 1450.0)],
    "SV": [("Calibration service", "EA", 880.0), ("IT software licence", "EA", 2400.0), ("Facility cleaning, monthly", "EA", 3900.0),
           ("Temporary staff, engineering", "EA", 7200.0), ("Test lab service", "EA", 5600.0)],
}

SYLLABLES = ["Havel", "Spree", "Oder", "Elbe", "Saale", "Weser", "Mulde", "Neisse", "Warta", "Vistula", "Tauber", "Lahn", "Ruhr",
             "Isar", "Lech", "Inn", "Main", "Mosel", "Saar", "Ems", "Fulda", "Werra", "Unstrut", "Pegnitz", "Regen", "Ilm", "Nahe"]
STEMS = {"CU": ["Kupferwerk", "Draht", "Leiter"], "ES": ["Elektroband", "Kernblech", "Magnetstahl"], "ST": ["Stahlbau", "Blechwerk", "Stahl"],
         "AL": ["Aluguss", "Leichtmetall", "Alu"], "OI": ["Isolieroel", "Fluid", "Oelwerk"], "IN": ["Isolation", "Durchfuehrung", "Isotech"],
         "EL": ["Elektronik", "Regeltechnik", "Sensorik"], "LG": ["Spedition", "Logistik", "Transport"], "SV": ["Service", "Technik", "Dienste"]}
FORMS = {"DE": ["GmbH", "AG", "GmbH & Co. KG"], "AT": ["GmbH"], "PL": ["Sp. z o.o.", "S.A."], "CZ": ["s.r.o."], "SE": ["AB"], "IT": ["S.p.A.", "S.r.l."],
         "ES": ["S.L."], "TR": ["A.S."], "CN": ["Co. Ltd."], "IN": ["Pvt. Ltd."], "KR": ["Co. Ltd."], "US": ["Inc."]}
COUNTRY_MIX = {"CU": {"DE": .5, "PL": .2, "SE": .1, "TR": .1, "CN": .1}, "ES": {"DE": .3, "AT": .2, "KR": .2, "CN": .2, "IN": .1},
               "ST": {"DE": .5, "PL": .3, "CZ": .2}, "AL": {"DE": .5, "IT": .3, "TR": .2}, "OI": {"DE": .4, "SE": .3, "US": .3},
               "IN": {"DE": .4, "IT": .2, "SE": .2, "CN": .2}, "EL": {"DE": .5, "AT": .2, "CZ": .1, "CN": .2},
               "LG": {"DE": .6, "PL": .4}, "SV": {"DE": .8, "PL": .2}}
ANCHOR_2024 = {"copper": 8600.0, "aluminium": 2250.0, "steel_hrc": 610.0, "goes": 3100.0, "oil": 880.0}   # EUR per tonne, 2024 average
SUPPLIERS_PER_CAT = {"CU": 9, "ES": 5, "ST": 14, "AL": 7, "OI": 4, "IN": 16, "EL": 18, "LG": 12, "SV": 30}


def months(a: date, b: date) -> pd.DatetimeIndex:
    return pd.date_range(pd.Timestamp(a).to_period("M").to_timestamp(), pd.Timestamp(b).to_period("M").to_timestamp(), freq="MS")


def commodity_indices(rng) -> pd.DataFrame:
    """Monthly indices in EUR per tonne: geometric random walk with drift, seasonality and a 2021-22 energy-crisis bump."""
    idx = months(INDEX_START, END)
    t = np.arange(len(idx))
    out = {"month": idx}
    shock = np.exp(-0.5 * ((t - 40) / 6.0) ** 2)               # peaks around May 2022
    for name, (level, drift, vol, season) in INDICES.items():
        eps = rng.normal(drift / 12 - vol**2 / 2, vol, len(t))
        path = level * np.exp(np.cumsum(eps))
        bump = {"steel_hrc": 0.55, "oil": 0.45, "aluminium": 0.35, "copper": 0.12, "goes": 0.3}[name]
        path *= (1 + bump * shock) * (1 + season * np.sin(2 * np.pi * (idx.month - 3) / 12))
        out[name] = path
    df = pd.DataFrame(out)
    in_2024 = df.month.dt.year == 2024
    for name, anchor in ANCHOR_2024.items():
        df[name] = (df[name] * anchor / df.loc[in_2024, name].mean()).round(1)
    return df


def _name(rng, cat, country, used):
    while True:
        n = f"{rng.choice(SYLLABLES)} {rng.choice(STEMS[cat])} {rng.choice(FORMS[country])}"
        if n not in used:
            used.add(n)
            return n


def _variant(name: str, rng) -> str:
    """How the same company gets typed into a second system."""
    choice = rng.integers(0, 4)
    if choice == 0:
        return name.upper()
    if choice == 1:
        return name.replace("GmbH", "G.m.b.H.").replace("Sp. z o.o.", "Sp.z.o.o.").replace("AG", "A.G.")
    if choice == 2:
        return " ".join(name.split()[:2])                         # legal form dropped
    return name.replace(" ", "  ", 1) + " "                        # double space, trailing space


def build(seed: int = SEED) -> dict:
    rng = np.random.default_rng(seed)
    key: dict = {}
    indices = commodity_indices(rng)

    # ---------------------------------------------------------------- true suppliers
    used, sup = set(), []
    for cat, n in SUPPLIERS_PER_CAT.items():
        mix = COUNTRY_MIX[cat]
        for _ in range(n):
            country = rng.choice(list(mix), p=list(mix.values()))
            sup.append({"golden_id": f"G{len(sup) + 1:04d}", "name": _name(rng, cat, country, used), "country": country, "category": cat,
                        "premium": rng.normal(0, 0.035), "otd": float(np.clip(rng.beta(9, 1.4), 0.55, 0.995)),
                        "defect_rate": float(np.clip(rng.gamma(1.3, 0.008), 0.0005, 0.08)), "lead_days": int(rng.integers(10, 90))})
    sup = pd.DataFrame(sup)
    sup["vat_id"] = [f"{c}{rng.integers(10**8, 10**9)}" for c in sup.country]
    # supplier preference: a few suppliers win most of each category (Pareto)
    sup["weight"] = rng.pareto(1.3, len(sup)) + 0.05

    # which system knows which supplier: German plants buy from most, the Polish plant from a subset
    in_a = rng.random(len(sup)) < 0.85
    in_b = (rng.random(len(sup)) < 0.35) | (sup.country == "PL").to_numpy()
    in_a |= ~in_b
    sup["in_a"], sup["in_b"] = in_a, in_b

    # ---------------------------------------------------------------- supplier masters
    terms_a = ["ZB30", "ZB45", "ZB60", "Z030", "30 Tage netto", "45 Tage netto", "60 days net", "NET30", "14 Tage 2% Skonto, 30 Tage netto"]
    rows_a, rows_b = [], []
    for i, s in sup.iterrows():
        days = int(rng.choice([30, 45, 60, 90], p=[.35, .3, .25, .1]))
        if s.in_a:
            rows_a.append({"LIFNR": f"{1000000 + i * 7}", "NAME1": s["name"], "LAND1": s.country, "STCEG": s.vat_id,
                           "ZTERM": rng.choice([t for t in terms_a if str(days) in t] or terms_a), "ERDAT": "", "SPERR": "", "_golden": s.golden_id})
        if s.in_b:
            rows_b.append({"supplier_code": f"PLS-{5000 + i}", "supplier_name": s["name"] if not s.in_a else _variant(s["name"], rng),
                           "country_code": s.country, "tax_number": s.vat_id if rng.random() > 0.3 else "", "payment_days": days, "_golden": s.golden_id})
    ma, mb = pd.DataFrame(rows_a), pd.DataFrame(rows_b)
    ma["ERDAT"] = [(date(2012, 1, 1) + timedelta(days=int(d))).strftime("%d.%m.%Y") for d in rng.integers(0, 4500, len(ma))]

    # planted: duplicate supplier records inside ERP_A (same company created twice)
    dup_src = ma.sample(9, random_state=seed)
    dups = dup_src.copy()
    dups["LIFNR"] = [f"{2000000 + k}" for k in range(len(dups))]
    dups["NAME1"] = [_variant(n, rng) for n in dups.NAME1]
    dups.loc[dups.index[::2], "STCEG"] = ""
    ma = pd.concat([ma, dups], ignore_index=True)
    # planted: missing country
    miss = ma.sample(14, random_state=seed + 1).index
    ma.loc[miss, "LAND1"] = ""
    # planted: one blocked supplier still receiving orders
    ma["SPERR"] = ""
    blocked = ma[~ma.LIFNR.isin(dups.LIFNR)].sample(1, random_state=seed + 2).LIFNR.iloc[0]
    ma.loc[ma.LIFNR == blocked, "SPERR"] = "X"
    key["duplicate_supplier_records_in_erp_a"] = len(dups)
    key["cross_system_supplier_pairs"] = int((sup.in_a & sup.in_b).sum())
    key["missing_supplier_country"] = len(miss)
    key["blocked_supplier_with_orders"] = blocked

    # ---------------------------------------------------------------- materials
    mats = []
    for cat, items in MATERIALS.items():
        for j, (desc, unit, price) in enumerate(items):
            mats.append({"cat": cat, "desc": desc, "unit": unit, "p0": price, "mat_a": f"{cat}-{100 + j}", "mat_b": f"M{rng.integers(10000, 99999)}"})
    mats = pd.DataFrame(mats)

    # contracts: the top suppliers per category have a framework agreement
    contracts = []
    for cat, g in sup.groupby("category"):
        top = g.sort_values("weight", ascending=False).head(max(2, len(g) // 3))
        for _, s in top.iterrows():
            contracts.append({"contract_id": f"FA-{len(contracts) + 1:03d}", "golden_id": s.golden_id, "category": cat,
                              "valid_from": "2024-01-01", "valid_to": "2027-12-31" if rng.random() > .2 else "2025-12-31",
                              "index_clause": CATEGORIES[cat]["index"] or ""})
    contracts = pd.DataFrame(contracts)

    # ---------------------------------------------------------------- purchase order lines
    ind = indices.set_index("month")
    ref = ind.loc["2024-01-01":"2024-12-01"].mean()
    lines, po_no = [], {"ERP_A": 4500000000, "ERP_B": 70000}
    pools = {}
    for sys_ in ("ERP_A", "ERP_B"):
        for cat in CAT_SHARE:
            cand = sup[(sup.category == cat) & (sup.in_a if sys_ == "ERP_A" else sup.in_b)]
            cand = cand if not cand.empty else sup[sup.category == cat]
            pools[sys_, cat] = (cand.index.to_numpy(), (cand.weight / cand.weight.sum()).to_numpy())
    mat_idx = {cat: mats.index[mats.cat == cat].to_numpy() for cat in CAT_SHARE}
    factors = {}
    for cat, c in CATEGORIES.items():
        if c["index"]:
            factors[cat] = 1 - c["weight"] + c["weight"] * ind[c["index"]].shift(c["lag"]) / ref[c["index"]]
    cats, probs = list(CAT_SHARE), list(CAT_SHARE.values())
    for m in months(START, END):
        for plant, p in PLANTS.items():
            n = int(rng.poisson(230 if p["system"] == "ERP_A" else 150) * (0.85 if m.month in (8, 12) else 1.0))
            sys = p["system"]
            for _ in range(n):
                cat = cats[rng.choice(len(cats), p=probs)]
                ids, w = pools[sys, cat]
                s = sup.loc[ids[rng.choice(len(ids), p=w)]]
                mat = mats.loc[mat_idx[cat][rng.integers(len(mat_idx[cat]))]]
                factor = factors[cat].loc[m] if cat in factors else 1.0
                price = mat.p0 * factor * (1 + s.premium) * rng.normal(1, 0.015)
                if mat.unit in ("KG", "L"):
                    qty = float(np.round(rng.lognormal(np.log(2500 if cat in ("CU", "ES", "ST") else 900), 0.8), 0))
                elif cat in ("LG", "SV"):
                    qty = float(rng.integers(1, 4))
                else:
                    qty = float(rng.integers(1, 40 if mat.p0 > 500 else 400))
                po_date = m + pd.Timedelta(days=int(rng.integers(0, 28)))
                due = po_date + pd.Timedelta(days=int(s.lead_days))
                late = rng.random() > s.otd
                gr = due + pd.Timedelta(days=int(rng.integers(3, 30)) if late else -int(rng.integers(0, 4)))
                po_no[sys] += 1
                lines.append({"system": sys, "plant": plant, "po": po_no[sys], "po_date": po_date, "golden_id": s.golden_id, "cat": cat,
                              "mat_a": mat.mat_a, "mat_b": mat.mat_b, "desc": mat.desc, "unit": mat.unit, "qty": qty,
                              "price_eur": round(price, 4), "due": due, "gr": gr, "defect": rng.random() < s.defect_rate * (3 if cat in ("IN", "EL") else 1)})
    lines = pd.DataFrame(lines)
    lines["line_id"] = np.arange(len(lines))

    gid_a = ma.drop_duplicates("_golden").set_index("_golden").LIFNR
    gid_b = mb.set_index("_golden").supplier_code

    # ---------------------------- ERP_A export (German formats, price unit per 100 for cheap items)
    la = lines[lines.system == "ERP_A"].copy()
    la["per"] = np.where(la.price_eur < 5, 100, 1)
    a = pd.DataFrame({
        "EBELN": la.po.astype(str), "EBELP": "00010", "BEDAT": la.po_date.dt.strftime("%d.%m.%Y"), "WERKS": la.plant,
        "LIFNR": la.golden_id.map(gid_a), "MATNR": la.mat_a, "TXZ01": la.desc, "MATKL": la.cat,
        "MENGE": la.qty.map(lambda x: f"{x:,.3f}".replace(",", "X").replace(".", ",").replace("X", ".")),
        "MEINS": la.unit, "NETPR": (la.price_eur * la.per).map(lambda x: f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")),
        "PEINH": la.per.astype(str), "WAERS": "EUR", "EINDT": la.due.dt.strftime("%d.%m.%Y"), "_line": la.line_id})
    # planted: lines whose supplier was created twice are partly booked on the duplicate account
    dup_map = dict(zip(dup_src.LIFNR, dups.LIFNR))
    on_dup = a.LIFNR.isin(dup_map) & (rng.random(len(a)) < 0.35)
    a.loc[on_dup, "LIFNR"] = a.loc[on_dup, "LIFNR"].map(dup_map)
    # planted: orders on the blocked supplier after it was blocked
    # planted: supplier numbers missing in the master (one-time vendors)
    orphan = a.sample(12, random_state=seed + 3).index
    a.loc[orphan, "LIFNR"] = [f"{9900000 + k}" for k in range(12)]
    # planted: export overlap creates exact duplicate lines
    overlap = a.sample(40, random_state=seed + 4)
    a = pd.concat([a, overlap], ignore_index=True)
    key["duplicate_po_lines_erp_a"] = 40
    key["orphan_supplier_lines_erp_a"] = 12

    # ---------------------------- ERP_B export (ISO dates, PLN, category often blank, unit mistakes)
    lb = lines[lines.system == "ERP_B"].copy()
    b = pd.DataFrame({"order_no": "B" + lb.po.astype(str), "order_date": lb.po_date.dt.strftime("%Y-%m-%d"), "plant": lb.plant,
                      "supplier_code": lb.golden_id.map(gid_b), "material_no": lb.mat_b, "description": lb.desc,
                      "category": lb.cat, "quantity": lb.qty, "uom": lb.unit, "unit_price": (lb.price_eur * PLN_PER_EUR).round(2),
                      "currency": "PLN", "delivery_date": lb.due.dt.strftime("%Y-%m-%d"), "_line": lb.line_id})
    blank = b.sample(frac=0.18, random_state=seed + 5).index
    b.loc[blank, "category"] = ""
    key["unclassified_lines_erp_b"] = len(blank)
    kg_cu = b[(b.uom == "KG") & b.description.str.startswith("Copper")].sample(20, random_state=seed + 6).index
    b.loc[kg_cu, "unit_price"] = (b.loc[kg_cu, "unit_price"] * 1000).round(2)       # price per tonne typed on a per-kg line
    key["price_per_tonne_on_kg_lines_erp_b"] = sorted(b.loc[kg_cu, "_line"].astype(int).tolist())
    ret = b.sample(18, random_state=seed + 7).index
    b.loc[ret, "quantity"] = -b.loc[ret, "quantity"]                                 # returns booked as negative quantity
    key["negative_quantity_lines_erp_b"] = 18
    b.loc[b.supplier_code.isna(), "supplier_code"] = ""

    # ---------------------------------------------------------------- goods receipts and quality notifications
    gr = lines[["line_id", "gr", "qty", "po_date", "defect"]].copy()
    gr = gr[gr.gr <= pd.Timestamp(END)]
    early = gr.sample(15, random_state=seed + 8).index
    gr.loc[early, "gr"] = gr.loc[early, "po_date"] - pd.Timedelta(days=5)              # receipt before the order: a booking error
    key["receipt_before_order"] = 15
    receipts = pd.DataFrame({"line_id": gr.line_id, "receipt_date": gr.gr.dt.strftime("%Y-%m-%d"), "received_qty": gr.qty})
    qn = gr[gr.defect]
    quality = pd.DataFrame({"notification": [f"QN{70000 + k}" for k in range(len(qn))], "line_id": qn.line_id.to_numpy(),
                            "defect_code": rng.choice(["DIM", "SURF", "DOC", "ELEC", "PACK"], len(qn)),
                            "rejected_qty": np.maximum(1, (qn.qty.abs() * rng.uniform(0.01, 0.2, len(qn))).round()).to_numpy()})

    key["true_suppliers"] = len(sup)
    return {"indices": indices, "supplier_master_erp_a": ma, "supplier_master_erp_b": mb, "po_lines_erp_a": a, "po_lines_erp_b": b,
            "goods_receipts": receipts, "quality_notifications": quality, "contracts": contracts, "_truth_lines": lines, "_truth_suppliers": sup,
            "_key": key}


def write(raw=RAW, seed: int = SEED) -> dict:
    """Write the exports the way the source systems deliver them."""
    raw.mkdir(parents=True, exist_ok=True)
    d = build(seed)
    d["indices"].assign(month=d["indices"].month.dt.strftime("%Y-%m")).to_csv(raw / "commodity_indices.csv", index=False)
    d["supplier_master_erp_a"].drop(columns="_golden").to_csv(raw / "erp_a_lfa1.csv", sep=";", index=False)
    d["supplier_master_erp_b"].drop(columns="_golden").to_csv(raw / "erp_b_suppliers.csv", index=False)
    d["po_lines_erp_a"].rename(columns={"_line": "ZLINE"}).to_csv(raw / "erp_a_ekpo.csv", sep=";", index=False)
    d["po_lines_erp_b"].rename(columns={"_line": "line_ref"}).to_csv(raw / "erp_b_orders.csv", index=False)
    d["goods_receipts"].to_csv(raw / "goods_receipts.csv", index=False)
    d["quality_notifications"].to_csv(raw / "quality_notifications.csv", index=False)
    contracts = d["contracts"].copy()
    # contracts reference ERP_A supplier numbers where they exist, else ERP_B codes
    ga = d["supplier_master_erp_a"].drop_duplicates("_golden").set_index("_golden").LIFNR
    gb = d["supplier_master_erp_b"].set_index("_golden").supplier_code
    contracts["supplier_ref"] = contracts.golden_id.map(ga).fillna(contracts.golden_id.map(gb))
    contracts.drop(columns="golden_id").to_csv(raw / "contracts.csv", index=False)
    truth = {**d["_key"],
             "golden_of_erp_a": dict(zip(d["supplier_master_erp_a"].LIFNR, d["supplier_master_erp_a"]._golden)),
             "golden_of_erp_b": dict(zip(d["supplier_master_erp_b"].supplier_code, d["supplier_master_erp_b"]._golden))}
    (raw / "_answer_key.json").write_text(json.dumps(truth, indent=1, default=str))
    d["_truth_lines"].to_csv(raw / "_truth_lines.csv.gz", index=False)
    return d
