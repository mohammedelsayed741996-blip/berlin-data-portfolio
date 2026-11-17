"""IFRS 9 style expected credit loss on the live book.

Simplifications, stated up front:
* cash flows are not discounted;
* exposure at default is today's outstanding balance (no amortisation credit);
* lifetime PD uses the 12-month PD for the next year and lets the annual
  PD fade by ``PD_DECAY`` per year after that, matching the seasoning shape
  of the vintage curves (defaults bunch up in the first two years).
Each of these makes the ECL a little conservative, which is the right side to
err on in an investor report.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import config
from .features import FEATURES

SICR_PD_MULTIPLE = 2.0  # stage 2 if current PD is more than 2x the PD at origination
STAGE2_DPD = 30
PD_DECAY = 0.80  # annual PD in year k = PD_12m * PD_DECAY ** (k - 1)


def lifetime_pd(pd_12m: np.ndarray, remaining_months: np.ndarray, decay: float = PD_DECAY) -> np.ndarray:
    """Cumulative default probability over the remaining term."""
    years = np.maximum(np.ceil(np.asarray(remaining_months, dtype=float) / 12.0), 1).astype(int)
    pd_12m = np.clip(np.asarray(pd_12m, dtype=float), 0.0, 1.0)
    survival = np.ones_like(pd_12m)
    for k in range(int(years.max())):
        active = years > k
        annual = np.clip(pd_12m * decay**k, 0.0, 1.0)
        survival = np.where(active, survival * (1 - annual), survival)
    return 1 - survival


def current_book(loans: pd.DataFrame, performance: pd.DataFrame) -> pd.DataFrame:
    """Latest observation of every loan that is still open (incl. open workouts)."""
    obs = pd.Timestamp(config.OBSERVATION_DATE)
    latest = performance.sort_values("as_of_date").groupby("loan_id").tail(1)
    open_perf = latest.loc[
        (latest["as_of_date"] == obs) & latest["status"].isin(["Performing", "Delinquent"])
    ]
    open_workouts = latest.loc[latest["status"] == "Defaulted"].merge(
        loans.loc[loans["workout_closed_flag"] == 0, ["loan_id"]], on="loan_id"
    )
    book = pd.concat([open_perf, open_workouts], ignore_index=True)
    book = book.merge(loans, on="loan_id", how="left", validate="one_to_one")
    book["remaining_term_months"] = np.clip(book["term_months"] - book["months_on_book"], 1, None)
    return book


def lgd_by_product(loans: pd.DataFrame) -> pd.DataFrame:
    """Realised LGD from closed workouts, with the product prior as fallback.

    A credibility weight blends observed LGD and the prior: with few closed
    cases the prior dominates.
    """
    closed = loans.loc[loans["workout_closed_flag"] == 1].copy()
    closed["lgd"] = 1 - closed["recovery_eur"] / closed["ead_at_default_eur"]
    obs = closed.groupby("product_type").agg(closed_workouts=("lgd", "size"), realised_lgd=("lgd", "mean"))
    prior = pd.Series({p.name: p.base_lgd for p in config.PRODUCTS}, name="prior_lgd")
    out = prior.to_frame().join(obs).fillna({"closed_workouts": 0})
    weight = out["closed_workouts"] / (out["closed_workouts"] + 30)
    out["lgd"] = (weight * out["realised_lgd"].fillna(out["prior_lgd"]) + (1 - weight) * out["prior_lgd"]).round(4)
    return out.reset_index(names="product_type")


def roll_to_default_pd(performance: pd.DataFrame, horizon: int = 12) -> dict[int, float]:
    """Share of loans in a given DPD bucket that default within ``horizon`` months."""
    perf = performance[["loan_id", "months_on_book", "days_past_due", "status"]]
    defaults = perf.loc[perf["status"] == "Defaulted", ["loan_id", "months_on_book"]].rename(
        columns={"months_on_book": "default_mob"}
    )
    obs_end = performance.groupby("loan_id")["months_on_book"].max().rename("last_mob")
    out: dict[int, float] = {}
    for bucket in (30, 60):
        rows = perf.loc[perf["days_past_due"] == bucket].merge(defaults, on="loan_id", how="left")
        rows = rows.merge(obs_end, on="loan_id")
        # Only rows with a full horizon of follow-up, or that defaulted inside it.
        hit = rows["default_mob"].notna() & (rows["default_mob"] - rows["months_on_book"] <= horizon)
        full = (rows["last_mob"] - rows["months_on_book"] >= horizon) | hit
        rows = rows.loc[full]
        out[bucket] = float(hit[full].mean()) if len(rows) else np.nan
    return out


@dataclass
class ECLResult:
    """Loan-level ECL plus a summary by stage."""

    loans: pd.DataFrame
    by_stage: pd.DataFrame

    @property
    def total_ecl(self) -> float:
        return float(self.loans["ecl_eur"].sum())

    @property
    def total_exposure(self) -> float:
        return float(self.loans["ead_eur"].sum())

    @property
    def coverage(self) -> float:
        return self.total_ecl / self.total_exposure


def compute_ecl(
    book: pd.DataFrame,
    pd_12m: np.ndarray,
    pd_origination: np.ndarray,
    lgd_table: pd.DataFrame,
    roll_rates: dict[int, float],
    lgd_add_on: float = 0.0,
) -> ECLResult:
    """Stage every loan and compute its expected credit loss."""
    if len(book) != len(pd_12m) or len(book) != len(pd_origination):
        raise ValueError("PD arrays must align with the book")
    df = book[["loan_id", "product_type", "region", "installer_id", "status", "days_past_due",
               "remaining_term_months", "outstanding_balance_eur"] + [f for f in FEATURES if f not in ("product_type",)]].copy()
    df["ead_eur"] = df["outstanding_balance_eur"]
    lgd_map = dict(zip(lgd_table["product_type"], lgd_table["lgd"]))
    df["lgd"] = np.clip(df["product_type"].map(lgd_map).astype(float) + lgd_add_on, 0, 1)

    pd12 = np.asarray(pd_12m, dtype=float).copy()
    dpd = df["days_past_due"].to_numpy()
    for bucket, roll in roll_rates.items():
        if not np.isnan(roll):
            pd12 = np.where(dpd == bucket, np.maximum(pd12, roll), pd12)
    df["pd_12m"] = pd12
    df["pd_origination"] = pd_origination

    defaulted = df["status"].eq("Defaulted").to_numpy()
    sicr = (dpd >= STAGE2_DPD) | (pd12 > SICR_PD_MULTIPLE * np.asarray(pd_origination))
    df["stage"] = np.select([defaulted, sicr], [3, 2], default=1)

    life = lifetime_pd(pd12, df["remaining_term_months"].to_numpy())
    df["pd_lifetime"] = life
    df["pd_used"] = np.select([df["stage"] == 3, df["stage"] == 2], [1.0, life], default=pd12)
    df["ecl_eur"] = (df["pd_used"] * df["lgd"] * df["ead_eur"]).round(2)

    by_stage = (
        df.groupby("stage")
        .agg(loans=("loan_id", "size"), exposure_eur=("ead_eur", "sum"), ecl_eur=("ecl_eur", "sum"))
        .assign(coverage=lambda t: t["ecl_eur"] / t["exposure_eur"])
        .round({"exposure_eur": 0, "ecl_eur": 0, "coverage": 4})
        .reset_index()
    )
    return ECLResult(loans=df, by_stage=by_stage)
