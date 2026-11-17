import numpy as np
import pandas as pd
import pytest

from solar_credit import config
from solar_credit.data_generator import annuity_payment, generate_loan_book, remaining_balance


def test_same_seed_gives_same_data():
    a = generate_loan_book(n_loans=300, n_installers=20, seed=5)
    b = generate_loan_book(n_loans=300, n_installers=20, seed=5)
    pd.testing.assert_frame_equal(a.loans, b.loans)
    pd.testing.assert_frame_equal(a.performance, b.performance)


def test_no_hidden_or_personal_columns(book):
    for frame in (book.loans, book.installers):
        assert not [c for c in frame.columns if c.startswith("_")]
    banned = {"name", "first_name", "last_name", "address", "date_of_birth", "iban", "email"}
    assert banned.isdisjoint(book.loans.columns)


def test_loan_fields_are_in_range(book):
    loans = book.loans
    assert loans["loan_id"].is_unique
    assert loans["bureau_score"].between(100, 999).all()
    assert (loans["loan_amount_eur"] > 0).all()
    assert loans["interest_rate"].between(0.02, 0.12).all()
    assert set(loans["product_type"]) <= {p.name for p in config.PRODUCTS}
    assert set(loans["country"]) <= {"DE", "AT"}


def test_default_rate_is_plausible(book):
    rate = book.loans["default_flag"].mean()
    assert 0.02 < rate < 0.15


def test_performance_is_consistent(book):
    perf = book.performance
    assert perf["outstanding_balance_eur"].ge(0).all()
    assert perf["days_past_due"].isin([0, 30, 60, 90]).all()
    # One default row per defaulted loan, with 90 DPD.
    defaults = perf.loc[perf["status"] == "Defaulted"]
    assert defaults["loan_id"].is_unique
    assert (defaults["days_past_due"] == 90).all()
    assert len(defaults) == book.loans["default_flag"].sum()
    # Nothing is observed after the observation date.
    assert perf["as_of_date"].max() <= pd.Timestamp(config.OBSERVATION_DATE)


def test_annuity_amortises_to_zero():
    principal = np.array([20_000.0])
    rate = np.array([0.06])
    term = np.array([120])
    pay = annuity_payment(principal, rate, term)[0]
    assert pay == pytest.approx(222.04, abs=0.01)
    assert remaining_balance(principal, rate, term, np.array([120]))[0] == pytest.approx(0, abs=1e-6)
    assert remaining_balance(principal, rate, term, np.array([0]))[0] == pytest.approx(20_000)


def test_rejects_bad_sizes():
    with pytest.raises(ValueError):
        generate_loan_book(n_loans=0)
