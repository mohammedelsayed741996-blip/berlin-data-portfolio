"""Paths, seed and the fictional company's reference data.

Havelwerk Grid Components is invented. It builds power transformers and switchgear in three plants and
buys copper, electrical steel, tank steel, insulation, oil, electronics and services. All names, IDs and
amounts are generated; no real supplier or person appears anywhere.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
RAW, MODEL = DATA / "raw", DATA / "model"
OUTPUTS = ROOT / "outputs"
FIGURES = OUTPUTS / "figures"
SEED = 20261122

START, END = date(2024, 11, 1), date(2026, 10, 31)       # purchasing history in the ERP exports
INDEX_START = date(2019, 1, 1)                            # commodity index history

PLANTS = {
    "DE10": {"name": "Berlin", "country": "DE", "system": "ERP_A"},
    "DE20": {"name": "Erfurt", "country": "DE", "system": "ERP_A"},
    "PL30": {"name": "Gdansk", "country": "PL", "system": "ERP_B"},
}

# Category -> commodity index the price follows (None = no index), share of price linked, lag in months
CATEGORIES = {
    "CU": {"name": "Copper conductors & windings", "index": "copper", "weight": 0.75, "lag": 1, "type": "direct"},
    "ES": {"name": "Electrical steel (GOES) cores", "index": "goes", "weight": 0.65, "lag": 2, "type": "direct"},
    "ST": {"name": "Tank & structural steel", "index": "steel_hrc", "weight": 0.55, "lag": 1, "type": "direct"},
    "AL": {"name": "Aluminium parts", "index": "aluminium", "weight": 0.6, "lag": 1, "type": "direct"},
    "OI": {"name": "Transformer oil", "index": "oil", "weight": 0.5, "lag": 1, "type": "direct"},
    "IN": {"name": "Insulation & bushings", "index": None, "weight": 0.0, "lag": 0, "type": "direct"},
    "EL": {"name": "Electronics & controls", "index": None, "weight": 0.0, "lag": 0, "type": "direct"},
    "LG": {"name": "Logistics & freight", "index": None, "weight": 0.0, "lag": 0, "type": "indirect"},
    "SV": {"name": "Services, IT & facility", "index": None, "weight": 0.0, "lag": 0, "type": "indirect"},
}

INDICES = {   # start level, annual drift, monthly volatility, seasonal amplitude (share)
    "copper": (5600.0, 0.07, 0.055, 0.015),        # EUR per tonne
    "aluminium": (1700.0, 0.04, 0.05, 0.02),
    "steel_hrc": (480.0, 0.03, 0.065, 0.04),
    "goes": (2100.0, 0.05, 0.045, 0.01),
    "oil": (850.0, 0.02, 0.07, 0.03),
}

COUNTRY_RISK = {"DE": 1, "AT": 1, "PL": 1, "CZ": 1, "SE": 1, "IT": 2, "ES": 2, "TR": 3, "CN": 3, "IN": 3, "KR": 2, "US": 1}
PLN_PER_EUR = 4.30
