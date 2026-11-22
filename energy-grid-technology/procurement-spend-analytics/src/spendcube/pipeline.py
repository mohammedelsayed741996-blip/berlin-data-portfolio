"""Run everything: raw exports -> quality rules -> golden suppliers -> spend cube -> analytics -> forecasts -> reports.

    PYTHONPATH=src python -m spendcube.pipeline [--regenerate]
"""

from __future__ import annotations

import argparse
import json

import pandas as pd

from . import analytics as A
from . import cube as C
from . import forecast as F
from . import generate, profiling, quality as Q, sources as S, suppliers as SU
from .config import MODEL, OUTPUTS, RAW


def load_indices(raw) -> pd.DataFrame:
    ind = raw["commodity_indices"].copy()
    ind["month"] = pd.to_datetime(ind.month)
    return ind.astype({c: float for c in ind.columns if c != "month"})


def run(regenerate: bool = False, reports: bool = True) -> dict:
    if regenerate or not (RAW / "erp_a_ekpo.csv").exists():
        generate.write()
    raw = S.read_raw()
    key = json.loads((RAW / "_answer_key.json").read_text())

    recs, merges, review = SU.match(SU.stack_masters(raw))
    gold = SU.golden_records(recs)
    harmonised = S.harmonise(raw)
    dq = Q.run(raw, harmonised, recs, review)
    match_eval = SU.evaluate(recs, key)
    found = Q.score_against_key(dq, key, match_eval)

    lines, clean_log = C.clean(harmonised, recs, raw)
    tables = C.build(lines, gold)
    con = C.to_sqlite(tables, MODEL / "spendcube.db" if reports else ":memory:")

    ind = load_indices(raw)
    vol = F.volatility(ind)
    head = A.headline(con)
    cats = A.q(con, "SELECT * FROM v_spend_by_category ORDER BY spend_eur DESC")
    kr = A.kraljic(con, vol)
    score = A.supplier_scorecard(con)
    pareto = A.q(con, "SELECT * FROM v_supplier_pareto")

    bt = F.backtest(ind)
    fsum = F.summarise(bt)
    chosen = fsum.chosen.to_dict()
    cover = F.coverage(bt, ind, chosen)
    fc = F.forecast(ind, chosen)
    pt = F.pass_through(tables["fact_po_line"], ind)
    impact = F.budget_impact(tables["fact_po_line"], ind, fc, pt)

    result = {
        "data_quality": {"rules": len(dq), "rules_with_findings": int((dq.failing > 0).sum()),
                         "planted_problems_found": f"{int(found.found.sum())} of {int(found.planted.sum())}",
                         "all_planted_found": bool((found.found == found.planted).all()), "cleaning": clean_log},
        "supplier_matching": {k: (round(v, 3) if isinstance(v, float) else v) for k, v in match_eval.items()} | {"left_for_review": len(review)},
        "spend": {k: (round(v, 4) if isinstance(v, float) else v) for k, v in head.items()},
        "forecast": {"backtest_mape_naive_by_index": fsum["naive_mape"].round(4).to_dict(),
                     "best_skill_vs_naive_by_index": fsum.filter(like="_skill").max(axis=1).round(3).to_dict(),
                     "models_chosen": chosen, "band_coverage_80pct": round(cover, 3)},
        "pass_through": pt.round(3).to_dict("records"),
        "budget_impact_6m_eur": {r.category: {"expected": round(r.impact_eur_6m_expected), "low": round(r.impact_eur_6m_low), "high": round(r.impact_eur_6m_high)}
                                 for r in impact.itertuples()},
    }
    if reports:
        from . import reporting as R
        OUTPUTS.mkdir(exist_ok=True)
        profiling.write_docs(profiling.profile(raw))
        dq.to_csv(OUTPUTS / "dq_results.csv", index=False)
        found.to_csv(OUTPUTS / "dq_planted_vs_found.csv", index=False)
        Q.scorecard(dq).to_csv(OUTPUTS / "dq_scorecard.csv")
        merges.to_csv(OUTPUTS / "supplier_merges.csv", index=False)
        review.to_csv(OUTPUTS / "supplier_review_queue.csv", index=False)
        score.to_csv(OUTPUTS / "supplier_scorecard.csv", index=False)
        kr.to_csv(OUTPUTS / "kraljic.csv", index=False)
        fsum.to_csv(OUTPUTS / "forecast_backtest_summary.csv")
        fc.to_csv(OUTPUTS / "commodity_forecast.csv", index=False)
        impact.to_csv(OUTPUTS / "budget_impact.csv", index=False)
        (OUTPUTS / "results.json").write_text(json.dumps(result, indent=2, default=str))
        ctx = dict(con=con, dq=dq, found=found, head=head, cats=cats, kr=kr, score=score, pareto=pareto, bt=bt, fsum=fsum, fc=fc,
                   ind=ind, pt=pt, impact=impact, review=review, merges=merges, result=result, tables=tables)
        R.figures(ctx)
        R.excel(ctx)
        R.deck(ctx)
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--regenerate", action="store_true")
    a = ap.parse_args()
    print(json.dumps(run(a.regenerate), indent=2, default=str))
