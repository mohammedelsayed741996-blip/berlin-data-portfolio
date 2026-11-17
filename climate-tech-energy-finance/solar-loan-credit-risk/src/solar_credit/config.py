"""Central configuration for the solar loan credit-risk project.

Every number here is a synthetic modelling assumption chosen to look plausible
for a German/Austrian residential green-energy loan book. None of it is
Cloover data or any lender's real data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
DATA_DIR: Path = PROJECT_ROOT / "data"
OUTPUT_DIR: Path = PROJECT_ROOT / "outputs"
FIGURE_DIR: Path = OUTPUT_DIR / "figures"
SQL_DIR: Path = PROJECT_ROOT / "sql"

SEED: int = 42
N_LOANS: int = 10_000
N_INSTALLERS: int = 120

FIRST_ORIGINATION: str = "2023-01-01"
LAST_ORIGINATION: str = "2025-12-31"
OBSERVATION_DATE: str = "2026-10-31"

# Region -> (share of originations, regional unemployment rate in %).
REGIONS: dict[str, tuple[float, float]] = {
    "Bayern": (0.19, 3.8),
    "Baden-Wuerttemberg": (0.17, 4.3),
    "Nordrhein-Westfalen": (0.17, 7.5),
    "Niedersachsen": (0.10, 6.1),
    "Hessen": (0.07, 5.7),
    "Rheinland-Pfalz": (0.05, 5.4),
    "Sachsen": (0.05, 6.4),
    "Brandenburg": (0.05, 6.1),
    "Schleswig-Holstein": (0.04, 5.7),
    "Berlin": (0.03, 9.8),
    "Austria": (0.08, 7.1),
}


@dataclass(frozen=True)
class Product:
    """Loan product financed through installers."""

    name: str
    share: float
    min_amount: float
    max_amount: float
    terms_months: tuple[int, ...]
    base_lgd: float  # expected loss given default before collateral effects


PRODUCTS: tuple[Product, ...] = (
    Product("PV", 0.30, 8_000, 22_000, (60, 120, 180), 0.62),
    Product("PV+Battery", 0.38, 14_000, 35_000, (120, 180, 240), 0.58),
    Product("HeatPump", 0.20, 12_000, 30_000, (120, 180), 0.70),
    Product("PV+Battery+Wallbox", 0.12, 20_000, 45_000, (180, 240), 0.55),
)

EMPLOYMENT_TYPES: dict[str, float] = {
    "Employee": 0.62,
    "CivilServant": 0.10,
    "SelfEmployed": 0.13,
    "Retired": 0.15,
}

# Energy price assumptions used to estimate customer savings (EUR per kWh).
ELECTRICITY_PRICE_EUR_KWH: float = 0.37
FEED_IN_TARIFF_EUR_KWH: float = 0.08
GAS_PRICE_EUR_KWH: float = 0.11
PV_YIELD_KWH_PER_KWP: float = 950.0

# Scorecard scaling: 600 points at 50:1 good:bad odds, 20 points to double odds.
SCORE_BASE_POINTS: float = 600.0
SCORE_BASE_ODDS: float = 50.0
SCORE_PDO: float = 20.0

# Out-of-time split for the 12-month default model.
TRAIN_END: str = "2024-06-30"
PD_HORIZON_MONTHS: int = 12

# Underwriting policy.
MAX_DTI: float = 0.45
MIN_BUREAU_SCORE: int = 400
MIN_SAVINGS_COVERAGE: float = 0.35  # PV products only; heat pump savings are smaller by design


@dataclass(frozen=True)
class Scenario:
    """Macro and collateral shock applied in the stress test."""

    name: str
    electricity_price_change: float = 0.0  # relative change, -0.2 = 20% lower
    unemployment_shift_pp: float = 0.0  # added to every region, in percentage points
    bureau_score_shift: float = 0.0  # applied to every borrower's score
    lgd_add_on: float = 0.0  # absolute add-on to LGD, 0.1 = +10pp
    description: str = ""


SCENARIOS: tuple[Scenario, ...] = (
    Scenario("Baseline", description="Current assumptions, no shock."),
    Scenario(
        "Mild downturn",
        electricity_price_change=-0.15,
        unemployment_shift_pp=1.0,
        bureau_score_shift=-15,
        lgd_add_on=0.05,
        description="Power prices fall 15%, unemployment +1pp, small score drift.",
    ),
    Scenario(
        "Severe recession",
        electricity_price_change=-0.30,
        unemployment_shift_pp=3.0,
        bureau_score_shift=-40,
        lgd_add_on=0.12,
        description="Power prices fall 30%, unemployment +3pp, installer failures cut recoveries.",
    ),
    Scenario(
        "Installer default wave",
        lgd_add_on=0.20,
        description="Several large installers fail: no PD change, recoveries drop sharply.",
    ),
)


@dataclass
class RunConfig:
    """Paths and sizes for one pipeline run, overridable in tests."""

    n_loans: int = N_LOANS
    n_installers: int = N_INSTALLERS
    seed: int = SEED
    data_dir: Path = field(default_factory=lambda: DATA_DIR)
    output_dir: Path = field(default_factory=lambda: OUTPUT_DIR)
