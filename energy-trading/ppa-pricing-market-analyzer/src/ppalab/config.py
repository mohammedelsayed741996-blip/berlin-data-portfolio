"""Paths, seed and the assumptions of the synthetic German power market.

The market is simulated, not downloaded: prices come from a simple merit-order model driven by gas and
carbon prices, demand, and growing solar and wind capacity. The shape is realistic (seasons, evening peaks,
solar cannibalisation, negative prices, the 2022 crisis); the numbers are not real exchange data.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
OUTPUTS = ROOT / "outputs"
FIGURES = OUTPUTS / "figures"
SEED = 20261125

START, END = "2019-01-01", "2026-10-31 23:00"   # hourly history, Europe/Berlin local time without DST handling
AS_OF = "2026-11-02"                              # pricing date for forward curves and offers

# Installed capacity in GW at the start of each year (interpolated within the year)
SOLAR_GW = {2019: 49, 2020: 54, 2021: 59, 2022: 66, 2023: 81, 2024: 97, 2025: 112, 2026: 125, 2027: 140}
WIND_GW = {2019: 60, 2020: 61, 2021: 63, 2022: 64, 2023: 67, 2024: 71, 2025: 75, 2026: 80, 2027: 85}

BALANCING_EUR_MWH = {"solar": 1.6, "wind": 2.8}  # forecast-error balancing cost borne by the offtaker's balancing group
RISK_LAMBDA = 0.5                                 # premium per unit of standard deviation of the PPA value (EUR/MWh)
# A new plant yields more than the fleet average (better modules, trackers, taller turbines): about 940 and 1,930 full-load hours
ASSET_YIELD = {"solar": 1.35, "wind": 1.15}
