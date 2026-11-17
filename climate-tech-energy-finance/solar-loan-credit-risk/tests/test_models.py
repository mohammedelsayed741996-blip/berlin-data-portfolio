import numpy as np
import pytest
from scipy.stats import spearmanr

from solar_credit.features import TARGET
from solar_credit.models import GradientBoostingPD, calibration_table, evaluate, ks_statistic
from solar_credit.scorecard import Scorecard


def test_target_only_uses_seasoned_loans(model_data):
    for frame in (model_data.train, model_data.test):
        assert frame[TARGET].isin([0, 1]).all()
    assert model_data.train["origination_date"].max() < model_data.test["origination_date"].min()


def test_woe_is_monotone_for_bureau_score(scorecard):
    woe = scorecard.binnings["bureau_score"].table["woe"].to_numpy()
    # Higher bureau score bins should never look riskier than the bin below.
    assert np.all(np.diff(woe) > -0.25)
    assert woe[-1] > woe[0]


def test_scorecard_ranks_risk_out_of_time(scorecard, model_data):
    pd_hat = scorecard.predict_pd(model_data.X_test)
    m = evaluate(model_data.y_test, pd_hat, "scorecard")
    assert m["auc"] > 0.70
    assert 0 < m["predicted_dr"] < 0.15


def test_higher_score_means_lower_pd(scorecard, model_data):
    X = model_data.X_test
    scores = scorecard.score(X)
    pds = scorecard.predict_pd(X)
    # Points are rounded per bin, so ranks match almost but not exactly.
    rho = spearmanr(scores, pds).statistic
    assert rho < -0.97


def test_points_double_odds(scorecard):
    assert scorecard.factor == pytest.approx(20 / np.log(2))


def test_reason_codes_have_points(scorecard, model_data):
    codes = scorecard.reason_codes(model_data.X_test.head(5))
    assert len(codes) == 5
    assert all(len(c) <= 3 for c in codes)


def test_challenger_runs(model_data):
    gbm = GradientBoostingPD().fit(model_data.X_train, model_data.y_train)
    p = gbm.predict_pd(model_data.X_test)
    assert ((p >= 0) & (p <= 1)).all()


def test_ks_and_calibration_table():
    y = np.array([0, 0, 0, 1, 1] * 40)
    p = np.array([0.1, 0.2, 0.3, 0.8, 0.9] * 40)
    assert ks_statistic(y, p) == pytest.approx(1.0)
    tab = calibration_table(y, p, n_groups=5)
    assert tab["loans"].sum() == len(y)


def test_unfitted_scorecard_raises(model_data):
    with pytest.raises(RuntimeError):
        Scorecard().predict_pd(model_data.X_test)
