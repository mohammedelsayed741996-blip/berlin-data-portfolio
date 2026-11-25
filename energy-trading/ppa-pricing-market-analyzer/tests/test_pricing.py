import numpy as np
import pandas as pd

from ppalab import pricing as P


def test_hpfc_matches_traded_base_and_peak(data):
    c = P.hpfc(data["hourly"], 2027, 80.0, 92.0)
    assert np.isclose(c.price.mean(), 80.0) and np.isclose(c[c.is_peak].price.mean(), 92.0)
    assert len(c) == 8760
    mid = c[(c.timestamp.dt.month == 6) & (c.timestamp.dt.hour == 13)].price.mean()
    eve = c[(c.timestamp.dt.month == 6) & (c.timestamp.dt.hour == 20)].price.mean()
    assert mid < eve                                                       # summer middays are cheap


def test_scenarios_average_to_the_forward(scen, data):
    fwd = data["curve"].set_index("year").base_eur_mwh
    for y in (2027, 2028):
        mean = np.mean([s[s.year == y].price_eur_mwh.mean() for s in scen])
        assert abs(mean / fwd[y] - 1) < 1e-9


def test_offer_walk_adds_up(scen):
    for tech in ("solar", "wind"):
        o = P.offer(P.asset_stats(scen, tech, 10), tech, 2, "BBB")
        assert np.isclose(o["forward_base"] + o["shape"] + o["curtailment_uplift"], o["expected_capture"])
        parts = ["balancing", "hedging", "profile_risk", "volume_risk", "credit", "margin"]
        assert np.isclose(o["expected_capture"] + sum(o[p] for p in parts), o["offer_price"])
        assert all(o[p] <= 0 for p in parts)
    s, w = (P.offer(P.asset_stats(scen, t, 10), t, 2, "BBB") for t in ("solar", "wind"))
    assert s["capture_rate"] < w["capture_rate"] and s["curtailed_share"] > w["curtailed_share"]


def test_worse_credit_lowers_the_offer(scen):
    st = P.asset_stats(scen, "solar", 10)
    assert P.offer(st, "solar", 2, "B")["offer_price"] < P.offer(st, "solar", 2, "AA")["offer_price"]


def test_structures_trade_return_for_risk(scen):
    st = P.asset_stats(scen, "solar", 10)
    o = P.offer(st, "solar", 2, "BBB")
    r = P.structures(scen, "solar", 10, o["offer_price"], 70.0)
    s = P.summarise_structures(r)
    assert s.loc["pay_as_produced", "spread P10-P90"] == 0
    assert s.loc["merchant", "spread P10-P90"] > s.loc["baseload", "spread P10-P90"] > 0
    assert np.isclose(r.swap, r.baseload - 1.5).all()


def test_curtailment_in_negative_hours():
    s = pd.DataFrame({"price_eur_mwh": [-10.0, 50.0], "solar_cf": [0.5, 0.5], "wind_cf": [0.1, 0.1], "scenario": 0})
    st = P.asset_stats([s], "solar", 1.0)
    assert np.isclose(st.capture_paid.iloc[0], 50.0) and np.isclose(st.curtailed_share.iloc[0], 0.5)
