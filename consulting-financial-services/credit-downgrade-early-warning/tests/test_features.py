import numpy as np
import pandas as pd

from downgrade_ews import config as C, features


def test_issuer_names_and_numbers_are_masked(run, tables):
    sample = run.scored.sample(500, random_state=0)
    names = sample["issuer_id"].map(dict(zip(tables["issuers"]["issuer_id"], tables["issuers"]["issuer_name"].str.lower())))
    assert not any(n in t for n, t in zip(names, sample["text"]))
    assert not sample["text"].str.contains(r"\d").any()


def test_negation_marking():
    assert features.mark_negation("[co] denies reports of liquidity problems.") == \
        "[co] denies neg_reports neg_of neg_liquidity neg_problems."
    assert features.mark_negation("liquidity problems.") == "liquidity problems."


def test_target_matches_rating_actions(run, tables):
    dg = tables["rating_actions"]
    dg = set(zip(*dg[dg["action"] == "downgrade"][["issuer_id", "month"]].values.T))
    p = run.panel[run.panel["labelled"]].sample(400, random_state=1)
    for r in p.itertuples():
        nxt = [(pd.Period(r.month, freq="M") + k).strftime("%Y-%m") for k in range(1, C.HORIZON_MONTHS + 1)]
        assert r.y == int(any((r.issuer_id, m) in dg for m in nxt))
    assert not run.panel[run.panel["month"] > (pd.Period(C.END, freq="M") - C.HORIZON_MONTHS).strftime("%Y-%m")]["labelled"].any()


def test_text_features_only_use_past_articles(run):
    news = run.scored
    p = run.panel.sample(200, random_state=2)
    for r in p.itertuples():
        start = (pd.Period(r.month, freq="M") - 2).strftime("%Y-%m")
        a = news[(news["issuer_id"] == r.issuer_id) & (news["date"].str[:7] >= start) & (news["date"].str[:7] <= r.month)]
        assert r.news_3m == len(a)


def test_financials_are_point_in_time(run, tables):
    fin = tables["financials"]
    p = run.panel.dropna(subset=["leverage"]).sample(200, random_state=3)
    for r in p.itertuples():
        avail = fin[(fin["issuer_id"] == r.issuer_id) & (fin["published"] <= r.month)]
        assert r.leverage == avail.sort_values("quarter_end")["net_debt_to_ebitda"].iloc[-1]


def test_training_articles_have_out_of_fold_scores(run):
    s = run.scored
    train = s[(s["date"].str[:7] <= "2025-03") & s["y"].notna()]
    in_sample = run.text_model.predict_proba(train["text"])[:, 1]
    assert not np.allclose(in_sample, train["p_article"])
