"""Simulate an online money-earlier-or-later experiment.

Each participant answers 60 choices between a smaller-sooner (SS) and a larger-later (LL)
amount, plus 4 catch trials where the later option is smaller, so choosing it makes no sense.
Half see delays ("in 30 days"), half see calendar dates ("on 21 December").

People differ in how they decide. The simulation keeps four kinds, so the models can be
checked against a known truth:

    hyperbolic         V = x / (1 + k t)
    quasi-hyperbolic   V = x if t = 0 else beta * x * exp(-r t)
    exponential        V = x * exp(-r t)
    itch               a heuristic that compares money and time in absolute and relative terms
                       (Ericson et al. 2015), with no discount function at all

Discounting types show a magnitude effect: k (or r) is lower for larger amounts.
Choices are noisy (logistic in the value difference) and 2% of trials are random lapses.

Nothing here describes a real person. Participant ids are random codes.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as C


def sigmoid(z):
    return 1.0 / (1.0 + np.exp(-np.clip(z, -35, 35)))


# ---------------------------------------------------------------- design
def design(rng: np.random.Generator, n: int = C.N_TRIALS) -> pd.DataFrame:
    ss_amt = rng.integers(C.SS_AMOUNT[0], C.SS_AMOUNT[1] + 1, n).astype(float)
    ratio = rng.uniform(*C.LL_RATIO, n) ** 1.0
    ll_amt = np.round(ss_amt * ratio)
    ll_amt = np.maximum(ll_amt, ss_amt + 1)
    ss_t = rng.choice(C.SS_DELAYS, n).astype(float)
    ll_t = ss_t + rng.choice(C.INTERVALS, n)
    return pd.DataFrame({"ss_amount": ss_amt, "ss_delay": ss_t, "ll_amount": ll_amt, "ll_delay": ll_t, "catch": False})


def catch_trials(rng: np.random.Generator, n: int = C.N_CATCH) -> pd.DataFrame:
    """The later option is smaller: anyone reading the question picks the sooner one."""
    ss_amt = rng.integers(30, 81, n).astype(float)
    ll_amt = ss_amt - rng.integers(5, 16, n)
    ss_t = np.zeros(n)
    ll_t = rng.choice((30, 60, 90), n).astype(float)
    return pd.DataFrame({"ss_amount": ss_amt, "ss_delay": ss_t, "ll_amount": ll_amt, "ll_delay": ll_t, "catch": True})


# ---------------------------------------------------------------- people
def draw_person(rng: np.random.Generator, kind: str, condition: str) -> dict:
    date = condition == "date"
    p = {"type": kind, "condition": condition, "tau": float(np.exp(rng.normal(np.log(0.35), 0.35)))}
    if kind == "hyperbolic":
        p["log_k"] = float(rng.normal(np.log(0.012), 1.0) + (C.DATE_FRAME_LOGK_SHIFT if date else 0.0))
    elif kind == "exponential":
        p["log_r"] = float(rng.normal(np.log(0.005), 0.8) + (C.DATE_FRAME_LOGK_SHIFT if date else 0.0))
    elif kind == "quasi_hyperbolic":
        p["beta"] = float(np.clip(rng.normal(0.84 + (C.DATE_FRAME_BETA_SHIFT if date else 0.0), 0.07), 0.55, 1.0))
        p["log_r"] = float(rng.normal(np.log(0.002), 0.7) + (C.DATE_FRAME_LOGK_SHIFT if date else 0.0))
    elif kind == "itch":
        p.update({"b0": rng.normal(0.0, 0.5), "bxa": rng.normal(0.06, 0.02), "bxr": rng.normal(4.0, 1.2),
                  "bta": rng.normal(-0.012, 0.005), "btr": rng.normal(-2.2, 0.7) * (C.DATE_FRAME_ITCH_TR if date else 1.0)})
    return p


def magnitude(x):
    return (np.asarray(x) / 40.0) ** C.MAGNITUDE_EXPONENT


def p_later(p: dict, d: pd.DataFrame) -> np.ndarray:
    """True probability of choosing the larger-later option, before lapses."""
    xs, ts, xl, tl = (d[c].values for c in ("ss_amount", "ss_delay", "ll_amount", "ll_delay"))
    kind = p["type"]
    if kind == "itch":
        xstar, tstar = (xl + xs) / 2, (tl + ts) / 2
        z = (p["b0"] + p["bxa"] * (xl - xs) + p["bxr"] * (xl - xs) / xstar
             + p["bta"] * (tl - ts) + p["btr"] * (tl - ts) / tstar)
        return sigmoid(z)
    m = magnitude(xl)
    if kind == "hyperbolic":
        k = np.exp(p["log_k"]) * m
        vs, vl = xs / (1 + k * ts), xl / (1 + k * tl)
    elif kind == "exponential":
        r = np.exp(p["log_r"]) * m
        vs, vl = xs * np.exp(-r * ts), xl * np.exp(-r * tl)
    else:
        r = np.exp(p["log_r"]) * m
        vs = np.where(ts == 0, xs, p["beta"] * xs * np.exp(-r * ts))
        vl = p["beta"] * xl * np.exp(-r * tl)
    return sigmoid(p["tau"] * (vl - vs))


# ---------------------------------------------------------------- simulation
def _pid(rng, used: set) -> str:
    while True:
        code = "P" + "".join(rng.choice(list("ABCDEFGHJKLMNPQRSTUVWXYZ23456789"), 6))
        if code not in used:
            used.add(code)
            return code


def _rt(rng, d: pd.DataFrame, choice, fast=False) -> np.ndarray:
    if fast:
        return np.round(np.exp(rng.normal(np.log(330), 0.25, len(d))))
    # harder choices take longer: closeness of the two options
    gap = np.abs(np.log(d["ll_amount"] / d["ss_amount"]) - 0.4)
    return np.round(np.exp(rng.normal(np.log(1900) - 0.6 * gap, 0.35)))


def simulate(seed: int = C.SEED) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    used: set = set()
    people, trials, truth = [], [], []
    start = pd.Timestamp("2026-10-05 09:00")
    kinds = list(C.TYPE_SHARES)
    shares = np.array(list(C.TYPE_SHARES.values()))

    def run(pid, kind, cond, when, params=None, careless=None):
        d = pd.concat([design(rng), catch_trials(rng)], ignore_index=True)
        d = d.sample(frac=1, random_state=int(rng.integers(1e9))).reset_index(drop=True)
        if careless == "random":
            p = np.full(len(d), 0.5)
        elif careless == "straight":
            p = np.full(len(d), 0.995)
        else:
            p = p_later(params, d)
            p = (1 - C.LAPSE) * p + C.LAPSE * 0.5
        choice = (rng.random(len(d)) < p).astype(int)
        d.insert(0, "trial", np.arange(1, len(d) + 1))
        d.insert(0, "pid", pid)
        d["frame"] = cond
        d["choice_ll"] = choice
        d["rt_ms"] = _rt(rng, d, choice, fast=careless is not None).astype(int)
        d["p_true"] = p
        trials.append(d)
        people.append({"pid": pid, "condition": cond, "submitted_at": when,
                       "device": rng.choice(["desktop", "mobile"], p=[0.6, 0.4]),
                       "duration_min": round(float(d["rt_ms"].sum() / 60000 + rng.uniform(1.5, 4)), 1)})

    for i in range(C.N_PARTICIPANTS):
        pid = _pid(rng, used)
        cond = C.CONDITIONS[i % 2]
        kind = kinds[int(rng.choice(len(kinds), p=shares))]
        params = draw_person(rng, kind, cond)
        when = start + pd.Timedelta(minutes=int(rng.integers(0, 60 * 24 * 21)))
        run(pid, kind, cond, when, params)
        truth.append({"pid": pid, "careless": "no", **params})
    for kind, n in (("random", C.PLANTED["random_clickers"]), ("straight", C.PLANTED["straightliners"])):
        for _ in range(n):
            pid = _pid(rng, used)
            cond = C.CONDITIONS[int(rng.integers(2))]
            when = start + pd.Timedelta(minutes=int(rng.integers(0, 60 * 24 * 21)))
            run(pid, kind, cond, when, careless=kind)
            truth.append({"pid": pid, "careless": kind, "type": "careless", "condition": cond})
    # duplicate submissions: the same code comes back days later and answers a fresh set of trials
    genuine = [t for t in truth if t["careless"] == "no"]
    for t in rng.choice(genuine, C.PLANTED["duplicate_submissions"], replace=False):
        first = next(p for p in people if p["pid"] == t["pid"])
        params = {k: v for k, v in t.items() if k not in ("pid", "careless")}
        run(t["pid"], params["type"], t["condition"], first["submitted_at"] + pd.Timedelta(days=int(rng.integers(1, 6))), params)
    participants = pd.DataFrame(people)
    participants["submission"] = participants.groupby("pid").cumcount() + 1
    tr = pd.concat(trials, ignore_index=True)
    tr["submission"] = tr.groupby(["pid", "trial"]).cumcount() + 1
    return {"participants": participants.sort_values("submitted_at").reset_index(drop=True),
            "trials": tr, "truth": pd.DataFrame(truth)}
