import re

import numpy as np
import pandas as pd

from downgrade_ews import config as C, data


def test_generation_is_deterministic():
    a = data.generate()
    b = data.generate()
    pd.testing.assert_frame_equal(a["news"], b["news"])
    pd.testing.assert_frame_equal(a["rating_actions"], b["rating_actions"])


def test_issuers_are_synthetic_and_unique(tables):
    iss = tables["issuers"]
    assert len(iss) == C.N_ISSUERS and iss["issuer_name"].is_unique
    assert iss["issuer_id"].str.fullmatch(r"ISS\d{4}").all()


def test_news_contains_no_personal_data(tables):
    text = " ".join(tables["news"]["headline"]) + " " + " ".join(tables["news"]["body"].head(5000))
    assert not re.search(r"@|\+\d{2}\s?\d|\bMr\.|\bMrs\.|\bHerr\b|\bFrau\b", text)


def test_news_mix(tables):
    n = tables["news"]
    assert 0.25 < (n["language"] == "de").mean() < 0.40
    assert len(n) > 50_000
    assert n["date"].str[:7].between(C.START, C.END).all()


def test_downgrade_frequency_is_plausible(tables):
    dg = tables["rating_actions"]
    dg = dg[dg["action"] == "downgrade"]
    per_year = len(dg) / (len(pd.period_range(C.START, C.END, freq="M")) / 12)
    assert 0.10 < per_year / C.N_ISSUERS < 0.22


def test_agency_lags_the_latent_credit_path(tables):
    lat = tables["latent"].set_index(["issuer_id", "month"])
    dg = tables["rating_actions"]
    dg = dg[dg["action"] == "downgrade"]
    gaps = [lat.loc[(r.issuer_id, (pd.Period(r.month, freq="M") - 1).strftime("%Y-%m")), "stress_gap"]
            for r in dg.itertuples() if r.month > C.START]
    assert np.median(gaps) > 0.8       # the month before a downgrade, quality is already well below the rating


def test_financials_are_published_two_months_after_quarter_end(tables):
    f = tables["financials"]
    lag = pd.PeriodIndex(f["published"], freq="M") - pd.PeriodIndex(f["quarter_end"], freq="M")
    assert all(x.n == 2 for x in lag)
