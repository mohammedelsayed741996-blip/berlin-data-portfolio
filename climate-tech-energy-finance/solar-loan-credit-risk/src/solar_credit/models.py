"""Challenger model and the validation metrics used for both models."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import brier_score_loss, roc_auc_score, roc_curve

from .features import CATEGORICAL_FEATURES, FEATURES


@dataclass
class GradientBoostingPD:
    """Gradient-boosted trees on raw features, kept as a challenger."""

    model: HistGradientBoostingClassifier | None = None
    categories: dict[str, list[str]] | None = None

    def _encode(self, X: pd.DataFrame) -> pd.DataFrame:
        enc = X[FEATURES].copy()
        for c in CATEGORICAL_FEATURES:
            lookup = {v: i for i, v in enumerate(self.categories[c])}
            enc[c] = enc[c].astype(str).map(lookup).fillna(-1).astype(int)
        return enc

    def fit(self, X: pd.DataFrame, y: pd.Series) -> "GradientBoostingPD":
        self.categories = {c: sorted(X[c].astype(str).unique()) for c in CATEGORICAL_FEATURES}
        cat_mask = [c in CATEGORICAL_FEATURES for c in FEATURES]
        self.model = HistGradientBoostingClassifier(
            max_depth=3,
            learning_rate=0.05,
            max_iter=250,
            min_samples_leaf=60,
            l2_regularization=1.0,
            categorical_features=cat_mask,
            random_state=7,
        )
        self.model.fit(self._encode(X), y)
        return self

    def predict_pd(self, X: pd.DataFrame) -> np.ndarray:
        if self.model is None:
            raise RuntimeError("Model is not fitted")
        return self.model.predict_proba(self._encode(X))[:, 1]


def ks_statistic(y: np.ndarray, pd_hat: np.ndarray) -> float:
    """Maximum gap between the cumulative bad and good distributions."""
    fpr, tpr, _ = roc_curve(y, pd_hat)
    return float(np.max(tpr - fpr))


def evaluate(y: pd.Series, pd_hat: np.ndarray, name: str) -> dict[str, float | str]:
    """AUC, Gini, KS, Brier score and predicted vs observed default rate."""
    y_arr = np.asarray(y)
    auc = roc_auc_score(y_arr, pd_hat)
    return {
        "model": name,
        "auc": round(float(auc), 4),
        "gini": round(float(2 * auc - 1), 4),
        "ks": round(ks_statistic(y_arr, pd_hat), 4),
        "brier": round(float(brier_score_loss(y_arr, pd_hat)), 5),
        "predicted_dr": round(float(np.mean(pd_hat)), 4),
        "observed_dr": round(float(np.mean(y_arr)), 4),
    }


def calibration_table(y: pd.Series, pd_hat: np.ndarray, n_groups: int = 10) -> pd.DataFrame:
    """Observed vs predicted default rate by risk decile (1 = riskiest)."""
    df = pd.DataFrame({"y": np.asarray(y), "pd": pd_hat})
    df["decile"] = pd.qcut(df["pd"].rank(method="first", ascending=False), n_groups, labels=False) + 1
    out = df.groupby("decile").agg(loans=("y", "size"), defaults=("y", "sum"),
                                   predicted_pd=("pd", "mean"), observed_dr=("y", "mean"))
    return out.round(4).reset_index()


def binomial_test_by_grade(y: pd.Series, pd_hat: np.ndarray, n_groups: int = 5) -> pd.DataFrame:
    """One-sided binomial check per grade: are defaults higher than predicted?

    Uses the normal approximation, which is fine at these group sizes.
    """
    from scipy.stats import norm

    tab = calibration_table(y, pd_hat, n_groups)
    se = np.sqrt(tab["predicted_pd"] * (1 - tab["predicted_pd"]) / tab["loans"])
    tab["z"] = (tab["observed_dr"] - tab["predicted_pd"]) / se
    tab["p_value"] = 1 - norm.cdf(tab["z"])
    tab["flag"] = np.where(tab["p_value"] < 0.05, "Underestimated", "OK")
    return tab.rename(columns={"decile": "grade"}).round(4)
