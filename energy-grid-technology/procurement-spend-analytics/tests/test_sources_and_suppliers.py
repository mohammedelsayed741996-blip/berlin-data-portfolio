import pandas as pd

from spendcube import sources as S, suppliers as SU


def test_german_numbers_and_payment_terms():
    assert S.de_number(pd.Series(["1.234,50", "0,75", "12"])).tolist() == [1234.5, 0.75, 12.0]
    assert [S.terms_days(t) for t in ["ZB30", "Z045", "30 Tage netto", "60 days net", "NET30", "14 Tage 2% Skonto, 30 Tage netto", "45"]] == \
        [30, 45, 30, 60, 30, 30, 45]


def test_keyword_classifier_matches_erp_a_material_groups(raw):
    a = raw["erp_a_ekpo"]
    assert (a.TXZ01.map(S.classify) == a.MATKL).all()


def test_classifier_fills_blank_categories_correctly(raw, truth):
    lines = S.harmonise(raw)
    blank = lines[lines.category_was_blank].merge(truth[["line_id", "cat"]], left_on="line_ref", right_on="line_id")
    assert len(blank) > 500
    assert (blank.category == blank.cat).mean() == 1.0


def test_sap_price_unit_and_pln_are_converted(raw, truth):
    lines = S.harmonise(raw).drop_duplicates(["source", "line_ref"])
    m = lines.merge(truth[["line_id", "price_eur"]], left_on="line_ref", right_on="line_id")
    ok = (m.unit_price_eur / m.price_eur).between(0.995, 1.005)
    assert ok.mean() > 0.998          # the rest are the planted per-tonne prices


def test_name_normalisation():
    assert SU.normalise("Saar Draht G.m.b.H. & Co. KG") == SU.normalise("SAAR DRAHT GmbH & Co. KG ") == "saar draht"
    assert SU.legal_form("Ruhr Stahlbau S.A.") != SU.legal_form("Ruhr Stahlbau Sp. z o.o.")


def test_supplier_matching_finds_every_duplicate_without_false_merges(matched, key):
    recs, merges, review = matched
    e = SU.evaluate(recs, key)
    assert e["recall"] == 1.0 and e["precision"] == 1.0
    assert e["golden_records"] == key["true_suppliers"]


def test_conflicting_vat_ids_go_to_review_not_merge():
    m = pd.DataFrame({"supplier_ref": ["1", "2"], "source": "ERP_A", "name": ["Isar Dienste GmbH", "Isar Dienste GmbH"], "country": "DE",
                      "vat_id": ["DE111111111", "DE222222222"], "terms_days": 30, "terms_raw": "ZB30", "blocked": False})
    m["name_norm"] = m.name.map(SU.normalise)
    recs, merges, review = SU.match(m)
    assert recs.golden_id.nunique() == 2
    assert review.not_merged_because.tolist() == ["different VAT IDs"]
