"""Synthetic network, timetable, partners and 33 months of operated trips and bookings.

The data comes out of four "systems", the way a planning team meets it:

    planning tool   stops, line_stops, timetable
    partner CRM     partners (a Salesforce-style account export)
    operations log  operations (one row per trip run, with the bus actually used)
    ticketing       bookings (per trip) and od_monthly (per origin-destination and month)

Demand follows a gravity model (bigger cities, shorter distance, more passengers) with
seasons, weekdays, holidays, growth that differs by line, and noise. Buses have finite
seats, so busy departures sell out and the extra demand is lost. That lost demand is kept
in a separate truth file for validation only; the analysis has to work from what the
systems record. A handful of data problems are planted in the systems (config.PLANTED).
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from . import config as C

HOLIDAYS = ["12-23", "12-24", "12-26", "12-27", "12-30", "01-02", "10-03", "05-01"]
EASTER = {2024: "2024-03-29", 2025: "2025-04-18", 2026: "2026-04-03"}


def haversine(a, b) -> float:
    (la1, lo1), (la2, lo2) = a, b
    p1, p2 = math.radians(la1), math.radians(la2)
    dp, dl = p2 - p1, math.radians(lo2 - lo1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


def road_km(c1: str, c2: str) -> float:
    a, b = C.CITIES[c1], C.CITIES[c2]
    return round(haversine(a[:2], b[:2]) * C.ROAD_FACTOR, 1)


def gravity(c1: str, c2: str) -> float:
    """Daily bus passengers between two cities, one direction, before seasons and noise."""
    p1, p2 = C.CITIES[c1][2], C.CITIES[c2][2]
    d = road_km(c1, c2)
    border = 0.75 if C.CITIES[c1][3] != C.CITIES[c2][3] else 1.0
    return 0.0042 * (p1 ** 0.72) * (p2 ** 0.72) / ((d / 100) ** 1.15) * border


def make_stops() -> pd.DataFrame:
    rows = []
    for i, (city, (lat, lon, pop, cc)) in enumerate(C.CITIES.items(), start=1):
        rows.append({"stop_id": f"S{i:02d}", "city": city, "stop_name": f"{city} central bus station", "country": cc,
                     "lat": lat, "lon": lon})
    s = pd.DataFrame(rows)
    city = C.PLANTED["swapped_coordinates_stop"]
    m = s["city"] == city
    s.loc[m, ["lat", "lon"]] = s.loc[m, ["lon", "lat"]].values                 # planted: lat and lon swapped
    base, dup_name = C.PLANTED["duplicate_stop"]
    b = s[s["city"] == base].iloc[0]
    s.loc[len(s)] = {"stop_id": "S99", "city": base, "stop_name": dup_name, "country": b["country"],
                     "lat": b["lat"] + 0.002, "lon": b["lon"] - 0.003}            # planted: same stop entered twice
    return s


def line_stops(stops: pd.DataFrame) -> pd.DataFrame:
    sid = {c: stops[stops["city"] == c]["stop_id"].iloc[0] for c in C.CITIES}
    rows = []
    for line, seq in C.LINES.items():
        for k, city in enumerate(seq):
            stop = sid[city]
            if line == "L031" and city == C.PLANTED["duplicate_stop"][0]:
                stop = "S99"                                                     # the duplicate is used by one line
            rows.append({"line": line, "seq": k + 1, "stop_id": stop, "city": city})
    return pd.DataFrame(rows)


def make_partners(rng) -> pd.DataFrame:
    names = ["Nordwind Reisen", "Elbtal Bus", "Alpenlinie", "Rheinland Touristik", "Ostsee Express",
             "Mainfranken Mobil", "Weichsel Coach", "Schwarzwald Reisen", "Hansa Fernbus"]
    depots = ["Hamburg", "Dresden", "Munich", "Cologne", "Rostock", "Nuremberg", "Berlin", "Freiburg", "Bremen"]
    rows = []
    for i, (n, d) in enumerate(zip(names, depots), start=1):
        pid = f"P{i:02d}"
        rows.append({"partner_id": pid, "partner_name": f"{n} GmbH (fictional)", "home_depot": d,
                     "contract_status": "active", "contract_end": "2027-12-31",
                     "fleet_single": int(rng.integers(8, 20)), "fleet_double": int(rng.integers(3, 10)),
                     "account_owner": "Partner Manager North" if i <= 5 else "Partner Manager South"})
    p = pd.DataFrame(rows)
    p.loc[p["partner_id"] == C.PLANTED["expired_contract_partner"], ["contract_status", "contract_end"]] = ["expired", C.PLANTED["expired_on"]]
    return p


LINE_PARTNER = {"L010": "P07", "L011": "P02", "L012": "P01", "L013": "P05", "L014": "P07", "L015": "P09",
                "L016": "P07", "L017": "P02", "L020": "P09", "L021": "P01", "L022": "P05", "L023": "P01",
                "L030": "P03", "L031": "P03", "L032": "P06", "L033": "P03", "L040": "P04", "L041": "P04",
                "L042": "P04", "L043": "P06", "L044": "P08", "L045": "P02"}
LINE_TREND = {"L016": 0.16, "L013": 0.12, "L022": 0.10, "L011": 0.09, "L023": -0.06, "L041": -0.04, "L045": -0.02}


def segment_flows(seq: list[str]) -> list[tuple[int, int, float, float]]:
    """(origin index, destination index, base daily demand, km) for each OD pair along one direction."""
    out = []
    for i in range(len(seq)):
        for j in range(i + 1, len(seq)):
            km = sum(road_km(seq[k], seq[k + 1]) for k in range(i, j))
            out.append((i, j, gravity(seq[i], seq[j]), km))
    return out


def make_timetable(rng) -> pd.DataFrame:
    rows = []
    for line, seq in C.LINES.items():
        for direction, s in (("A", seq), ("B", seq[::-1])):
            flows = segment_flows(s)
            seg = np.zeros(len(s) - 1)
            for i, j, d, _ in flows:
                seg[i:j] += d
            peak = seg.max() * 1.05
            f = int(np.clip(round(peak / 48), 1, 8))
            order = np.argsort(C.SLOT_WEIGHT)[::-1][:f]
            per_dep = peak / f
            bus = "double" if per_dep > 50 else "single"
            if line == C.PLANTED["capacity_mismatch_line"]:
                bus = "double"
            for slot in sorted(order):
                rows.append({"line": line, "direction": direction, "dep_time": C.DEPARTURE_SLOTS[slot],
                             "bus_type_planned": bus, "partner_id": LINE_PARTNER[line],
                             "origin": s[0], "destination": s[-1]})
    return pd.DataFrame(rows)


def day_factors(dates: pd.DatetimeIndex) -> np.ndarray:
    f = np.array([C.MONTH_FACTOR[d.month - 1] * C.WEEKDAY_FACTOR[d.weekday()] for d in dates])
    md = dates.strftime("%m-%d")
    f = f * np.where(np.isin(md, HOLIDAYS), 1.35, 1.0)
    for y, e in EASTER.items():
        e = pd.Timestamp(e)
        f = f * np.where((dates >= e - pd.Timedelta(days=1)) & (dates <= e + pd.Timedelta(days=3)), 1.3, 1.0)
    return f


def simulate(rng) -> dict[str, pd.DataFrame]:
    stops = make_stops()
    ls = line_stops(stops)
    partners = make_partners(rng)
    tt = make_timetable(rng)
    dates = pd.date_range(C.START, C.END, freq="D")
    nd = len(dates)
    years = np.asarray((dates - pd.Timestamp(C.START)).days / 365.25)
    base_f = day_factors(dates)
    trips, truth, od_rows = [], [], []
    for (line, direction), g in tt.groupby(["line", "direction"], sort=True):
        seq = C.LINES[line] if direction == "A" else C.LINES[line][::-1]
        flows = segment_flows(seq)
        growth = (1 + C.ANNUAL_GROWTH + LINE_TREND.get(line, 0.0)) ** years
        slots = [C.DEPARTURE_SLOTS.index(t) for t in g["dep_time"]]
        w = np.array([C.SLOT_WEIGHT[s] for s in slots])
        share = w / w.sum()
        planned = g["bus_type_planned"].iloc[0]
        sell_cap = C.BUS_TYPES[planned]
        real_cap = np.full(nd, sell_cap)
        if line == C.PLANTED["capacity_mismatch_line"]:
            # the partner switched this line to single-deckers in April 2026; ticketing kept selling 79 seats
            real_cap = np.where(dates >= pd.Timestamp(C.PLANTED["capacity_mismatch_from"]), C.BUS_TYPES["single"], sell_cap)
        line_noise = rng.lognormal(0, 0.10, nd)                       # shared day-level shock for the line
        od_month = {}
        for k, (dep, slot_share) in enumerate(zip(g["dep_time"], share)):
            demand = np.zeros((nd, len(flows)))
            for p, (i, j, d, km) in enumerate(flows):
                demand[:, p] = d * slot_share * base_f * growth * line_noise * rng.lognormal(0, 0.22, nd)
            # segment loads and capacity: scale every OD that crosses an over-full segment
            seg_load = np.zeros((nd, len(seq) - 1))
            for p, (i, j, d, km) in enumerate(flows):
                seg_load[:, i:j] += demand[:, [p]]
            peak = seg_load.max(axis=1)
            scale = np.minimum(1.0, sell_cap / np.maximum(peak, 1e-9))
            # round to whole passengers; where rounding up would overfill a segment, round down instead
            boarded = np.floor(demand * scale[:, None] + rng.random(demand.shape))
            over = np.zeros(nd, dtype=bool)
            for i in range(len(seq) - 1):
                cross = [p for p, f in enumerate(flows) if f[0] <= i < f[1]]
                over |= boarded[:, cross].sum(axis=1) > sell_cap
            boarded[over] = np.floor(demand[over] * scale[over, None])
            seg_b = np.zeros_like(seg_load)
            for p, (i, j, d, km) in enumerate(flows):
                seg_b[:, i:j] += boarded[:, [p]]
            kms = np.array([f[3] for f in flows])
            pax = boarded.sum(axis=1)
            pax_km = (boarded * kms).sum(axis=1)
            load_ratio = seg_b.max(axis=1) / sell_cap
            price_km = 0.062 * (0.85 + 0.45 * np.clip(load_ratio, 0, 1))      # fuller buses sell dearer seats
            revenue = (boarded * kms).sum(axis=1) * price_km
            cancelled = rng.random(nd) < 0.008
            pax[cancelled] = 0
            pax_km[cancelled] = 0
            revenue[cancelled] = 0
            seg_b[cancelled] = 0
            line_km = sum(road_km(seq[x], seq[x + 1]) for x in range(len(seq) - 1))
            ids = [f"{line}{direction}-{d:%Y%m%d}-{dep.replace(':', '')}" for d in dates]
            trips.append(pd.DataFrame({
                "trip_id": ids, "date": dates.strftime("%Y-%m-%d"), "line": line, "direction": direction, "dep_time": dep,
                "partner_id": g["partner_id"].iloc[0], "bus_type_planned": planned, "sell_capacity": sell_cap,
                "actual_capacity": real_cap, "status": np.where(cancelled, "cancelled", "operated"),
                "line_km": line_km, "pax": pax.astype(int), "pax_km": pax_km.round(1),
                "peak_load": seg_b.max(axis=1).astype(int), "peak_segment": [f"{seq[s]}-{seq[s + 1]}" for s in seg_b.argmax(axis=1)],
                "revenue_eur": revenue.round(2), "sold_out": (peak >= sell_cap) & ~cancelled,
                "delay_min": np.where(cancelled, np.nan, np.round(rng.gamma(1.2, 6, nd))),
            }))
            truth.append(pd.DataFrame({"trip_id": ids, "unconstrained_pax": np.where(cancelled, 0, demand.sum(axis=1)).round(1),
                                       "unconstrained_peak": np.where(cancelled, 0, peak).round(1)}))
            months = dates.strftime("%Y-%m")
            for p, (i, j, d, km) in enumerate(flows):
                s = pd.Series(np.where(cancelled, 0, boarded[:, p])).groupby(months).sum()
                r = pd.Series(np.where(cancelled, 0, boarded[:, p] * km * price_km)).groupby(months).sum()
                for m in s.index:
                    key = (m, seq[i], seq[j])
                    a = od_month.get(key, [0.0, 0.0, km])
                    od_month[key] = [a[0] + s[m], a[1] + r[m], km]
        for (m, o, d), (px, rev, km) in od_month.items():
            od_rows.append({"month": m, "line": line, "origin": o, "destination": d, "pax": int(px), "revenue_eur": round(rev, 2), "km": km})

    trips = pd.concat(trips, ignore_index=True).sort_values(["date", "dep_time", "line", "direction"]).reset_index(drop=True)
    truth = pd.concat(truth, ignore_index=True)
    ops_cols = ["trip_id", "date", "line", "direction", "dep_time", "partner_id", "bus_type_planned", "actual_capacity", "status", "delay_min"]
    operations = trips[ops_cols].rename(columns={"bus_type_planned": "bus_type"}).copy()
    operations["bus_type"] = np.where(operations["actual_capacity"] == C.BUS_TYPES["double"], "double", "single")
    operations = operations.rename(columns={"actual_capacity": "seats"})
    bookings = trips[["trip_id", "pax", "pax_km", "peak_load", "peak_segment", "revenue_eur", "sold_out"]].copy()

    # planted: trips that ran (bookings exist) but are missing from the operations log
    gone = operations[(operations["status"] == "operated") & (operations["date"] >= "2026-03-01")].sample(
        C.PLANTED["unlogged_trips"], random_state=int(rng.integers(1e9))).index
    operations = operations.drop(index=gone).reset_index(drop=True)
    # planted: booking records pointing at departures that are not in the timetable
    fake = bookings.sample(C.PLANTED["orphan_bookings"], random_state=int(rng.integers(1e9))).copy()
    fake["trip_id"] = [t.replace(t.split("-")[-1], "0545") for t in fake["trip_id"]]
    bookings = pd.concat([bookings, fake], ignore_index=True)

    return {"stops": stops, "line_stops": ls, "timetable": tt, "partners": partners, "operations": operations,
            "bookings": bookings, "od_monthly": pd.DataFrame(od_rows), "truth_demand": truth,
            "trips_full": trips}
