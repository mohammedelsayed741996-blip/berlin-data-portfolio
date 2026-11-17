"""Synthetic loan book for residential solar, battery and heat pump financing.

The generator produces three tables that mirror what a green-energy lender
would hold after three years of originations through installer partners:

* ``installers``  - one row per installation company (pseudonymous IDs)
* ``loans``       - one row per loan, origination data plus final outcome
* ``performance`` - one row per loan and month: balance and days past due

Defaults are drawn from a known risk equation, so the models built later can
be checked against a ground truth. The data holds no names, addresses or
birth dates: borrowers and installers appear only as pseudonymous IDs.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from . import config

logger = logging.getLogger(__name__)


@dataclass
class LoanBook:
    """Container for the three generated tables."""

    installers: pd.DataFrame
    loans: pd.DataFrame
    performance: pd.DataFrame

    def save(self, data_dir: Path) -> None:
        """Write the tables as CSV (performance is gzip-compressed)."""
        data_dir.mkdir(parents=True, exist_ok=True)
        self.installers.to_csv(data_dir / "installers.csv", index=False)
        self.loans.to_csv(data_dir / "loans.csv", index=False)
        self.performance.to_csv(
            data_dir / "performance.csv.gz", index=False, compression="gzip"
        )
        logger.info("Saved loan book to %s", data_dir)


def annuity_payment(principal: np.ndarray, annual_rate: np.ndarray, term: np.ndarray) -> np.ndarray:
    """Monthly instalment of a fully amortising annuity loan."""
    r = annual_rate / 12.0
    with np.errstate(divide="ignore", invalid="ignore"):
        pay = principal * r / (1.0 - (1.0 + r) ** (-term))
    return np.where(r == 0, principal / term, pay)


def remaining_balance(
    principal: np.ndarray, annual_rate: np.ndarray, term: np.ndarray, months_paid: np.ndarray
) -> np.ndarray:
    """Outstanding principal of an annuity loan after ``months_paid`` instalments."""
    r = annual_rate / 12.0
    k = np.minimum(months_paid, term)
    growth = (1.0 + r) ** k
    pay = annuity_payment(principal, annual_rate, term)
    bal = principal * growth - pay * (growth - 1.0) / r
    return np.clip(bal, 0.0, None)


def _months_between(start: pd.Series, end: pd.Timestamp) -> np.ndarray:
    return ((end.year - start.dt.year) * 12 + (end.month - start.dt.month)).to_numpy()


def generate_installers(rng: np.random.Generator, n_installers: int) -> pd.DataFrame:
    """Installer partners with a hidden quality factor that affects borrower risk."""
    regions = list(config.REGIONS)
    weights = np.array([v[0] for v in config.REGIONS.values()])
    return pd.DataFrame(
        {
            "installer_id": [f"INST-{i:04d}" for i in range(1, n_installers + 1)],
            "installer_region": rng.choice(regions, size=n_installers, p=weights / weights.sum()),
            "installer_tenure_years": rng.integers(1, 26, size=n_installers),
            # Hidden: poor installation quality raises customer default risk.
            "_installer_quality": rng.normal(0.0, 1.0, size=n_installers),
            # A few installers write most of the volume (Pareto-like).
            "_volume_weight": rng.pareto(1.6, size=n_installers) + 0.2,
        }
    )


def generate_loans(
    rng: np.random.Generator, installers: pd.DataFrame, n_loans: int
) -> pd.DataFrame:
    """Origination data: borrower, asset, pricing and the true default probability."""
    vol = installers["_volume_weight"].to_numpy()
    inst_idx = rng.choice(len(installers), size=n_loans, p=vol / vol.sum())
    inst = installers.iloc[inst_idx].reset_index(drop=True)

    # Origination dates with growth: later months carry more volume.
    months = pd.date_range(config.FIRST_ORIGINATION, config.LAST_ORIGINATION, freq="MS")
    growth = np.linspace(1.0, 3.0, len(months))
    orig_month = rng.choice(months, size=n_loans, p=growth / growth.sum())
    orig_day = rng.integers(0, 28, size=n_loans)
    origination_date = pd.to_datetime(orig_month) + pd.to_timedelta(orig_day, unit="D")

    # Most customers live in their installer's region.
    regions = np.array(list(config.REGIONS))
    reg_w = np.array([v[0] for v in config.REGIONS.values()])
    random_region = rng.choice(regions, size=n_loans, p=reg_w / reg_w.sum())
    same_region = rng.random(n_loans) < 0.85
    region = np.where(same_region, inst["installer_region"].to_numpy(), random_region)
    unemployment = np.array([config.REGIONS[r][1] for r in region])

    # Product, amount, term.
    prod_names = np.array([p.name for p in config.PRODUCTS])
    prod_share = np.array([p.share for p in config.PRODUCTS])
    prod_idx = rng.choice(len(config.PRODUCTS), size=n_loans, p=prod_share)
    product = prod_names[prod_idx]
    lo = np.array([config.PRODUCTS[i].min_amount for i in prod_idx])
    hi = np.array([config.PRODUCTS[i].max_amount for i in prod_idx])
    loan_amount = np.round(lo + (hi - lo) * rng.beta(2.0, 2.5, size=n_loans), -2)
    term = np.array([rng.choice(config.PRODUCTS[i].terms_months) for i in prod_idx])

    # Borrower profile.
    emp_types = np.array(list(config.EMPLOYMENT_TYPES))
    emp_w = np.array(list(config.EMPLOYMENT_TYPES.values()))
    employment = rng.choice(emp_types, size=n_loans, p=emp_w)
    income = rng.lognormal(mean=np.log(4_300), sigma=0.38, size=n_loans)
    income = np.where(employment == "Retired", income * 0.72, income)
    income = np.where(employment == "CivilServant", income * 1.08, income)
    income = np.round(np.clip(income, 1_800, 16_000), -1)
    bureau = np.clip(rng.normal(760, 110, size=n_loans), 100, 999).round().astype(int)
    existing_debt = np.round(income * rng.beta(1.3, 9.0, size=n_loans), -1)

    # Risk-based pricing grid by bureau band (fixed rate for the full term).
    base_rate = np.select(
        [bureau >= 850, bureau >= 750, bureau >= 650, bureau >= 550],
        [0.0449, 0.0529, 0.0619, 0.0729],
        default=0.0849,
    )
    rate = np.round(base_rate + rng.normal(0, 0.0025, size=n_loans) + (term - 120) / 240 * 0.006, 4)
    instalment = annuity_payment(loan_amount, rate, term)

    # System size and expected savings.
    has_pv = np.char.find(product.astype(str), "PV") >= 0
    has_batt = np.char.find(product.astype(str), "Battery") >= 0
    kwp = np.where(has_pv, np.round(loan_amount / np.where(has_batt, 2_300, 1_500), 1), 0.0)
    self_consumption = np.where(has_batt, 0.65, 0.33) * rng.uniform(0.85, 1.15, size=n_loans)
    pv_kwh = kwp * config.PV_YIELD_KWH_PER_KWP
    pv_savings = pv_kwh * (
        self_consumption * config.ELECTRICITY_PRICE_EUR_KWH
        + (1 - self_consumption) * config.FEED_IN_TARIFF_EUR_KWH
    )
    heat_demand_kwh = rng.uniform(12_000, 22_000, size=n_loans)
    hp_savings = np.where(
        product == "HeatPump",
        heat_demand_kwh * config.GAS_PRICE_EUR_KWH
        - heat_demand_kwh / 3.2 * config.ELECTRICITY_PRICE_EUR_KWH * 0.75,
        0.0,
    )
    annual_savings = np.round(np.clip(pv_savings + hp_savings, 150, None), 0)
    coverage = annual_savings / 12.0 / instalment
    dti = (existing_debt + instalment) / income

    df = pd.DataFrame(
        {
            "loan_id": [f"LN-{i:06d}" for i in range(1, n_loans + 1)],
            "installer_id": inst["installer_id"].to_numpy(),
            "origination_date": origination_date.normalize(),
            "country": np.where(region == "Austria", "AT", "DE"),
            "region": region,
            "region_unemployment_pct": unemployment,
            "product_type": product,
            "loan_amount_eur": loan_amount,
            "term_months": term,
            "interest_rate": rate,
            "monthly_instalment_eur": np.round(instalment, 2),
            "system_kwp": kwp,
            "expected_annual_savings_eur": annual_savings,
            "savings_coverage_ratio": np.round(coverage, 3),
            "employment_type": employment,
            "net_monthly_income_eur": income,
            "existing_debt_payments_eur": existing_debt,
            "dti_ratio": np.round(dti, 4),
            "bureau_score": bureau,
            "installer_tenure_years": inst["installer_tenure_years"].to_numpy(),
        }
    )

    # True annual default probability (hidden ground truth).
    logit = (
        -4.0
        - 0.0105 * (bureau - 760)
        + 4.2 * (dti - 0.25)
        - 0.85 * (np.clip(coverage, 0, 2) - 0.7)
        + 0.55 * (employment == "SelfEmployed")
        - 0.45 * (employment == "CivilServant")
        + 0.12 * (unemployment - 5.5)
        + 0.30 * inst["_installer_quality"].to_numpy() * -1
        - 0.015 * (inst["installer_tenure_years"].to_numpy() - 10)
        + 0.25 * (product == "HeatPump")
        + rng.normal(0, 0.35, size=n_loans)
    )
    df["_true_annual_pd"] = 1.0 / (1.0 + np.exp(-logit))
    return df


def _seasoning_multiplier(mob: np.ndarray) -> np.ndarray:
    """Default hazard rises over the first year on book, then eases."""
    return 0.35 + 1.15 * np.exp(-((mob - 14.0) ** 2) / (2 * 9.0**2)) + 0.45 * (mob > 14)


def simulate_performance(
    rng: np.random.Generator, loans: pd.DataFrame, observation_date: pd.Timestamp
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Simulate monthly balances, delinquency, default, prepayment and recoveries."""
    n = len(loans)
    first_month = loans["origination_date"] + pd.offsets.MonthEnd(1)
    max_mob = _months_between(first_month, observation_date) + 1
    max_mob = np.clip(max_mob, 0, None)
    horizon = int(max_mob.max())

    annual_pd = loans["_true_annual_pd"].to_numpy()
    base_monthly = 1.0 - (1.0 - annual_pd) ** (1.0 / 12.0)

    default_mob = np.full(n, -1)
    prepay_mob = np.full(n, -1)
    active = np.ones(n, dtype=bool)
    for mob in range(1, horizon + 1):
        alive = active & (mob <= max_mob)
        if not alive.any():
            continue
        haz = np.clip(base_monthly * _seasoning_multiplier(np.array(mob, dtype=float)), 0, 0.5)
        u = rng.random(n)
        # Default is recognised at 90+ DPD; it needs three months on book.
        new_def = alive & (mob >= 3) & (u < haz)
        prepay = alive & ~new_def & (rng.random(n) < 0.0035)
        default_mob[new_def] = mob
        prepay_mob[prepay] = mob
        active &= ~(new_def | prepay)

    amount = loans["loan_amount_eur"].to_numpy()
    rate = loans["interest_rate"].to_numpy()
    term = loans["term_months"].to_numpy()

    # Temporary delinquency that cures (does not end in default).
    cure_start = np.where(
        rng.random(n) < np.clip(annual_pd * 4.0, 0, 0.6),
        rng.integers(2, np.maximum(max_mob, 3) + 1),
        -1,
    )
    cure_len = rng.choice([1, 2], size=n, p=[0.75, 0.25])

    rows = []
    for i in range(n):
        last = int(max_mob[i])
        if last <= 0:
            continue
        d, p = default_mob[i], prepay_mob[i]
        end = last
        if p > 0:
            end = min(end, p)
        if d > 0:
            end = min(end, d)
        mobs = np.arange(1, end + 1)
        bal = remaining_balance(
            np.full(len(mobs), amount[i]), np.full(len(mobs), rate[i]),
            np.full(len(mobs), term[i]), mobs,
        )
        dpd = np.zeros(len(mobs), dtype=int)
        status = np.array(["Performing"] * len(mobs), dtype=object)
        if d > 0:
            # Missed payments: balance stops amortising from first missed month.
            first_missed = d - 3
            for k, mob in enumerate(mobs):
                if mob > first_missed:
                    dpd[k] = min(90, 30 * (mob - first_missed))
                    bal[k] = remaining_balance(
                        np.array([amount[i]]), np.array([rate[i]]), np.array([term[i]]),
                        np.array([max(first_missed, 0)]),
                    )[0]
            status[dpd > 0] = "Delinquent"
            status[-1] = "Defaulted"
        elif cure_start[i] > 0 and cure_start[i] <= end:
            for k, mob in enumerate(mobs):
                if cure_start[i] <= mob < cure_start[i] + cure_len[i]:
                    dpd[k] = 30 * (mob - cure_start[i] + 1)
            status[dpd > 0] = "Delinquent"
        if p > 0 and (d < 0 or p < d):
            status[-1] = "Prepaid"
            bal[-1] = 0.0
        as_of = loans["origination_date"].iloc[i] + pd.offsets.MonthEnd(1)
        as_of_dates = pd.date_range(as_of, periods=len(mobs), freq="ME")
        rows.append(
            pd.DataFrame(
                {
                    "loan_id": loans["loan_id"].iloc[i],
                    "as_of_date": as_of_dates,
                    "months_on_book": mobs,
                    "outstanding_balance_eur": np.round(bal, 2),
                    "days_past_due": dpd,
                    "status": status,
                }
            )
        )
    perf = pd.concat(rows, ignore_index=True)

    # Outcome fields on the loan table.
    out = loans.copy()
    out["default_flag"] = (default_mob > 0).astype(int)
    out["default_mob"] = np.where(default_mob > 0, default_mob, np.nan)
    out["prepaid_flag"] = ((prepay_mob > 0) & (default_mob < 0)).astype(int)
    ead = perf.loc[perf["status"] == "Defaulted"].set_index("loan_id")["outstanding_balance_eur"]
    out["ead_at_default_eur"] = out["loan_id"].map(ead)

    # Recoveries: product-specific, collected 6-18 months after default.
    base_lgd = out["product_type"].map({p.name: p.base_lgd for p in config.PRODUCTS}).to_numpy()
    lgd = np.clip(rng.beta(base_lgd * 8, (1 - base_lgd) * 8), 0.05, 1.0)
    workout = rng.integers(6, 19, size=n)
    def_dates = [
        (od + pd.offsets.MonthEnd(int(m))) if m > 0 else pd.NaT
        for od, m in zip(out["origination_date"], default_mob)
    ]
    out["default_date"] = pd.to_datetime(def_dates)
    closed = out["default_flag"].eq(1) & (
        out["default_date"] + pd.to_timedelta(workout * 30, unit="D") <= observation_date
    )
    out["workout_closed_flag"] = closed.astype(int)
    out["recovery_eur"] = np.where(closed, np.round(out["ead_at_default_eur"] * (1 - lgd), 2), np.nan)
    return out, perf


def generate_loan_book(
    n_loans: int = config.N_LOANS,
    n_installers: int = config.N_INSTALLERS,
    seed: int = config.SEED,
) -> LoanBook:
    """Build the full synthetic loan book. Same seed, same data."""
    if n_loans <= 0 or n_installers <= 0:
        raise ValueError("n_loans and n_installers must be positive")
    rng = np.random.default_rng(seed)
    obs = pd.Timestamp(config.OBSERVATION_DATE)
    installers = generate_installers(rng, n_installers)
    loans = generate_loans(rng, installers, n_loans)
    loans, perf = simulate_performance(rng, loans, obs)
    logger.info(
        "Generated %d loans, %d performance rows, %d defaults",
        len(loans), len(perf), int(loans["default_flag"].sum()),
    )
    public_inst = installers.drop(columns=[c for c in installers if c.startswith("_")])
    public_loans = loans.drop(columns=[c for c in loans if c.startswith("_")])
    return LoanBook(installers=public_inst, loans=public_loans, performance=perf)


def load_loan_book(data_dir: Path = config.DATA_DIR) -> LoanBook:
    """Read the saved tables, generating them first if they are missing."""
    needed = ["installers.csv", "loans.csv", "performance.csv.gz"]
    if not all((data_dir / f).exists() for f in needed):
        logger.info("Data not found in %s, generating it", data_dir)
        generate_loan_book().save(data_dir)
    installers = pd.read_csv(data_dir / "installers.csv")
    loans = pd.read_csv(
        data_dir / "loans.csv", parse_dates=["origination_date", "default_date"]
    )
    perf = pd.read_csv(data_dir / "performance.csv.gz", parse_dates=["as_of_date"])
    return LoanBook(installers=installers, loans=loans, performance=perf)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    generate_loan_book().save(config.DATA_DIR)
