import numpy as np

from ppalab import bess as B, crm as C


def test_battery_dp_on_a_known_day():
    rev, act = B.optimise_day(np.array([10, 10, 50, 50, 0, 100.0]))
    # buy 2 MWh at 10, sell at 50 (x0.88, minus 4 degradation each); buy 1 at 0, sell at 100
    assert np.isclose(rev, -20 + 2 * (44 - 4) + (88 - 4))
    assert act.tolist() == [1, 1, -1, -1, 1, -1]


def test_battery_never_loses_money_and_ends_empty():
    rng = np.random.default_rng(0)
    for _ in range(50):
        p = rng.normal(60, 40, 24)
        rev, act = B.optimise_day(p)
        assert rev >= 0 and act.sum() == 0
        assert (np.cumsum(act) >= 0).all() and (np.cumsum(act) <= 2).all()


def test_flat_prices_give_no_trades():
    rev, act = B.optimise_day(np.full(24, 50.0))
    assert rev == 0 and (act == 0).all()


def test_crm_checks_find_planted_problems(data):
    chk = C.checks(data["opp"]).set_index("check").opportunities
    assert chk["Close date missing"] == 6 and chk["Volume is zero"] == 4
    assert chk["Probability does not match stage"] == 5


def test_pipeline_uses_stage_probability_not_typed_value(data):
    opp = data["opp"].copy()
    before = C.pipeline(opp).to_numpy().sum()
    opp.loc[~opp.Stage.str.startswith("Closed"), "Probability (%)"] = 99
    assert np.isclose(C.pipeline(opp).to_numpy().sum(), before)


def test_win_rates_are_shares(data):
    w = C.win_rates(data["opp"])
    assert w.win_rate.between(0, 1).all() and (w.won <= w.closed).all()
