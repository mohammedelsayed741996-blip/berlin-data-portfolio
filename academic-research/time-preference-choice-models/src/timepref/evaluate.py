"""Out-of-sample comparison of discounting models, a heuristic and machine learning.

Every participant's 60 trials are split into 4 folds. Each model is trained without the
held-out fold and predicts it, so every trial gets exactly one out-of-sample prediction.

Contenders
    base rate         the participant's share of later choices in the training folds (naive baseline)
    exponential, hyperbolic, quasi_hyperbolic, itch    fitted per participant
    hyperbolic_eb, itch_eb    the same, shrunk towards the population (empirical Bayes): each person's
                      estimate borrows strength from everyone else, as ML does by pooling
    ml_pooled         gradient boosting on trial features and frame, one model for everyone
    ml_person         the same plus person features from the training folds (base rate, fitted log k and tau)
    hybrid            the same plus the per-person hyperbolic and ITCH predictions as features. On training
                      rows these come from an inner 3-fold split, so the booster never sees in-sample fits
    oracle            the true choice probability, known only because the data are simulated

Completeness (Fudenberg et al. 2022) is the share of the predictable variation a model captures:
    (loss of base rate - loss of model) / (loss of base rate - loss of the best possible prediction)
With real data the best possible prediction is unknown and a strong ML model stands in for it. Here
the oracle gives the true ceiling, so the ML stand-in can itself be checked.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier

from . import config as C
from . import models as M

EPS = 1e-6


def assign_folds(trials: pd.DataFrame, k: int = C.CV_FOLDS, seed: int = C.SEED) -> pd.Series:
    rng = np.random.default_rng(seed)
    out = pd.Series(0, index=trials.index)
    for _, idx in trials.groupby("pid").groups.items():
        perm = rng.permutation(len(idx))
        out.loc[idx] = perm % k
    return out


def trial_features(d: pd.DataFrame) -> pd.DataFrame:
    xs, ts, xl, tl = (d[c].astype(float) for c in ("ss_amount", "ss_delay", "ll_amount", "ll_delay"))
    return pd.DataFrame({
        "ss_amount": xs, "ll_amount": xl, "ss_delay": ts, "ll_delay": tl,
        "x_diff": xl - xs, "x_ratio": xl / xs, "t_diff": tl - ts, "t_rel": (tl - ts) / ((tl + ts) / 2),
        "immediate": (ts == 0).astype(float), "implied_daily_rate": np.log(xl / xs) / (tl - ts),
        "date_frame": (d["frame"] == "date").astype(float),
    }, index=d.index)


def log_loss(y, p) -> float:
    p = np.clip(p, EPS, 1 - EPS)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def _inner_oof(model: str, d: pd.DataFrame, k: int = 3) -> np.ndarray:
    """Out-of-fold predictions inside one participant's training trials."""
    y = d["choice_ll"].values
    out = np.zeros(len(d))
    folds = np.arange(len(d)) % k
    for f in range(k):
        m = folds != f
        out[~m] = M.predict(model, M.fit(model, d.iloc[m], y[m]).theta, d.iloc[~m])
    return out


def _person_fold(d: pd.DataFrame, tr: np.ndarray, models) -> dict:
    """All per-participant work for one fold: fits, out-of-sample predictions, inner out-of-fold predictions."""
    dtr, dte = d[tr], d[~tr]
    ytr = dtr["choice_ll"].values
    out = {"base": (ytr.sum() + 0.5) / (len(ytr) + 1), "pred": {}, "theta": {}, "oof": {}}
    for m in models:
        fit = M.fit(m, dtr, ytr)
        out["pred"][m] = M.predict(m, fit.theta, dte)
        out["theta"][m] = fit.theta
    for m in ("hyperbolic", "itch"):
        out["oof"][m] = _inner_oof(m, dtr)
    return out


def _person_eb(d: pd.DataFrame, tr: np.ndarray, priors: dict) -> dict:
    dtr, dte = d[tr], d[~tr]
    return {m: M.predict(m, M.fit(m, dtr, dtr["choice_ll"].values, prior=pr).theta, dte) for m, pr in priors.items()}


def cross_validate(trials: pd.DataFrame, models=M.MODELS, seed: int = C.SEED, n_jobs: int = -1) -> pd.DataFrame:
    """One out-of-sample prediction per trial and contender."""
    from joblib import Parallel, delayed

    t = trials.reset_index(drop=True).copy()
    t["fold"] = assign_folds(t, seed=seed)
    X = trial_features(t)
    eb = ("hyperbolic", "itch")
    names = ("base_rate", *models, *(f"{m}_eb" for m in eb), "ml_pooled", "ml_person", "hybrid")
    preds = {m: np.zeros(len(t)) for m in names}
    groups = list(t.groupby("pid").indices.items())
    y = t["choice_ll"].values
    pool = Parallel(n_jobs=n_jobs, batch_size=8)
    for f in range(C.CV_FOLDS):
        tr_mask = (t["fold"] != f).values
        te_mask = ~tr_mask
        res = pool(delayed(_person_fold)(t.iloc[idx], tr_mask[idx], models) for _, idx in groups)
        P = np.zeros((len(t), 3))
        oof = {m: np.zeros(len(t)) for m in eb}
        for (pid, idx), r in zip(groups, res):
            tr_idx, te_idx = idx[tr_mask[idx]], idx[te_mask[idx]]
            preds["base_rate"][te_idx] = r["base"]
            for m in models:
                preds[m][te_idx] = r["pred"][m]
            for m in eb:
                oof[m][tr_idx] = r["oof"][m]
            P[idx] = (r["base"], r["theta"]["hyperbolic"][0], r["theta"]["hyperbolic"][1])
        # empirical Bayes: refit everyone with the population as prior
        priors = {m: M.population_prior(np.array([r["theta"][m] for r in res])) for m in eb}
        res_eb = pool(delayed(_person_eb)(t.iloc[idx], tr_mask[idx], priors) for _, idx in groups)
        for (pid, idx), r in zip(groups, res_eb):
            te_idx = idx[te_mask[idx]]
            for m in eb:
                preds[f"{m}_eb"][te_idx] = r[m]
        Xp = X.assign(base_rate=P[:, 0], hyp_log_k=P[:, 1], hyp_log_tau=P[:, 2])
        Xh = Xp.assign(p_hyperbolic=np.where(tr_mask, oof["hyperbolic"], preds["hyperbolic"]),
                       p_itch=np.where(tr_mask, oof["itch"], preds["itch"]))
        for name, XX in (("ml_pooled", X), ("ml_person", Xp), ("hybrid", Xh)):
            gb = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, max_leaf_nodes=15,
                                                min_samples_leaf=40, l2_regularization=1.0, random_state=seed)
            gb.fit(XX[tr_mask], y[tr_mask])
            preds[name][te_mask] = gb.predict_proba(XX[te_mask])[:, 1]
    out = t[["pid", "trial", "frame", "choice_ll", "p_true", "fold"]].copy()
    for name, p in preds.items():
        out[f"p_{name}"] = p
    out["p_oracle"] = t["p_true"].values
    return out


def scoreboard(cv: pd.DataFrame) -> pd.DataFrame:
    y = cv["choice_ll"].values
    names = [c[2:] for c in cv.columns if c.startswith("p_") and c != "p_true"]
    loss = {n: log_loss(y, cv[f"p_{n}"].values) for n in names}
    naive, best = loss["base_rate"], loss["oracle"]
    rows = []
    for n in names:
        p = cv[f"p_{n}"].values
        rows.append({"model": n, "log_loss": loss[n], "accuracy": float(np.mean((p > 0.5) == y)),
                     "completeness": (naive - loss[n]) / (naive - best)})
    return pd.DataFrame(rows).sort_values("log_loss").reset_index(drop=True)


def by_type(cv: pd.DataFrame, truth: pd.DataFrame, names=("exponential", "hyperbolic", "quasi_hyperbolic", "itch", "itch_eb", "ml_person")) -> pd.DataFrame:
    d = cv.merge(truth[["pid", "type"]], on="pid")
    rows = []
    for ty, g in d.groupby("type"):
        y = g["choice_ll"].values
        naive, best = log_loss(y, g["p_base_rate"]), log_loss(y, g["p_oracle"])
        for n in names:
            rows.append({"true_type": ty, "model": n, "completeness": (naive - log_loss(y, g[f"p_{n}"])) / (naive - best)})
    return pd.DataFrame(rows).pivot(index="true_type", columns="model", values="completeness")


def bootstrap_ci(cv: pd.DataFrame, a: str, b: str, n: int = C.BOOT, seed: int = C.SEED) -> tuple[float, float, float]:
    """Difference in log loss (a minus b), resampling participants."""
    rng = np.random.default_rng(seed)
    y = cv["choice_ll"].values

    def per_trial(n_):
        p = np.clip(cv[f"p_{n_}"].values, EPS, 1 - EPS)
        return -(y * np.log(p) + (1 - y) * np.log(1 - p))
    diff = pd.Series(per_trial(a) - per_trial(b)).groupby(cv["pid"].values).mean()
    vals = diff.values
    boots = rng.choice(vals, (n, len(vals))).mean(axis=1)
    return float(vals.mean()), float(np.quantile(boots, 0.025)), float(np.quantile(boots, 0.975))
