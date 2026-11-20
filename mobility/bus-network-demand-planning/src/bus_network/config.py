"""Network, demand and planning settings for a fictional intercity bus operator.

City names and coordinates are public geography. Everything else is invented: the
operator, its lines and timetable, the partner bus companies, the bookings and every
number derived from them. No person appears anywhere in the data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

SEED = 20261120
START = "2024-01-01"
END = "2026-09-30"
PLAN_SEASON = ("2026-12-14", "2027-03-31")    # winter timetable to plan
BACKTEST_SEASON = ("2025-12-14", "2026-03-31")  # same season one year earlier, for the forecast backtest

# city: (lat, lon, population in thousands, country)
CITIES = {
    "Berlin": (52.52, 13.40, 3_780, "DE"), "Hamburg": (53.55, 10.00, 1_910, "DE"), "Munich": (48.14, 11.58, 1_510, "DE"),
    "Cologne": (50.94, 6.96, 1_080, "DE"), "Frankfurt": (50.11, 8.68, 775, "DE"), "Stuttgart": (48.78, 9.18, 630, "DE"),
    "Duesseldorf": (51.23, 6.77, 630, "DE"), "Leipzig": (51.34, 12.37, 620, "DE"), "Dortmund": (51.51, 7.47, 595, "DE"),
    "Bremen": (53.08, 8.80, 570, "DE"), "Dresden": (51.05, 13.74, 565, "DE"), "Hanover": (52.38, 9.73, 545, "DE"),
    "Nuremberg": (49.45, 11.08, 525, "DE"), "Muenster": (51.96, 7.63, 320, "DE"), "Karlsruhe": (49.01, 8.40, 310, "DE"),
    "Mannheim": (49.49, 8.47, 315, "DE"), "Freiburg": (47.99, 7.85, 235, "DE"), "Kiel": (54.32, 10.14, 250, "DE"),
    "Rostock": (54.09, 12.10, 210, "DE"), "Erfurt": (50.98, 11.03, 215, "DE"), "Kassel": (51.31, 9.48, 200, "DE"),
    "Goettingen": (51.54, 9.93, 118, "DE"), "Wuerzburg": (49.79, 9.95, 128, "DE"), "Regensburg": (49.01, 12.10, 155, "DE"),
    "Aachen": (50.78, 6.08, 250, "DE"), "Magdeburg": (52.12, 11.63, 240, "DE"),
    "Prague": (50.08, 14.44, 1_360, "CZ"), "Vienna": (48.21, 16.37, 2_000, "AT"), "Amsterdam": (52.37, 4.90, 930, "NL"),
    "Copenhagen": (55.68, 12.57, 660, "DK"), "Warsaw": (52.23, 21.01, 1_860, "PL"), "Zurich": (47.38, 8.54, 440, "CH"),
}

# line id: stop sequence (served in both directions)
LINES = {
    "L010": ["Berlin", "Leipzig", "Nuremberg", "Munich"],
    "L011": ["Berlin", "Dresden", "Prague", "Vienna"],
    "L012": ["Berlin", "Hamburg", "Kiel"],
    "L013": ["Berlin", "Rostock", "Copenhagen"],
    "L014": ["Berlin", "Hanover", "Dortmund", "Cologne"],
    "L015": ["Berlin", "Magdeburg", "Hanover", "Bremen"],
    "L016": ["Berlin", "Warsaw"],
    "L017": ["Berlin", "Erfurt", "Frankfurt"],
    "L020": ["Hamburg", "Bremen", "Muenster", "Dortmund", "Cologne"],
    "L021": ["Hamburg", "Hanover", "Kassel", "Frankfurt"],
    "L022": ["Hamburg", "Copenhagen"],
    "L023": ["Hamburg", "Amsterdam"],
    "L030": ["Munich", "Stuttgart", "Karlsruhe", "Frankfurt"],
    "L031": ["Munich", "Zurich"],
    "L032": ["Munich", "Regensburg", "Prague"],
    "L033": ["Munich", "Vienna"],
    "L040": ["Cologne", "Duesseldorf", "Amsterdam"],
    "L041": ["Cologne", "Aachen", "Amsterdam"],
    "L042": ["Cologne", "Frankfurt", "Mannheim", "Stuttgart"],
    "L043": ["Frankfurt", "Wuerzburg", "Nuremberg", "Regensburg"],
    "L044": ["Frankfurt", "Karlsruhe", "Freiburg", "Zurich"],
    "L045": ["Leipzig", "Goettingen", "Kassel", "Dortmund"],
}

BUS_TYPES = {"single": 49, "double": 79}
COST_PER_BUS_KM = 1.55            # EUR, paid to the partner
DRIVE_SPEED_KMH = 72              # average including stops, for bus-hours
ROAD_FACTOR = 1.22                # road distance / straight-line distance

DEPARTURE_SLOTS = ["06:30", "08:00", "10:00", "12:30", "15:00", "17:30", "20:00", "23:00"]
SLOT_WEIGHT = [0.10, 0.17, 0.15, 0.12, 0.14, 0.15, 0.10, 0.07]   # time-of-day preference
WEEKDAY_FACTOR = [0.85, 0.80, 0.85, 0.95, 1.30, 1.05, 1.25]       # Mon..Sun
MONTH_FACTOR = [0.72, 0.70, 0.85, 1.00, 1.05, 1.08, 1.30, 1.32, 1.02, 1.00, 0.88, 1.10]
ANNUAL_GROWTH = 0.06

PARTNERS = 9

# Planted data problems the validation has to find
PLANTED = {
    "swapped_coordinates_stop": "Regensburg",
    "duplicate_stop": ("Munich", "Muenchen ZOB"),
    "expired_contract_partner": "P07",
    "expired_on": "2026-06-30",
    "capacity_mismatch_line": "L017",      # sold as double-decker, partner runs single-deckers
    "capacity_mismatch_from": "2026-04-01",
    "unlogged_trips": 140,                 # planned trips with no operations record
    "orphan_bookings": 60,                 # booking records with no matching trip
}


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
