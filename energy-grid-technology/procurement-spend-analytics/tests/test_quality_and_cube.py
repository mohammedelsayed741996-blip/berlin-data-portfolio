from spendcube import quality as Q, sources as S, suppliers as SU
from spendcube.analytics import headline, kraljic, q, supplier_scorecard


def test_every_planted_problem_is_found(raw, matched, key):
    recs, _, review = matched
    dq = Q.run(raw, S.harmonise(raw), recs, review)
    found = Q.score_against_key(dq, key, SU.evaluate(recs, key))
    assert (found.found == found.planted).all(), found
    assert dq.set_index("id").failing["DQ12"] == 0
    sc = Q.scorecard(dq)
    assert ((sc.fillna(1) >= 0) & (sc.fillna(1) <= 1)).all().all()


def test_rules_file_is_complete():
    for r in Q.load_rules():
        assert {"id", "dataset", "dimension", "rule", "severity", "owner", "action"} <= set(r)
        assert r["dimension"] in {"completeness", "uniqueness", "validity", "consistency", "timeliness"}


def test_cube_reconciles_to_true_spend(model, truth, key):
    tables, con, log = model
    f = tables["fact_po_line"]
    assert log["duplicate_lines_removed"] == key["duplicate_po_lines_erp_a"]
    assert log["prices_corrected_per_tonne"] == len(key["price_per_tonne_on_kg_lines_erp_b"])
    assert len(f) == len(truth)
    ours = (f.quantity.abs() * f.unit_price_eur).sum()
    true = (truth.qty * truth.price_eur).sum()
    assert abs(ours / true - 1) < 1e-4


def test_views(model):
    _, con, _ = model
    p = q(con, "SELECT * FROM v_supplier_pareto")
    assert abs(p.cumulative_share.iloc[-1] - 1) < 1e-3 and p.cumulative_share.is_monotonic_increasing
    c = q(con, "SELECT * FROM v_category_concentration")
    assert c.hhi.between(0, 10000).all()
    cat = q(con, "SELECT * FROM v_spend_by_category")
    assert abs(cat.share_pct.sum() - 100) < 0.5


def test_headline_and_scorecards(model):
    _, con, _ = model
    h = headline(con)
    assert 0 < h["on_contract_share"] < 1 and abs(h["maverick_expired_contract_eur"] + h["maverick_no_contract_eur"] - h["maverick_eur"]) < 1
    s = supplier_scorecard(con)
    assert s.score.between(0, 100).all()
    k = kraljic(con, {"copper": 0.05, "goes": 0.04, "steel_hrc": 0.07, "aluminium": 0.04, "oil": 0.07})
    assert set(k.quadrant) <= {"Strategic", "Leverage", "Bottleneck", "Non-critical"}
    assert k.set_index("category").quadrant["CU"] == "Strategic"
