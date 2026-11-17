"""Model dataset: 12-month default target with an out-of-time split."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from . import config

NUMERIC_FEATURES: list[str] = [
    "bureau_score",
    "dti_ratio",
    "savings_coverage_ratio",
    "region_unemployment_pct",
    "installer_tenure_years",
    "loan_amount_eur",
    "term_months",
    "net_monthly_income_eur",
]
CATEGORICAL_FEATURES: list[str] = ["employment_type", "product_type"]
FEATURES: list[str] = NUMERIC_FEATURES + CATEGORICAL_FEATURES
TARGET: str = "default_12m"


@dataclass
class ModelData:
    """Train and out-of-time test sets for the PD model."""

    train: pd.DataFrame
    test: pd.DataFrame

    @property
    def X_train(self) -> pd.DataFrame:
        return self.train[FEATURES]

    @property
    def y_train(self) -> pd.Series:
        return self.train[TARGET]

    @property
    def X_test(self) -> pd.DataFrame:
        return self.test[FEATURES]

    @property
    def y_test(self) -> pd.Series:
        return self.test[TARGET]


def add_default_target(loans: pd.DataFrame, horizon: int = config.PD_HORIZON_MONTHS) -> pd.DataFrame:
    """Flag defaults inside the first ``horizon`` months on book.

    Only loans with a full observation window are kept, so a recent loan that
    simply has not had time to default is never counted as "good".
    """
    obs = pd.Timestamp(config.OBSERVATION_DATE)
    cutoff = obs - pd.DateOffset(months=horizon)
    seasoned = loans.loc[loans["origination_date"] <= cutoff].copy()
    seasoned[TARGET] = (seasoned["default_mob"].fillna(10**6) <= horizon).astype(int)
    return seasoned


def build_model_data(loans: pd.DataFrame) -> ModelData:
    """Out-of-time split: older vintages train the model, newer ones test it."""
    missing = [c for c in FEATURES if c not in loans.columns]
    if missing:
        raise KeyError(f"Loan table is missing model features: {missing}")
    data = add_default_target(loans)
    train_end = pd.Timestamp(config.TRAIN_END)
    train = data.loc[data["origination_date"] <= train_end].reset_index(drop=True)
    test = data.loc[data["origination_date"] > train_end].reset_index(drop=True)
    if train[TARGET].sum() < 20 or test[TARGET].sum() < 20:
        raise ValueError("Too few defaults to fit and validate a PD model")
    return ModelData(train=train, test=test)
