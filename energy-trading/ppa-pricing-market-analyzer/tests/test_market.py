import numpy as np

from ppalab import market as M, trends as T


def test_simulation_is_deterministic():
    a, _ = M.simulate()
    b, _ = M.simulate()
    assert a.price_eur_mwh.equals(b.price_eur_mwh)


def test_history_has_the_stylised_facts(hourly):
    y = T.yearly(hourly).set_index("year")
    assert y.base.idxmax() == 2022                                       # the crisis year
    assert y.negative_hours[2025] > 5 * y.negative_hours[2020]          # negative prices become common
    assert y.solar_capture_rate[2025] < y.solar_capture_rate[2019] - 0.2  # solar cannibalisation
    assert (y.wind_capture_rate < 1).all() and (y.solar_capture_rate < 1).all()
    assert hourly.solar_gw[hourly.timestamp.dt.hour.isin([0, 1, 2, 23])].max() == 0


def test_capture_price_definition():
    import pandas as pd
    df = pd.DataFrame({"price_eur_mwh": [10.0, 100.0], "solar_gw": [3.0, 1.0]})
    assert T.capture(df, "solar_gw") == (30 + 100) / 4


def test_forward_curve_and_volatility(data):
    c = data["curve"]
    assert (c.base_eur_mwh.diff().dropna() < 0).all()
    v = T.forward_volatility(data["cal27"])
    assert 0.2 < v.annualised_vol.median() < 0.4
    assert np.isclose(data["cal27"].cal27_base_eur_mwh.iloc[-1], c.base_eur_mwh.iloc[0])
