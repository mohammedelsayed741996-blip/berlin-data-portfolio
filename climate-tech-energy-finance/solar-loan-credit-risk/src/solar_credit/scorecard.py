"""Weight-of-evidence scorecard: the explainable champion PD model.

Each feature is cut into bins, every bin gets a weight of evidence (WoE), and
a logistic regression on the WoE values gives the probability of default.
The coefficients are then scaled into points so an underwriter can read a
decision line by line: which bin the customer fell into and what it cost.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from . import config
from .features import CATEGORICAL_FEATURES, NUMERIC_FEATURES

logger = logging.getLogger(__name__)

SMOOTHING = 0.5  # added to good and bad counts so empty bins stay finite


@dataclass
class FeatureBinning:
    """Bins, WoE values and information value for one feature."""

    feature: str
    is_categorical: bool
    edges: np.ndarray | None  # numeric cut points incl. -inf/+inf
    table: pd.DataFrame  # one row per bin: bin, n, bads, bad_rate, woe, iv

    @property
    def iv(self) -> float:
        return float(self.table["iv"].sum())

    def assign_bins(self, values: pd.Series) -> pd.Series:
        """Map raw values to bin labels."""
        if self.is_categorical:
            known = set(self.table["bin"])
            return values.astype(str).where(values.astype(str).isin(known), "OTHER")
        cats = pd.cut(values.astype(float), bins=self.edges, right=True, include_lowest=True)
        return cats.astype(str)

    def transform(self, values: pd.Series) -> pd.Series:
        """Replace raw values by their bin's WoE (unknown bins get WoE 0)."""
        mapping = dict(zip(self.table["bin"], self.table["woe"]))
        return self.assign_bins(values).map(mapping).fillna(0.0).astype(float)


def _woe_table(bins: pd.Series, y: pd.Series) -> pd.DataFrame:
    grp = pd.DataFrame({"bin": bins.to_numpy(), "y": y.to_numpy()}).groupby("bin", observed=True)["y"]
    tab = pd.DataFrame({"n": grp.size(), "bads": grp.sum()}).reset_index()
    tab["goods"] = tab["n"] - tab["bads"]
    total_good = tab["goods"].sum()
    total_bad = tab["bads"].sum()
    dist_good = (tab["goods"] + SMOOTHING) / (total_good + SMOOTHING * len(tab))
    dist_bad = (tab["bads"] + SMOOTHING) / (total_bad + SMOOTHING * len(tab))
    tab["bad_rate"] = tab["bads"] / tab["n"]
    tab["woe"] = np.log(dist_good / dist_bad)
    tab["iv"] = (dist_good - dist_bad) * tab["woe"]
    return tab[["bin", "n", "bads", "bad_rate", "woe", "iv"]]


def fit_binning(x: pd.Series, y: pd.Series, categorical: bool, n_bins: int = 5) -> FeatureBinning:
    """Quantile bins for numeric features, one bin per level for categoricals."""
    if categorical:
        bins = x.astype(str)
        return FeatureBinning(x.name, True, None, _woe_table(bins, y))
    qs = np.unique(np.quantile(x.astype(float), np.linspace(0, 1, n_bins + 1)[1:-1]))
    edges = np.concatenate([[-np.inf], qs, [np.inf]])
    binning = FeatureBinning(x.name, False, edges, pd.DataFrame())
    binning.table = _woe_table(binning.assign_bins(x), y)
    # Keep bins in numeric order for readable tables.
    order = {str(c): i for i, c in enumerate(pd.cut(pd.Series([0.0]), bins=edges).cat.categories)}
    binning.table = binning.table.assign(_o=binning.table["bin"].map(order)).sort_values("_o").drop(columns="_o")
    return binning


@dataclass
class Scorecard:
    """Fitted WoE logistic scorecard with points scaling and reason codes."""

    min_iv: float = 0.02
    binnings: dict[str, FeatureBinning] = field(default_factory=dict)
    selected: list[str] = field(default_factory=list)
    model: LogisticRegression | None = None

    @property
    def factor(self) -> float:
        return config.SCORE_PDO / np.log(2.0)

    @property
    def offset(self) -> float:
        return config.SCORE_BASE_POINTS - self.factor * np.log(config.SCORE_BASE_ODDS)

    def fit(self, X: pd.DataFrame, y: pd.Series) -> "Scorecard":
        """Bin every feature, keep those with IV >= ``min_iv``, fit the regression."""
        if y.nunique() != 2:
            raise ValueError("Target must contain both defaults and non-defaults")
        for col in NUMERIC_FEATURES + CATEGORICAL_FEATURES:
            if col in X:
                self.binnings[col] = fit_binning(X[col], y, col in CATEGORICAL_FEATURES)
        self.selected = [c for c, b in self.binnings.items() if b.iv >= self.min_iv]
        if not self.selected:
            raise ValueError("No feature reached the minimum information value")
        woe = self.woe_transform(X)
        self.model = LogisticRegression(C=1.0, max_iter=1_000)
        self.model.fit(woe, y)
        logger.info("Scorecard fitted on %d features: %s", len(self.selected), self.selected)
        return self

    def woe_transform(self, X: pd.DataFrame) -> pd.DataFrame:
        return pd.DataFrame({c: self.binnings[c].transform(X[c]) for c in self.selected}, index=X.index)

    def predict_pd(self, X: pd.DataFrame) -> np.ndarray:
        """12-month probability of default."""
        if self.model is None:
            raise RuntimeError("Scorecard is not fitted")
        return self.model.predict_proba(self.woe_transform(X))[:, 1]

    def iv_table(self) -> pd.DataFrame:
        rows = [(c, b.iv, c in self.selected) for c, b in self.binnings.items()]
        return (
            pd.DataFrame(rows, columns=["feature", "information_value", "selected"])
            .sort_values("information_value", ascending=False)
            .reset_index(drop=True)
        )

    def points_table(self) -> pd.DataFrame:
        """Points per bin. The base points are spread evenly across features."""
        if self.model is None:
            raise RuntimeError("Scorecard is not fitted")
        coefs = dict(zip(self.selected, self.model.coef_[0]))
        base = (self.offset - self.factor * self.model.intercept_[0]) / len(self.selected)
        frames = []
        for c in self.selected:
            t = self.binnings[c].table.copy()
            t.insert(0, "feature", c)
            t["points"] = np.round(base - self.factor * coefs[c] * t["woe"]).astype(int)
            frames.append(t)
        return pd.concat(frames, ignore_index=True)

    def score(self, X: pd.DataFrame) -> np.ndarray:
        """Total score: higher means safer."""
        pts = self.points_table()
        total = np.zeros(len(X))
        for c in self.selected:
            mapping = dict(zip(pts.loc[pts["feature"] == c, "bin"], pts.loc[pts["feature"] == c, "points"]))
            fallback = float(pts.loc[pts["feature"] == c, "points"].median())
            total += self.binnings[c].assign_bins(X[c]).map(mapping).fillna(fallback).to_numpy(dtype=float)
        return total

    def reason_codes(self, X: pd.DataFrame, top_n: int = 3) -> list[list[str]]:
        """For each applicant, the features where they lost the most points."""
        pts = self.points_table()
        best = pts.groupby("feature")["points"].max()
        out: list[list[str]] = []
        lost = {}
        for c in self.selected:
            sub = pts.loc[pts["feature"] == c]
            mapping = dict(zip(sub["bin"], sub["points"]))
            got = self.binnings[c].assign_bins(X[c]).map(mapping).fillna(sub["points"].median())
            lost[c] = best[c] - got.to_numpy(dtype=float)
        lost_df = pd.DataFrame(lost, index=X.index)
        for _, row in lost_df.iterrows():
            top = row[row > 0].sort_values(ascending=False).head(top_n)
            out.append([f"{feat} (-{int(v)} pts)" for feat, v in top.items()])
        return out
