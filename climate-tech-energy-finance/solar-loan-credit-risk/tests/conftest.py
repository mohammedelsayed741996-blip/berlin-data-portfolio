"""Shared fixtures: a small loan book generated once per test session."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from solar_credit.data_generator import LoanBook, generate_loan_book  # noqa: E402
from solar_credit.features import build_model_data  # noqa: E402
from solar_credit.scorecard import Scorecard  # noqa: E402


@pytest.fixture(scope="session")
def book() -> LoanBook:
    return generate_loan_book(n_loans=4_000, n_installers=60, seed=11)


@pytest.fixture(scope="session")
def model_data(book):
    return build_model_data(book.loans)


@pytest.fixture(scope="session")
def scorecard(model_data) -> Scorecard:
    return Scorecard().fit(model_data.X_train, model_data.y_train)
