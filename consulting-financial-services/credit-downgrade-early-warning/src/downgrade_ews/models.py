"""Second-stage models, out-of-time evaluation and the monthly alert list."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

from . import config as C
from .features import KEYWORDS

RATING = ["notch", "notches_above_hy", "outlook_negative", "outlook_positive", "months_since_downgrade"]
FINANCIAL = ["leverage", "coverage", "leverage_chg_1y", "coverage_chg_1y", "ret_3m", "ret_6m", "drawdown_12m"]
KEYWORD = list(KEYWORDS) + ["news_1m", "news_3m", "news_trend"]
NLP = ["p_mean_1m", "p_mean_3m", "p_max_3m", "high_1m", "high_3m", "high_trend"]

FEATURE_SETS = {
    "Outlook only": ["outlook_negative"],
    "Ratings + financials": RATING + FINANCIAL,
    "+ keyword rules": RATING + FINANCIAL + KEYWORD,
    "+ NLP news scores": RATING + FINANCIAL + KEYWORD + NLP,
}
FULL = "+ NLP news scores"


def train_end() -> str:
    return (pd.Period(C.TEST_START, freq="M") - C.HORIZON_MONTHS - 1).strftime("%Y-%m")


def split(panel: pd.DataFrame):
    """Train on as-of months up to 2025-03, test from 2025-07. The three months in between are left
    out so no training label looks into the test period."""
    p = panel[panel["labelled"] & (panel["notch"] < len(C.RATINGS) - 1)]
    p = p[p["month"] >= "2022-04"]                      # needs three months of history
    end = train_end()
    return p[p["month"] <= end].copy(), p[p["month"] >= C.TEST_START].copy(), end


def make_model(name: str):
    if name == "Outlook only":
        return LogisticRegression()
    return HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, max_leaf_nodes=15, min_samples_leaf=40,
                                          l2_regularization=1.0, random_state=C.SEED)


@dataclass
class Result:
    name: str
    model: object
    features: list
    scores: pd.Series


def fit_all(train: pd.DataFrame, test: pd.DataFrame) -> dict[str, Result]:
    out = {}
    for name, cols in FEATURE_SETS.items():
        m = make_model(name)
        X = train[cols]
        if name == "Outlook only":
            X = X.fillna(0)
        m.fit(X, train["y"])
        Xt = test[cols].fillna(0) if name == "Outlook only" else test[cols]
        out[name] = Result(name, m, cols, pd.Series(m.predict_proba(Xt)[:, 1], index=test.index))
    return out


def alerts(test: pd.DataFrame, scores: pd.Series, k: int = C.ALERT_THRESHOLD_TOP_K) -> pd.DataFrame:
    """The k highest-scoring issuers each month: the analyst's review list."""
    t = test.assign(score=scores)
    return t.sort_values(["month", "score"], ascending=[True, False]).groupby("month").head(k)


def event_metrics(test: pd.DataFrame, flagged: pd.DataFrame, actions: pd.DataFrame) -> dict:
    """Per downgrade in the test window: was the issuer flagged in the 3 months before, and how early?"""
    dg = actions[actions["action"] == "downgrade"]
    first, last = (pd.Period(C.TEST_START, freq="M") + 1), pd.Period(test["month"].max(), freq="M") + C.HORIZON_MONTHS
    dg = dg[(dg["month"].apply(lambda m: pd.Period(m, freq="M")) >= first)
            & (dg["month"].apply(lambda m: pd.Period(m, freq="M")) <= last)]
    fl = set(zip(flagged["issuer_id"], flagged["month"]))
    caught, leads = 0, []
    for d in dg.itertuples():
        pm = pd.Period(d.month, freq="M")
        prior = [(pm - k).strftime("%Y-%m") for k in range(1, C.HORIZON_MONTHS + 1)]
        hits = [k for k, m in enumerate(prior, start=1) if (d.issuer_id, m) in fl]
        if hits:
            caught += 1
            leads.append(max(hits))
    return {"downgrades": len(dg), "caught": caught, "event_recall": caught / len(dg) if len(dg) else np.nan,
            "median_lead_months": float(np.median(leads)) if leads else np.nan}


def evaluate(results: dict[str, Result], test: pd.DataFrame, actions: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for name, r in results.items():
        y, s = test["y"], r.scores
        if name == "Outlook only":
            flagged = test[test["outlook_negative"] == 1]
        else:
            flagged = alerts(test, s)
        hits = flagged["y"].sum()
        ev = event_metrics(test, flagged, actions)
        rows.append({"model": name, "roc_auc": roc_auc_score(y, s), "pr_auc": average_precision_score(y, s),
                     "brier": brier_score_loss(y, s), "alerts_per_month": len(flagged) / test["month"].nunique(),
                     "alert_precision": hits / len(flagged) if len(flagged) else np.nan,
                     **ev})
    return pd.DataFrame(rows).round(4)


def base_rate(test: pd.DataFrame) -> float:
    return float(test["y"].mean())
