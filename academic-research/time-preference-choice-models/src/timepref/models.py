"""Choice models fitted per participant by penalised maximum likelihood.

All models predict P(choose larger-later). The three discounting models put the options'
discounted values into a logistic choice rule with a sensitivity tau (per euro):

    exponential        V = x exp(-r t)                                  params: log r, log tau
    hyperbolic         V = x / (1 + k t)                                 params: log k, log tau
    quasi-hyperbolic   V = x if t = 0 else beta x exp(-r t)              params: beta, log r, log tau

ITCH (intertemporal choice heuristic, Ericson et al. 2015) skips discounting and compares the
attributes directly:

    logit P = b0 + b1 (xL - xS) + b2 (xL - xS)/x* + b3 (tL - tS) + b4 (tL - tS)/t*
    with x* and t* the averages of the two amounts and the two delays.

Weak normal penalties on the parameters (equivalent to MAP with wide priors) keep the fit finite
for people who always choose one side; without them tau runs off to infinity.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import minimize

EPS = 1e-6
MODELS = ("exponential", "hyperbolic", "quasi_hyperbolic", "itch")
N_PARAMS = {"exponential": 2, "hyperbolic": 2, "quasi_hyperbolic": 3, "itch": 5}


def _arrays(d: pd.DataFrame):
    return tuple(d[c].values.astype(float) for c in ("ss_amount", "ss_delay", "ll_amount", "ll_delay"))


def itch_features(d: pd.DataFrame) -> np.ndarray:
    xs, ts, xl, tl = _arrays(d)
    xstar, tstar = (xl + xs) / 2, (tl + ts) / 2
    return np.column_stack([np.ones(len(d)), (xl - xs) / 10, (xl - xs) / xstar, (tl - ts) / 30, (tl - ts) / tstar])


def predict(model: str, theta: np.ndarray, d: pd.DataFrame) -> np.ndarray:
    if model == "itch":
        z = itch_features(d) @ theta
        return 1 / (1 + np.exp(-np.clip(z, -35, 35)))
    xs, ts, xl, tl = _arrays(d)
    if model == "exponential":
        r, tau = np.exp(theta[0]), np.exp(theta[1])
        vs, vl = xs * np.exp(-r * ts), xl * np.exp(-r * tl)
    elif model == "hyperbolic":
        k, tau = np.exp(theta[0]), np.exp(theta[1])
        vs, vl = xs / (1 + k * ts), xl / (1 + k * tl)
    else:
        beta, r, tau = theta[0], np.exp(theta[1]), np.exp(theta[2])
        vs = np.where(ts == 0, xs, beta * xs * np.exp(-r * ts))
        vl = beta * xl * np.exp(-r * tl)
    return 1 / (1 + np.exp(-np.clip(tau * (vl - vs), -35, 35)))


# prior means and sds (wide), in the parameterisation above
PRIOR = {
    "exponential": (np.array([np.log(0.005), np.log(0.3)]), np.array([2.5, 1.5])),
    "hyperbolic": (np.array([np.log(0.01), np.log(0.3)]), np.array([2.5, 1.5])),
    "quasi_hyperbolic": (np.array([0.9, np.log(0.003), np.log(0.3)]), np.array([0.25, 2.5, 1.5])),
    "itch": (np.zeros(5), np.full(5, 5.0)),
}
BOUNDS = {
    "exponential": [(-12, 1), (-8, 4)],
    "hyperbolic": [(-12, 2), (-8, 4)],
    "quasi_hyperbolic": [(0.2, 1.5), (-12, 1), (-8, 4)],
    "itch": [(-20, 20)] * 5,
}
STARTS = {
    "exponential": [[np.log(0.005), np.log(0.3)], [np.log(0.05), np.log(0.1)]],
    "hyperbolic": [[np.log(0.01), np.log(0.3)], [np.log(0.1), np.log(0.1)]],
    "quasi_hyperbolic": [[0.9, np.log(0.003), np.log(0.3)], [0.7, np.log(0.001), np.log(0.1)]],
    "itch": [np.zeros(5)],
}


@dataclass
class Fit:
    model: str
    theta: np.ndarray
    nll: float           # negative log-likelihood without the penalty
    n: int

    @property
    def bic(self) -> float:
        return 2 * self.nll + N_PARAMS[self.model] * np.log(self.n)


def _nll(model, theta, d, y):
    p = np.clip(predict(model, theta, d), EPS, 1 - EPS)
    return -np.sum(y * np.log(p) + (1 - y) * np.log(1 - p))


def fit(model: str, d: pd.DataFrame, y: np.ndarray, prior: tuple | None = None) -> Fit:
    """Penalised ML fit. Pass prior=(mean, sd) to shrink towards a population (empirical Bayes)."""
    mu, sd = prior if prior is not None else PRIOR[model]

    def obj(th):
        return _nll(model, th, d, y) + 0.5 * np.sum(((th - mu) / sd) ** 2)

    best = None
    starts = list(STARTS[model]) + ([mu] if prior is not None else [])
    for s in starts:
        r = minimize(obj, np.array(s, float), method="L-BFGS-B", bounds=BOUNDS[model])
        if best is None or r.fun < best.fun:
            best = r
    return Fit(model, best.x, float(_nll(model, best.x, d, y)), len(y))


def fit_all(trials: pd.DataFrame, models=MODELS) -> pd.DataFrame:
    """Fit every model to every participant's full data; one row per participant and model."""
    rows = []
    for pid, d in trials.groupby("pid", sort=False):
        y = d["choice_ll"].values
        for m in models:
            f = fit(m, d, y)
            rows.append({"pid": pid, "model": m, "nll": f.nll, "bic": f.bic, **{f"theta{i}": v for i, v in enumerate(f.theta)}})
    return pd.DataFrame(rows)


def best_model(fits: pd.DataFrame) -> pd.DataFrame:
    """Lowest BIC per participant, plus the BIC gap to the runner-up."""
    f = fits.sort_values(["pid", "bic"])
    top = f.groupby("pid").head(2)
    out = top.groupby("pid").agg(best=("model", "first"), bic_best=("bic", "first"), bic_second=("bic", "last")).reset_index()
    out["delta_bic"] = out["bic_second"] - out["bic_best"]
    return out


def population_prior(thetas: np.ndarray, floor: float = 0.15) -> tuple[np.ndarray, np.ndarray]:
    """Robust population mean and spread of per-person estimates, used as an empirical-Bayes prior."""
    med = np.median(thetas, axis=0)
    mad = 1.4826 * np.median(np.abs(thetas - med), axis=0)
    return med, np.maximum(mad, floor)
