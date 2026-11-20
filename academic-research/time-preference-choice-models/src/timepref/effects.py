"""Can time preferences be shaped? The framing treatment, the magnitude effect and present bias.

Framing (between subjects): half the participants saw delays ("in 30 days"), half calendar
dates ("on 21 December"). The outcome is each person's fitted hyperbolic log k, plus a
model-free outcome, the share of later choices. Inference uses a permutation test and a
bootstrap over participants, so no distributional assumption is needed.

Magnitude effect (within subjects): k is fitted separately on each person's trials with
smaller and larger later amounts (median split), and the paired difference is tested.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as C
from . import models as M


def person_table(trials: pd.DataFrame, fits: pd.DataFrame) -> pd.DataFrame:
    hyp = fits[fits["model"] == "hyperbolic"].set_index("pid")
    qh = fits[fits["model"] == "quasi_hyperbolic"].set_index("pid")
    g = trials.groupby("pid").agg(frame=("frame", "first"), share_later=("choice_ll", "mean"))
    g["log_k"] = hyp["theta0"]
    g["beta"] = qh["theta0"]
    return g.reset_index()


def _perm_and_boot(a: np.ndarray, b: np.ndarray, rng, n=C.BOOT):
    diff = a.mean() - b.mean()
    pooled = np.concatenate([a, b])
    perm = np.array([np.subtract(*(lambda s: (s[:len(a)].mean(), s[len(a):].mean()))(rng.permutation(pooled))) for _ in range(n)])
    p = float((np.abs(perm) >= abs(diff)).mean())
    boot = np.array([rng.choice(a, len(a)).mean() - rng.choice(b, len(b)).mean() for _ in range(n)])
    pooled_sd = np.sqrt(((len(a) - 1) * a.var(ddof=1) + (len(b) - 1) * b.var(ddof=1)) / (len(a) + len(b) - 2))
    return {"diff": float(diff), "ci_low": float(np.quantile(boot, 0.025)), "ci_high": float(np.quantile(boot, 0.975)),
            "p_perm": p, "cohens_d": float(diff / pooled_sd), "n_date": len(a), "n_delay": len(b)}


def framing_effect(people: pd.DataFrame, seed: int = C.SEED) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for outcome in ("log_k", "share_later", "beta"):
        a = people.loc[people["frame"] == "date", outcome].values
        b = people.loc[people["frame"] == "delay", outcome].values
        rows.append({"outcome": outcome, **_perm_and_boot(a, b, rng)})
    return pd.DataFrame(rows)


def magnitude_effect(trials: pd.DataFrame, seed: int = C.SEED) -> dict:
    """Paired difference in hyperbolic log k between larger and smaller later amounts."""
    rng = np.random.default_rng(seed)
    cut = trials["ll_amount"].median()
    rows = []
    for pid, d in trials.groupby("pid"):
        small, large = d[d["ll_amount"] < cut], d[d["ll_amount"] >= cut]
        ks = M.fit("hyperbolic", small, small["choice_ll"].values).theta[0]
        kl = M.fit("hyperbolic", large, large["choice_ll"].values).theta[0]
        rows.append({"pid": pid, "log_k_small": ks, "log_k_large": kl})
    d = pd.DataFrame(rows)
    diff = (d["log_k_large"] - d["log_k_small"]).values
    boot = np.array([rng.choice(diff, len(diff)).mean() for _ in range(C.BOOT)])
    signs = rng.choice([-1, 1], (C.BOOT, len(diff)))
    p = float((np.abs((signs * diff).mean(axis=1)) >= abs(diff.mean())).mean())
    return {"cut_eur": float(cut), "mean_diff_log_k": float(diff.mean()), "median_diff_log_k": float(np.median(diff)),
            "ci_low": float(np.quantile(boot, 0.025)), "ci_high": float(np.quantile(boot, 0.975)), "p_signflip": p,
            "share_lower_k_for_large": float((diff < 0).mean()), "n": len(diff), "table": d}


def with_careless(trials_all_first: pd.DataFrame, fits_fn, excluded: list, seed: int = C.SEED) -> pd.DataFrame:
    """Robustness: the framing effect on the share of later choices with and without exclusions."""
    rng = np.random.default_rng(seed)
    rows = []
    real = trials_all_first[~trials_all_first["catch"]]
    for label, d in (("after exclusions", real[~real["pid"].isin(excluded)]), ("no exclusions", real)):
        g = d.groupby("pid").agg(frame=("frame", "first"), share_later=("choice_ll", "mean"))
        a = g.loc[g["frame"] == "date", "share_later"].values
        b = g.loc[g["frame"] == "delay", "share_later"].values
        rows.append({"sample": label, **_perm_and_boot(a, b, rng, n=1000)})
    return pd.DataFrame(rows)
