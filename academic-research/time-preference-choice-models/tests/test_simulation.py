import numpy as np
import pandas as pd

from timepref import config as C, world


def test_design_is_valid():
    d = world.design(np.random.default_rng(0), 500)
    assert (d["ll_amount"] > d["ss_amount"]).all()
    assert (d["ll_delay"] > d["ss_delay"]).all()
    c = world.catch_trials(np.random.default_rng(0), 50)
    assert (c["ll_amount"] < c["ss_amount"]).all()           # catch trials: later option is smaller


def test_counts(tables):
    tr, ppl = tables["trials"], tables["participants"]
    n = C.N_PARTICIPANTS + C.PLANTED["random_clickers"] + C.PLANTED["straightliners"]
    assert ppl["pid"].nunique() == n
    assert len(ppl) == n + C.PLANTED["duplicate_submissions"]
    assert (tr.groupby(["pid", "submission"]).size() == C.N_TRIALS + C.N_CATCH).all()


def test_no_personal_data(tables):
    cols = set(tables["participants"].columns) | set(tables["trials"].columns)
    assert not cols & {"name", "email", "age", "birth_date", "gender", "ip_address", "postcode"}
    assert tables["participants"]["pid"].str.fullmatch(r"P[A-Z2-9]{6}").all()


def test_hyperbolic_value_falls_with_delay_and_rises_with_amount():
    p = {"type": "hyperbolic", "log_k": np.log(0.01), "tau": 0.5}
    base = pd.DataFrame({"ss_amount": [20.0], "ss_delay": [0.0], "ll_amount": [30.0], "ll_delay": [30.0]})
    later = base.assign(ll_delay=180.0)
    bigger = base.assign(ll_amount=40.0)
    assert world.p_later(p, later)[0] < world.p_later(p, base)[0] < world.p_later(p, bigger)[0]


def test_date_frame_makes_people_more_patient_in_truth(tables):
    t = tables["truth"]
    h = t[t["type"] == "hyperbolic"]
    assert h.loc[h["condition"] == "date", "log_k"].mean() < h.loc[h["condition"] == "delay", "log_k"].mean()
