"""Settings for the synthetic issuer universe, the news feed and the models.

Every issuer, article and number here is invented. Issuer names are generated
from syllables, articles never name a person, and nothing refers to a real
company, so the data contains no personal or confidential information.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

SEED = 20261118
N_ISSUERS = 360
START = "2022-01"
END = "2026-09"                 # last month with data
TEST_START = "2025-07"          # out-of-time test period (15 months)
HORIZON_MONTHS = 3              # target: downgrade within the next 3 months
ALERT_THRESHOLD_TOP_K = 15      # analysts can review about 15 names a month

# Rating scale used for corporates; index 0 is the best rating.
RATINGS = ["AA", "AA-", "A+", "A", "A-", "BBB+", "BBB", "BBB-", "BB+", "BB", "BB-", "B+", "B", "B-", "CCC"]
INVESTMENT_GRADE_FLOOR = "BBB-"

SECTORS = {
    # sector: (share of issuers, sensitivity to the sector shock, de-domiciled share)
    "Real estate": (0.12, 1.6, 0.55),
    "Automotive": (0.10, 1.3, 0.60),
    "Chemicals": (0.10, 1.1, 0.50),
    "Retail": (0.10, 1.2, 0.40),
    "Utilities": (0.10, 0.6, 0.45),
    "Telecoms": (0.08, 0.5, 0.35),
    "Industrials": (0.14, 0.9, 0.55),
    "Transport & logistics": (0.08, 1.0, 0.40),
    "Healthcare": (0.08, 0.4, 0.35),
    "Consumer goods": (0.10, 0.7, 0.40),
}

# Months in which a sector took a hit (sector, start month, length in months, size)
SECTOR_SHOCKS = [
    ("Real estate", "2022-10", 9, 0.10),        # rate rise
    ("Chemicals", "2022-09", 6, 0.08),          # gas prices
    ("Retail", "2023-03", 6, 0.06),
    ("Automotive", "2024-10", 8, 0.07),         # EV transition, weak demand
    ("Real estate", "2025-09", 5, 0.05),
    ("Chemicals", "2025-11", 6, 0.06),
]

LANGUAGE_SHARE_DE = 0.30        # share of articles in German (more for German issuers)
ARTICLES_PER_MONTH = 2.4        # average per issuer, more when something happens


@dataclass
class Paths:
    root: Path = field(default_factory=lambda: Path(__file__).resolve().parents[2])

    @property
    def data(self) -> Path:
        return self.root / "data"

    @property
    def outputs(self) -> Path:
        return self.root / "outputs"

    @property
    def figures(self) -> Path:
        return self.root / "outputs" / "figures"
