"""Settings for the synthetic broker, its monitoring programme and the oversight checks.

Everything is invented. Client and watchlist names are built from random syllables,
account numbers are random hashes, analysts are codes (A01 to A08) and the high-risk
jurisdictions are placeholders (HR1 to HR4). No real person, company, sanctions list
or country assessment is used, so the data contains no personal data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

SEED = 20261119
N_CLIENTS = 15_000
START = "2025-10-01"
END = "2026-09-30"
MONTHS = [f"2025-{m:02d}" for m in (10, 11, 12)] + [f"2026-{m:02d}" for m in range(1, 10)]

# Residence countries for clients; HR1-HR4 stand for high-risk jurisdictions in the risk methodology.
RESIDENCE = {"DE": 0.88, "AT": 0.04, "NL": 0.02, "PL": 0.02, "IT": 0.02, "ES": 0.02}
HIGH_RISK_JURISDICTIONS = ["HR1", "HR2", "HR3", "HR4"]

# Planted suspicious behaviour (typology: number of clients)
TYPOLOGIES = {
    "T1 structuring": 25,
    "T2 pass-through": 30,
    "T3 third-party funding": 30,
    "T4 mule ring": 36,          # six rings of six sharing a payout account or device
    "T5 high-risk jurisdiction": 20,
    "T6 profile mismatch": 25,
}
SANCTIONED_CLIENTS = 3          # clients whose names match a watchlist entry

# Transaction monitoring rules run by the (outsourced) first line
RULES = {
    "R01": "Single deposit of EUR 15,000 or more",
    "R02": "Several deposits between EUR 8,500 and 9,999 within 30 days",
    "R03": "Rapid in and out: 80% of deposits withdrawn within 7 days, little trading",
    "R04": "Funding from 2 or more third-party accounts within 30 days",
    "R05": "Deposit from a high-risk jurisdiction",
    "R06": "Monthly deposits above 5x the expected amount and above EUR 20,000",
}
R02_COUNT_BEFORE = 3
R02_COUNT_AFTER = 5             # silently changed in the vendor system
R02_CHANGE_DATE = "2026-04-01"

# Feed gap: card deposits from one payment provider never reached the monitoring system
FEED_GAP = ("2026-06-10", "2026-07-05", "PSP-B")

# First-line alert handling
ANALYSTS = [f"A{i:02d}" for i in range(1, 9)]
WEAK_ANALYST = "A06"            # closes too many real cases
SLOPPY_ANALYST = "A03"          # often leaves no rationale
ALERT_SLA_DAYS = 30
SCREENING_SLA_DAYS = 1
SCREENING_THRESHOLD = 0.86
SCREENING_OUTAGE = ("2026-03-09", "2026-03-13")   # new clients in this window screened late

PERIODIC_REVIEW_MONTHS = {"high": 12, "medium": 24, "low": 36}

# Risk appetite for the monthly MI (green up to amber limit, amber up to red limit)
KRI_LIMITS = {
    "alerts_over_sla_pct": (0.05, 0.15),
    "qa_error_rate": (0.03, 0.08),
    "missing_rationale_pct": (0.02, 0.05),
    "screening_late_count": (0, 10),
    "tm_feed_completeness_gap_pct": (0.001, 0.01),
    "overdue_reviews_high_risk": (5, 20),
    "median_days_alert_to_sar": (25, 35),
}

QA_CONFIDENCE = 0.95
QA_TOLERABLE_ERROR = 0.05


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

    @property
    def sql(self) -> Path:
        return self.root / "sql"
