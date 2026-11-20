import numpy as np
import pandas as pd

from timepref import evaluate as E, models as M, world


def test_fit_recovers_known_parameters():
    rng = np.random.default_rng(3)
    d = pd.concat([world.design(rng, 400)], ignore_index=True)
    true = {"type": "hyperbolic", "log_k": np.log(0.02), "tau": 0.4}
    d["frame"] = "delay"
    p = world.sigmoid(0.4 * (d["ll_amount"] / (1 + 0.02 * d["ll_delay"]) - d["ss_amount"] / (1 + 0.02 * d["ss_delay"])))
    y = (rng.random(len(d)) < p).astype(int)
    f = M.fit("hyperbolic", d, y)
    assert abs(f.theta[0] - true["log_k"]) < 0.35
    assert abs(np.exp(f.theta[1]) - 0.4) < 0.15


def test_penalty_keeps_one_sided_choosers_finite(small):
    d = small[small["pid"] == small["pid"].iloc[0]]
    f = M.fit("hyperbolic", d, np.ones(len(d)))
    assert np.isfinite(f.theta).all() and f.theta[1] < 4


def test_itch_is_best_for_most_itch_users(small, tables):
    fits = M.fit_all(small, models=("hyperbolic", "itch"))
    best = M.best_model(fits).merge(tables["truth"][["pid", "type"]], on="pid")
    itch = best[best["type"] == "itch"]
    assert (itch["best"] == "itch").mean() > 0.6


def test_shrinkage_prior():
    th = np.array([[0.0, 1.0], [0.2, 1.1], [10.0, 0.9], [0.1, 1.0]])
    mu, sd = M.population_prior(th)
    assert abs(mu[0] - 0.15) < 1e-9 and sd.min() >= 0.15          # median ignores the outlier


def test_completeness_definition():
    cv = pd.DataFrame({"pid": ["a"] * 4, "choice_ll": [1, 0, 1, 1], "p_base_rate": [0.75] * 4,
                       "p_oracle": [0.9, 0.1, 0.9, 0.9], "p_model": [0.8, 0.3, 0.8, 0.8]})
    b = E.scoreboard(cv).set_index("model")
    assert b.loc["base_rate", "completeness"] == 0 and b.loc["oracle", "completeness"] == 1
    assert 0 < b.loc["model", "completeness"] < 1


def test_cross_validation_runs_end_to_end(clean):
    pids = clean["pid"].drop_duplicates().iloc[:24]
    cv = E.cross_validate(clean[clean["pid"].isin(pids)])
    assert len(cv) == 24 * 60
    assert {"p_base_rate", "p_hyperbolic", "p_itch_eb", "p_ml_person", "p_hybrid", "p_oracle"} <= set(cv.columns)
    b = E.scoreboard(cv).set_index("model")
    assert b.loc["hyperbolic", "log_loss"] < b.loc["base_rate", "log_loss"]
