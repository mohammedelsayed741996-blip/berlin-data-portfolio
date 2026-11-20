"""Data validation across the planning tool, partner CRM, operations log and ticketing.

Network planning decisions are only as good as the data under them, so these checks run
before any KPI. Each returns the offending rows, so the issue log can show exactly what
to fix and who owns it.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import config as C
from .world import haversine

EUROPE = {"lat": (35.0, 72.0), "lon": (-11.0, 32.0)}


@dataclass
class Check:
    check_id: str
    name: str
    owner: str
    rows: pd.DataFrame
    action: str

    @property
    def status(self) -> str:
        return "PASS" if self.rows.empty else "FAIL"

    def summary(self) -> dict:
        ex = "" if self.rows.empty else "; ".join(str(v) for v in self.rows.iloc[0].values[:4])
        return {"check_id": self.check_id, "check": self.name, "status": self.status, "issues": len(self.rows),
                "example": ex, "owner": self.owner, "action": self.action if not self.rows.empty else ""}


def trip_key(trip_id: pd.Series) -> pd.DataFrame:
    """Split 'L010A-20250101-0800' into line, direction, date and departure time."""
    p = trip_id.str.extract(r"^(L\d{3})([AB])-(\d{8})-(\d{4})$")
    p.columns = ["line", "direction", "date", "dep"]
    p["date"] = pd.to_datetime(p["date"], format="%Y%m%d").dt.strftime("%Y-%m-%d")
    p["dep_time"] = p["dep"].str[:2] + ":" + p["dep"].str[2:]
    return p.drop(columns="dep")


def check_coordinates(t) -> Check:
    s = t["stops"]
    bad = s[~s["lat"].between(*EUROPE["lat"]) | ~s["lon"].between(*EUROPE["lon"])]
    return Check("V01", "Stop coordinates lie in Europe", "Network data", bad[["stop_id", "stop_name", "lat", "lon"]],
                 "Correct the coordinates in the planning tool (latitude and longitude look swapped)")


def check_duplicate_stops(t, max_km: float = 1.0) -> Check:
    s = t["stops"]
    rows = []
    for i in range(len(s)):
        for j in range(i + 1, len(s)):
            a, b = s.iloc[i], s.iloc[j]
            d = haversine((a["lat"], a["lon"]), (b["lat"], b["lon"]))
            if d < max_km:
                rows.append({"stop_a": a["stop_id"], "name_a": a["stop_name"], "stop_b": b["stop_id"], "name_b": b["stop_name"],
                             "distance_km": round(d, 2)})
    used = t["line_stops"]
    out = pd.DataFrame(rows)
    if not out.empty:
        out["lines_using_b"] = [", ".join(used.loc[used["stop_id"] == b, "line"]) for b in out["stop_b"]]
    return Check("V02", "No duplicate stops (two records within 1 km)", "Network data", out,
                 "Merge the duplicate into the main stop and re-point the lines that use it")


def check_unlogged_trips(t) -> Check:
    b = t["bookings"]
    key = trip_key(b["trip_id"])
    tt = t["timetable"][["line", "direction", "dep_time"]].assign(planned=True)
    valid = b[key.merge(tt, on=["line", "direction", "dep_time"], how="left")["planned"].fillna(False).values]
    missing = valid[~valid["trip_id"].isin(t["operations"]["trip_id"]) & (valid["pax"] > 0)]
    return Check("V03", "Every trip with passengers is in the operations log", "Operations / partner management",
                 missing[["trip_id", "pax", "revenue_eur"]],
                 "Ask the partners for the missing trip records; partner payments are based on the log")


def check_orphan_bookings(t) -> Check:
    b = t["bookings"]
    key = trip_key(b["trip_id"])
    tt = t["timetable"][["line", "direction", "dep_time"]].assign(planned=True)
    m = key.merge(tt, on=["line", "direction", "dep_time"], how="left")["planned"].isna().values
    return Check("V04", "Every booking belongs to a timetabled departure", "Ticketing / data",
                 b[m][["trip_id", "pax", "revenue_eur"]],
                 "Find the source of the departures that are not in the timetable and fix the ticketing mapping")


def check_capacity(t) -> Check:
    ops = t["operations"]
    b = t["bookings"]
    planned = t["timetable"][["line", "direction", "dep_time", "bus_type_planned"]]
    o = ops.merge(planned, on=["line", "direction", "dep_time"]).merge(b[["trip_id", "peak_load"]], on="trip_id")
    o["sold_seats"] = o["bus_type_planned"].map(C.BUS_TYPES)
    bad = o[(o["sold_seats"] != o["seats"]) & (o["status"] == "operated")]
    over = bad[bad["peak_load"] > bad["seats"]]
    out = bad.groupby(["line", "partner_id", "bus_type_planned", "bus_type"]).agg(
        trips=("trip_id", "size"), overbooked_trips=("peak_load", lambda s: int((s > bad.loc[s.index, "seats"]).sum())),
        max_overbooked_seats=("peak_load", lambda s: int((s - bad.loc[s.index, "seats"]).max()))).reset_index()
    out.attrs["overbooked"] = over
    return Check("V05", "Bus used matches the bus sold in ticketing", "Network planning / partner management", out,
                 "Either sell single-decker capacity on this line or get the partner to run double-deckers")


def check_contracts(t) -> Check:
    ops = t["operations"]
    p = t["partners"]
    o = ops.merge(p[["partner_id", "contract_status", "contract_end"]], on="partner_id")
    bad = o[(o["date"] > o["contract_end"]) & (o["status"] == "operated")]
    out = bad.groupby(["partner_id", "contract_end"]).agg(trips_after_end=("trip_id", "size"),
                                                          first=("date", "min"), last=("date", "max")).reset_index()
    return Check("V06", "Partners operate only under a valid contract", "Partner management", out,
                 "Renew the contract in the CRM or move the lines to another partner")


def check_cancelled_with_pax(t) -> Check:
    ops = t["operations"]
    b = t["bookings"]
    o = ops[ops["status"] == "cancelled"].merge(b, on="trip_id")
    return Check("V07", "Cancelled trips carry no passengers", "Operations", o[o["pax"] > 0][["trip_id", "pax"]],
                 "Check refunds and rebookings for these trips")


def check_od_reconciliation(t) -> Check:
    b = t["bookings"]
    key = trip_key(b["trip_id"])
    bm = b.assign(month=key["date"].str[:7], line=key["line"]).groupby(["month", "line"])["pax"].sum()
    od = t["od_monthly"].groupby(["month", "line"])["pax"].sum()
    diff = (bm - od).fillna(0)
    out = diff[diff != 0].rename("difference_pax").reset_index()
    return Check("V08", "Trip bookings agree with origin-destination totals", "Ticketing / data", out,
                 "The difference equals the orphan bookings in V04; fix those and re-run")


ALL = [check_coordinates, check_duplicate_stops, check_unlogged_trips, check_orphan_bookings, check_capacity,
       check_contracts, check_cancelled_with_pax, check_od_reconciliation]


def run_all(t) -> list[Check]:
    return [c(t) for c in ALL]


def issue_log(checks: list[Check]) -> pd.DataFrame:
    return pd.DataFrame([c.summary() for c in checks])


def clean_trips(t) -> pd.DataFrame:
    """The analysis table: bookings for timetabled departures, joined to the operations log where it exists.
    Capacity is what actually ran; trips missing from the log keep their bookings and planned bus."""
    b = t["bookings"]
    key = trip_key(b["trip_id"])
    b = pd.concat([b, key], axis=1)
    tt = t["timetable"]
    b = b.merge(tt, on=["line", "direction", "dep_time"], how="inner")
    o = t["operations"][["trip_id", "status", "seats", "delay_min"]]
    b = b.merge(o, on="trip_id", how="left")
    b["status"] = b["status"].fillna("operated (not logged)")
    b["seats"] = b["seats"].fillna(b["bus_type_planned"].map(C.BUS_TYPES))
    km = {}
    from .world import road_km
    for line, seq in C.LINES.items():
        km[line] = sum(road_km(seq[i], seq[i + 1]) for i in range(len(seq) - 1))
    b["line_km"] = b["line"].map(km)
    b["seat_km"] = b["seats"] * b["line_km"]
    b["bus_cost_eur"] = b["line_km"] * C.COST_PER_BUS_KM
    b["month"] = b["date"].str[:7]
    b = b[b["status"] != "cancelled"]
    return b.reset_index(drop=True)
