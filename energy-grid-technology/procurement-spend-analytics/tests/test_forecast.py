import numpy as np

from spendcube import forecast as F
from spendcube.config import CATEGORIES


def test_models_return_h_steps():
    y = np.log(np.linspace(100, 200, 60))
    for name, f in F.MODELS.items():
        out = f(y, 6)
        assert out.shape == (6,) and np.isfinite(out).all(), name


def test_drift_extrapolates_a_straight_line():
    y = np.arange(50, dtype=float)
    assert np.allclose(F.f_drift(y, 3), [50, 51, 52])


def test_backtest_has_no_lookahead(indices):
    bt = F.backtest(indices)
    one = bt[(bt.model == "naive") & (bt.h == 1)].iloc[0]
    month = indices.set_index("month")
    assert np.isclose(one.forecast, month.loc[one.origin, one["index"]])


def test_bands_are_calibrated(indices):
    bt = F.backtest(indices)
    cov = F.coverage(bt, indices, {k: "naive" for k in indices.columns if k != "month"})
    assert 0.7 <= cov <= 0.9


def test_pass_through_recovers_contract_formula(model, indices):
    tables, _, _ = model
    pt = F.pass_through(tables["fact_po_line"], indices).set_index("category")
    for cat, row in pt.iterrows():
        assert row.lag_months == CATEGORIES[cat]["lag"]
        assert abs(row.pass_through - CATEGORIES[cat]["weight"]) < 0.06
