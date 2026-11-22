"""Supplier master harmonisation: one golden record per real company across both ERPs.

Matching is deliberately simple and explainable, because every merge changes reported spend:
1. same VAT ID -> same company;
2. otherwise the normalised names (case, punctuation, legal form and spacing removed) must agree
   on country (or one side has no country) and reach a token similarity threshold.
Each merge keeps the rule that produced it, so a buyer can review the list before it goes live.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

import pandas as pd

from .sources import terms_days

LEGAL = r"\b(gmbh & co\. kg|g\.m\.b\.h\. & co\. kg|gmbh|g\.m\.b\.h\.|ag|a\.g\.|kg|sp\. ?z ?o\.? ?o\.?|s\.a\.|s\.r\.o\.|ab|s\.p\.a\.|s\.r\.l\.|s\.l\.|a\.s\.|co\. ltd\.|pvt\. ltd\.|inc\.)"


FORM_KEYS = [("gmbh&cokg", r"gmbh & co\.? kg|g\.m\.b\.h\. & co\. kg"), ("gmbh", r"gmbh|g\.m\.b\.h\."), ("ag", r"\bag\b|\ba\.g\."),
             ("spzoo", r"sp\. ?z ?o\.? ?o"), ("sa", r"\bs\.a\."), ("sro", r"s\.r\.o\."), ("ab", r"\bab$"), ("spa", r"s\.p\.a\."),
             ("srl", r"s\.r\.l\."), ("sl", r"\bs\.l\."), ("as", r"\ba\.s\."), ("ltd", r"ltd\."), ("inc", r"inc\.")]


def legal_form(name: str) -> str:
    n = name.lower().strip()
    for key, pattern in FORM_KEYS:
        if re.search(pattern, n):
            return key
    return ""


def normalise(name: str) -> str:
    n = name.lower().strip()
    n = re.sub(LEGAL, " ", n)
    n = re.sub(r"[^a-z0-9 ]", " ", n)
    return re.sub(r"\s+", " ", n).strip()


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def stack_masters(raw: dict[str, pd.DataFrame]) -> pd.DataFrame:
    a, b = raw["erp_a_lfa1"], raw["erp_b_suppliers"]
    sa = pd.DataFrame({"supplier_ref": a.LIFNR, "source": "ERP_A", "name": a.NAME1, "country": a.LAND1, "vat_id": a.STCEG,
                       "terms_days": a.ZTERM.map(terms_days), "terms_raw": a.ZTERM, "blocked": a.SPERR.eq("X")})
    sb = pd.DataFrame({"supplier_ref": b.supplier_code, "source": "ERP_B", "name": b.supplier_name, "country": b.country_code,
                       "vat_id": b.tax_number, "terms_days": pd.to_numeric(b.payment_days, errors="coerce"), "terms_raw": b.payment_days,
                       "blocked": False})
    s = pd.concat([sa, sb], ignore_index=True)
    s["name_norm"] = s.name.map(normalise)
    return s


def match(masters: pd.DataFrame, threshold: float = 0.92) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return (masters with golden_id, merges with the rule that made them, near-matches left for a person to review)."""
    parent = list(range(len(masters)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    merges = []
    recs = masters.reset_index(drop=True)
    for vat, g in recs[recs.vat_id.ne("")].groupby("vat_id"):
        idx = g.index.tolist()
        for j in idx[1:]:
            parent[find(j)] = find(idx[0])
            merges.append({"a": recs.supplier_ref[idx[0]], "b": recs.supplier_ref[j], "rule": "same VAT ID", "score": 1.0})
    recs["form"] = recs.name.map(legal_form)

    def attrs(root):
        members = [k for k in range(len(recs)) if find(k) == root]
        return ({v for v in recs.vat_id[members] if v}, {v for v in recs.form[members] if v}, {v for v in recs.country[members] if v})

    candidates = {}
    for i in range(len(recs)):
        for j in range(i + 1, len(recs)):
            sc = similarity(recs.name_norm[i], recs.name_norm[j])
            if sc >= threshold:
                candidates.setdefault(i, []).append((j, sc))
                candidates.setdefault(j, []).append((i, sc))
    review = []
    for i in range(len(recs)):
        for j, sc in candidates.get(i, []):
            if j < i or find(i) == find(j):
                continue
            (vi, fi, ci), (vj, fj, cj) = attrs(find(i)), attrs(find(j))
            reason = ("different VAT IDs" if vi and vj and vi.isdisjoint(vj) else "different legal forms" if fi and fj and fi.isdisjoint(fj)
                      else "different countries" if ci and cj and ci.isdisjoint(cj) else "")
            # a record without legal form that resembles several distinct companies is ambiguous
            if not reason and len({find(k) for k, _ in candidates[i]} | {find(i)}) > 2 and not recs.form[i]:
                reason = "matches several companies"
            if not reason and len({find(k) for k, _ in candidates[j]} | {find(j)}) > 2 and not recs.form[j]:
                reason = "matches several companies"
            if reason:
                review.append({"a": recs.supplier_ref[i], "b": recs.supplier_ref[j], "name_a": recs.name[i], "name_b": recs.name[j],
                               "score": round(sc, 3), "not_merged_because": reason})
                continue
            parent[find(j)] = find(i)
            merges.append({"a": recs.supplier_ref[i], "b": recs.supplier_ref[j], "rule": "normalised name", "score": round(sc, 3)})
    roots = [find(i) for i in range(len(recs))]
    order = {r: k for k, r in enumerate(dict.fromkeys(roots))}
    recs["golden_id"] = [f"S{order[r] + 1:04d}" for r in roots]
    return recs, pd.DataFrame(merges), pd.DataFrame(review, columns=["a", "b", "name_a", "name_b", "score", "not_merged_because"])


def golden_records(recs: pd.DataFrame) -> pd.DataFrame:
    """Survivorship: ERP_A record first (German plants own the relationship), then most complete values."""
    def pick(g: pd.DataFrame) -> pd.Series:
        g = g.sort_values(["source", "name"], key=lambda c: c.map({"ERP_A": 0, "ERP_B": 1}) if c.name == "source" else c.str.len())
        first = lambda col: next((v for v in g[col] if v not in ("", None) and v == v), "")
        return pd.Series({"supplier_name": g.name.iloc[0].strip(), "country": first("country"), "vat_id": first("vat_id"),
                          "terms_days": g.terms_days.dropna().min() if g.terms_days.notna().any() else float("nan"),
                          "blocked": bool(g.blocked.any()), "source_records": len(g), "systems": ",".join(sorted(set(g.source)))})
    return recs.groupby("golden_id").apply(pick, include_groups=False).reset_index()


def evaluate(recs: pd.DataFrame, key: dict) -> dict:
    """Pairwise precision and recall of the merges against the answer key."""
    truth = {**key["golden_of_erp_a"], **key["golden_of_erp_b"]}
    r = recs[recs.supplier_ref.isin(truth)].copy()
    r["true"] = r.supplier_ref.map(truth)
    tp = fp = fn = 0
    rows = r[["golden_id", "true"]].to_numpy()
    for i in range(len(rows)):
        for j in range(i + 1, len(rows)):
            same_pred, same_true = rows[i][0] == rows[j][0], rows[i][1] == rows[j][1]
            tp += same_pred and same_true
            fp += same_pred and not same_true
            fn += same_true and not same_pred
    return {"true_pairs": tp + fn, "found": tp, "false_merges": fp, "precision": tp / max(tp + fp, 1), "recall": tp / max(tp + fn, 1),
            "records": len(recs), "golden_records": recs.golden_id.nunique(), "true_suppliers": key["true_suppliers"]}
