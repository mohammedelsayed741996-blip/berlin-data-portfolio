"""Master data and planning assumptions for a fictional seed-breeding group.

Everything here is invented. The group, its entities, cost centers, vendors and
users are synthetic, and IDs are pseudonymous codes, so no personal data exists
anywhere in the project.

Fiscal year runs July to June, as is common for seed companies whose sales
peak in spring. "FY 2026/27" means July 2026 to June 2027.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

SEED = 20260930
GROUP_NAME = "Feldkern Group (fictional)"
CURRENCY = "EUR"

# Actuals run from the first month of FY 2024/25 to the month being closed.
FIRST_PERIOD = "2024-07"
CLOSE_PERIOD = "2026-09"          # period 3 of FY 2026/27
CUTOFF_WORKING_DAY = 3             # postings must be entered by working day 3 of the next month

ENTITIES = {
    "DE10": {"name": "Feldkern Saaten GmbH", "country": "DE", "revenue_share": 0.60},
    "FR10": {"name": "Feldkern Semences SAS", "country": "FR", "revenue_share": 0.25},
    "AT10": {"name": "Feldkern Saatgut GmbH", "country": "AT", "revenue_share": 0.15},
}

FUNCTIONAL_AREAS = {
    "COS": "Cost of sales",
    "SEL": "Selling",
    "RND": "Research and development",
    "GNA": "General and administration",
}

# cost center: (entity, functional area, name, FTE at start, monthly cost per FTE, non-personnel monthly base EUR)
COST_CENTERS = {
    "1100": ("DE10", "COS", "Production Einbeck", 62, 5600, 2_170_000),
    "1110": ("DE10", "COS", "Seed processing", 38, 5300, 1_540_000),
    "1120": ("DE10", "COS", "Quality lab", 14, 5900, 336_000),
    "2100": ("DE10", "SEL", "Sales sugarbeet DACH", 18, 7400, 455_000),
    "2110": ("DE10", "SEL", "Sales corn DACH", 16, 7200, 416_000),
    "2120": ("DE10", "SEL", "Marketing", 9, 6900, 780_000),
    "2130": ("DE10", "SEL", "Customer service", 11, 5200, 143_000),
    "3100": ("DE10", "RND", "Breeding sugarbeet", 44, 6800, 480_000),
    "3110": ("DE10", "RND", "Breeding corn", 36, 6700, 420_000),
    "3120": ("DE10", "RND", "Biotech lab", 22, 7600, 345_000),
    "3130": ("DE10", "RND", "Field trials", 28, 5400, 285_000),
    "4100": ("DE10", "GNA", "Finance and controlling", 17, 7100, 91_000),
    "4110": ("DE10", "GNA", "Human resources", 9, 6600, 50_000),
    "4120": ("DE10", "GNA", "IT", 14, 7500, 312_000),
    "4130": ("DE10", "GNA", "Management", 5, 14_500, 72_000),
    "1200": ("AT10", "COS", "Production Austria", 21, 5400, 665_000),
    "2200": ("AT10", "SEL", "Sales Austria", 8, 6800, 195_000),
    "3200": ("AT10", "RND", "Field trials Austria", 9, 5300, 84_000),
    "4200": ("AT10", "GNA", "Administration Austria", 6, 6200, 38_000),
    "1300": ("FR10", "COS", "Production France", 33, 5000, 1_050_000),
    "2300": ("FR10", "SEL", "Sales France", 14, 6600, 338_000),
    "2310": ("FR10", "SEL", "Marketing France", 4, 6300, 292_000),
    "3300": ("FR10", "RND", "Breeding cereals", 24, 6200, 255_000),
    "4300": ("FR10", "GNA", "Administration France", 8, 6000, 48_000),
}

# Locked when controlling moved into 4100; postings here are a close error.
BLOCKED_COST_CENTERS = {"4199": ("DE10", "GNA", "Controlling (locked since 01/2025)")}

GL_ACCOUNTS = {
    # balance sheet
    "0400": ("Fixed assets", "BS"),
    "0900": ("Assets under construction", "BS"),
    "1100": ("Trade receivables", "BS"),
    "1200": ("Bank", "BS"),
    "1400": ("Intercompany receivables", "BS"),
    "1990": ("Suspense account", "BS"),
    "2900": ("Equity", "BS"),
    "3300": ("Trade payables", "BS"),
    "3310": ("GR/IR clearing", "BS"),
    "3400": ("Intercompany payables", "BS"),
    "3700": ("Payroll liabilities", "BS"),
    "3900": ("Accrued liabilities", "BS"),
    # profit and loss
    "4000": ("Revenue sugarbeet seed", "REV"),
    "4010": ("Revenue corn seed", "REV"),
    "4020": ("Revenue cereal seed", "REV"),
    "4030": ("Revenue vegetable seed", "REV"),
    "4800": ("Intercompany service income", "REV_IC"),
    "5000": ("Materials and seed stock", "EXP"),
    "6000": ("Personnel expenses", "EXP"),
    "6200": ("Depreciation", "EXP"),
    "6400": ("Travel", "EXP"),
    "6500": ("External services", "EXP"),
    "6600": ("Rent and facilities", "EXP"),
    "6700": ("IT and software", "EXP"),
    "6800": ("Energy", "EXP"),
    "6900": ("Other operating expenses", "EXP"),
    "6950": ("Intercompany service charges", "EXP_IC"),
}

ACCOUNT_GROUPS = {
    "5000": "Materials", "6000": "Personnel", "6200": "Depreciation", "6400": "Travel",
    "6500": "External services", "6600": "Rent and facilities", "6700": "IT and software",
    "6800": "Energy", "6900": "Other", "6950": "Intercompany charges",
}

# Share of a cost center's non-personnel base by account, per functional area.
COST_MIX = {
    "COS": {"5000": 0.58, "6200": 0.14, "6500": 0.07, "6600": 0.05, "6700": 0.02, "6800": 0.12, "6900": 0.02},
    "SEL": {"6400": 0.18, "6500": 0.52, "6600": 0.10, "6700": 0.08, "6900": 0.12},
    "RND": {"5000": 0.20, "6200": 0.16, "6400": 0.06, "6500": 0.24, "6600": 0.12, "6700": 0.07, "6800": 0.10, "6900": 0.05},
    "GNA": {"6400": 0.05, "6500": 0.35, "6600": 0.20, "6700": 0.30, "6900": 0.10},
}

# Calendar-month seasonality (index 1..12, mean 1.0).
SEASON = {
    "COS": [1.05, 0.85, 0.80, 0.80, 0.85, 0.80, 0.85, 1.05, 1.45, 1.45, 1.25, 0.85],  # harvest and processing Sep-Nov
    "SEL": [0.95, 1.25, 1.30, 1.15, 0.95, 0.80, 0.70, 0.80, 1.05, 1.05, 1.00, 1.00],  # campaign before spring sowing
    "RND": [0.95, 0.95, 1.00, 1.15, 1.20, 1.15, 1.00, 0.95, 1.00, 0.90, 0.90, 0.85],  # field season
    "GNA": [1.00, 1.00, 1.00, 1.00, 1.00, 1.00, 1.00, 1.00, 1.00, 1.00, 1.00, 1.00],
}
FLAT_ACCOUNTS = {"6200", "6600"}   # depreciation and rent do not follow the season
THIRTEENTH_SALARY_MONTH = 11       # Weihnachtsgeld: half a monthly salary on top in November
ANNUAL_PAY_RAISE = 0.035           # applied every July
NON_PERSONNEL_INFLATION = 0.025    # per fiscal year

CROPS = {
    # crop: (revenue account, unit, list price EUR/unit FY 2024/25, annual units for the group)
    "sugarbeet": ("4000", "seed unit", 255.0, 330_000),
    "corn": ("4010", "seed unit", 96.0, 640_000),
    "cereals": ("4020", "dt", 62.0, 520_000),
    "vegetables": ("4030", "kg", 410.0, 36_000),
}
CROP_SEASON = {
    "sugarbeet": [3.6, 3.9, 2.4, 0.5, 0.1, 0.1, 0.1, 0.1, 0.1, 0.2, 0.3, 0.6],
    "corn":      [0.4, 1.8, 3.2, 3.4, 1.6, 0.2, 0.1, 0.1, 0.2, 0.3, 0.3, 0.4],
    "cereals":   [0.2, 0.6, 1.0, 0.4, 0.1, 0.1, 0.5, 2.6, 3.4, 2.2, 0.6, 0.3],
    "vegetables": [1.0, 1.2, 1.3, 1.2, 1.0, 0.9, 0.9, 0.9, 0.9, 0.9, 0.9, 0.9],
}

# Intercompany service charges billed monthly by DE10 (EUR).
IC_CHARGES = {"AT10": {"management fee": 46_000, "IT recharge": 18_400},
              "FR10": {"management fee": 71_000, "IT recharge": 27_600}}

# Capital projects: WBS element -> (entity, description, approved budget EUR, start period, end period)
CAPEX_PROJECTS = {
    "P-25-010": ("DE10", "Seed drying plant extension", 2_400_000, "2024-09", "2026-08"),
    "P-26-001": ("DE10", "New seed processing line", 4_200_000, "2025-10", "2027-06"),
    "P-26-002": ("FR10", "Greenhouse complex Chartres", 1_800_000, "2026-01", "2027-03"),
    "P-26-003": ("DE10", "Biotech lab equipment", 900_000, "2026-04", "2027-02"),
    "P-26-004": ("DE10", "ERP S/4 upgrade", 1_500_000, "2026-07", "2027-12"),
}
CAPEX_OVERRUN_LIMIT = 1.10   # actual + open commitments above 110% of budget needs a supplement request

# What actually happened in FY 2026/27 so far, against budget (the story the analysis must find).
ACTUAL_DRIFT_FY27 = {
    "volume": {"sugarbeet": 1.00, "corn": 1.06, "cereals": 0.84, "vegetables": 1.02},  # dry autumn hurt cereals
    "price": {"sugarbeet": 0.97, "corn": 1.02, "cereals": 1.04, "vegetables": 1.00},
    "energy": 1.18,          # energy above plan in production
    "fte_hiring_delay": 0.94,  # R&D hiring behind plan
}

# Errors planted in the closing month. The close checks have to find every one.
PLANTED_CLOSE_ISSUES = {
    "unbalanced_document": {"entity": "DE10", "difference": 1_250.00},
    "blocked_cost_center": {"entity": "DE10", "cost_center": "4199", "amount": 8_900.00},
    "wrong_entity_cost_center": {"entity": "DE10", "cost_center": "2300", "amount": 12_400.00},
    "missing_cost_center": {"entity": "FR10", "account": "6500", "amount": 5_600.00},
    "duplicate_invoice": {"entity": "DE10", "vendor": "V0147", "reference": "RE-2026-08817", "amount": 42_350.00},
    "intercompany_gap": {"partner": "AT10", "charge": "IT recharge", "amount": 18_400.00},
    "missing_depreciation_run": {"entity": "AT10"},
    "missing_rent": {"cost_center": "2300"},
    "late_postings": {"count": 6},
    "suspense_balance": {"entity": "FR10", "amount": 7_800.00},
    "aged_grir": {"count": 4},
    "misallocated_journal": {"amount": 250_000.00, "booked_on": "3110", "belongs_to": "2110",
                             "text": "Corn launch campaign Q1 - agency invoice"},
    "capex_overrun": {"wbs": "P-26-002"},
}

VARIANCE_THRESHOLD_PCT = 0.10
VARIANCE_THRESHOLD_EUR = 25_000


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
    def powerbi(self) -> Path:
        return self.root / "powerbi"

    @property
    def sql(self) -> Path:
        return self.root / "sql"
