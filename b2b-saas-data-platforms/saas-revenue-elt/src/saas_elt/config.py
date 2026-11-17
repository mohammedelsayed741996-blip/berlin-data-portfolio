"""Paths and simulation settings for the SaaS revenue ELT platform."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
CONTRACTS_DIR: Path = PROJECT_ROOT / "contracts"
DBT_DIR: Path = PROJECT_ROOT / "dbt_project"
OUTPUT_DIR: Path = PROJECT_ROOT / "outputs"

START_DATE: str = "2026-07-01"
N_DAYS: int = 92  # July to September 2026
SEED: int = 7

PLANS: dict[str, float] = {"Starter": 29.0, "Growth": 59.0, "Scale": 99.0}  # EUR per seat per month
COUNTRIES: dict[str, float] = {"DE": 0.55, "AT": 0.12, "CH": 0.10, "NL": 0.10, "FR": 0.07, "PL": 0.06}
TAX_RATES: dict[str, float] = {"DE": 0.19, "AT": 0.20, "CH": 0.081, "NL": 0.21, "FR": 0.20, "PL": 0.23}
CHF_PER_EUR: float = 0.95  # invoices to Swiss customers are issued in CHF
INDUSTRIES: tuple[str, ...] = ("Logistics", "Retail", "Manufacturing", "Healthcare", "FinancialServices", "Energy", "Software")
SEGMENTS: tuple[str, ...] = ("SMB", "MidMarket", "Enterprise")
EVENT_TYPES: tuple[str, ...] = ("login", "report_created", "dashboard_viewed", "export", "api_call")

# Planted incidents: day index (0 = START_DATE) -> what goes wrong.
INCIDENTS: dict[int, str] = {
    19: "api_page_overlap",      # billing API repeats records across page boundaries
    34: "schema_drift",          # billing API starts sending a new field: discount_eur
    49: "bad_segment_value",     # CRM writes 'Mid-Market' instead of 'MidMarket'
    59: "negative_invoice",      # an invoice arrives with a negative net amount
    69: "malformed_event_lines", # event file contains broken JSON lines
    74: "transform_outage",      # warehouse transform step fails all retries
}


@dataclass
class RunSettings:
    """Where one simulation run keeps its source systems and warehouse."""

    workdir: Path
    seed: int = SEED
    start_date: str = START_DATE
    n_days: int = N_DAYS
    initial_accounts: int = 320
    incidents: dict[int, str] = field(default_factory=lambda: dict(INCIDENTS))
    retry_backoff_s: float = 0.0  # kept at zero in simulation so runs stay fast

    @property
    def source_dir(self) -> Path:
        return self.workdir / "sources"

    @property
    def crm_db(self) -> Path:
        return self.source_dir / "crm.db"

    @property
    def event_drop_dir(self) -> Path:
        return self.source_dir / "event_drops"

    @property
    def warehouse_db(self) -> Path:
        return self.workdir / "warehouse" / "warehouse.db"
