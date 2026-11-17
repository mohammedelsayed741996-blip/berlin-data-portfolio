"""Credit decision engine for new applications.

Order of checks: hard policy rules first (they cannot be overridden by a good
score), then the scorecard cut-off. Every decision carries the reasons an
underwriter would put in the file.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import config
from .scorecard import Scorecard


@dataclass
class Decision:
    """Outcome for a single application."""

    application_id: str
    decision: str  # "Approve", "Refer" or "Decline"
    score: int
    pd_12m: float
    reasons: list[str] = field(default_factory=list)


def strategy_table(y: pd.Series, scores: np.ndarray, cutoffs: list[int] | None = None) -> pd.DataFrame:
    """Approval rate and bad rate of the approved book at each score cut-off."""
    if cutoffs is None:
        cutoffs = list(range(480, 661, 20))
    y_arr = np.asarray(y)
    rows = []
    for c in cutoffs:
        approved = scores >= c
        rows.append(
            {
                "cutoff": c,
                "approval_rate": round(float(approved.mean()), 4),
                "approved_bad_rate": round(float(y_arr[approved].mean()) if approved.any() else np.nan, 4),
                "declined_bad_rate": round(float(y_arr[~approved].mean()) if (~approved).any() else np.nan, 4),
                "bads_avoided_share": round(float(y_arr[~approved].sum() / max(y_arr.sum(), 1)), 4),
            }
        )
    return pd.DataFrame(rows)


def choose_cutoff(strategy: pd.DataFrame, max_bad_rate: float = 0.02) -> int:
    """Lowest cut-off whose approved book stays under the target bad rate."""
    ok = strategy.loc[strategy["approved_bad_rate"] <= max_bad_rate]
    if ok.empty:
        return int(strategy["cutoff"].max())
    return int(ok["cutoff"].min())


@dataclass
class DecisionEngine:
    """Policy rules plus a scorecard cut-off, with a refer band below it."""

    scorecard: Scorecard
    cutoff: int
    refer_band: int = 20

    def decide(self, applications: pd.DataFrame, id_col: str = "loan_id") -> list[Decision]:
        missing = [c for c in self.scorecard.selected + ["dti_ratio", "bureau_score", "savings_coverage_ratio", "product_type"]
                   if c not in applications.columns]
        if missing:
            raise KeyError(f"Applications are missing columns: {missing}")
        scores = self.scorecard.score(applications).astype(int)
        pds = self.scorecard.predict_pd(applications)
        reasons = self.scorecard.reason_codes(applications)
        out: list[Decision] = []
        for i, (_, app) in enumerate(applications.iterrows()):
            policy: list[str] = []
            if app["dti_ratio"] > config.MAX_DTI:
                policy.append(f"Policy: DTI {app['dti_ratio']:.0%} above {config.MAX_DTI:.0%}")
            if app["bureau_score"] < config.MIN_BUREAU_SCORE:
                policy.append(f"Policy: bureau score {int(app['bureau_score'])} below {config.MIN_BUREAU_SCORE}")
            if "PV" in str(app["product_type"]) and app["savings_coverage_ratio"] < config.MIN_SAVINGS_COVERAGE:
                policy.append(
                    f"Policy: energy savings cover only {app['savings_coverage_ratio']:.0%} of the instalment"
                )
            if policy:
                decision = "Decline"
                why = policy
            elif scores[i] >= self.cutoff:
                decision = "Approve"
                why = []
            elif scores[i] >= self.cutoff - self.refer_band:
                decision = "Refer"
                why = [f"Score {scores[i]} in refer band"] + reasons[i]
            else:
                decision = "Decline"
                why = [f"Score {scores[i]} below cut-off {self.cutoff}"] + reasons[i]
            out.append(Decision(str(app[id_col]), decision, int(scores[i]), round(float(pds[i]), 4), why))
        return out

    @staticmethod
    def to_frame(decisions: list[Decision]) -> pd.DataFrame:
        return pd.DataFrame(
            [{"application_id": d.application_id, "decision": d.decision, "score": d.score,
              "pd_12m": d.pd_12m, "reasons": "; ".join(d.reasons)} for d in decisions]
        )
