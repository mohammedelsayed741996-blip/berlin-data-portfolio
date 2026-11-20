"""Maps, charts, the Excel planning report and the GeoJSON / HTML network map."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402
from openpyxl import Workbook  # noqa: E402
from openpyxl.formatting.rule import CellIsRule, ColorScaleRule  # noqa: E402
from openpyxl.styles import Alignment, Font, PatternFill  # noqa: E402

from . import config as C  # noqa: E402

SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
TEXT_PRIMARY, TEXT_SECONDARY, GRID, SURFACE, NEUTRAL = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb", "#9b9a95"
LOAD_CMAP = LinearSegmentedColormap.from_list("load", ["#cfe0f5", "#2a78d6", "#0b3d7a"])


def _style(ax, title, subtitle="", grid_axis="y"):
    ax.set_facecolor(SURFACE)
    ax.figure.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=TEXT_SECONDARY, labelsize=9)
    if grid_axis:
        ax.grid(axis=grid_axis, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.set_title(title, loc="left", fontsize=12, color=TEXT_PRIMARY, pad=22 if subtitle else 8, fontweight="bold")
    if subtitle:
        ax.text(0, 1.02, subtitle, transform=ax.transAxes, fontsize=9, color=TEXT_SECONDARY)


def _save(fig, path: Path) -> Path:
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def _xy(city):
    lat, lon = C.CITIES[city][:2]
    return lon * np.cos(np.radians(51)), lat


def plot_network_map(G, gaps: pd.DataFrame, path: Path, n_gaps: int = 5) -> Path:
    """Schematic map: segment width = average passengers on board, colour = seat use; dashed = demand gaps."""
    fig, ax = plt.subplots(figsize=(8.5, 8.5))
    loads = []
    for a, b, d in G.edges(data=True):
        trips = d["seats"] / 60 if d["seats"] else 1
        loads.append(d["pax_proxy"])
    lmax = max(loads)
    for a, b, d in G.edges(data=True):
        (x1, y1), (x2, y2) = _xy(a), _xy(b)
        w = 1 + 9 * d["pax_proxy"] / lmax
        ax.plot([x1, x2], [y1, y2], color=LOAD_CMAP(0.25 + 0.75 * d["pax_proxy"] / lmax), linewidth=w, solid_capstyle="round", zorder=2)
    for r in gaps.head(n_gaps).itertuples():
        (x1, y1), (x2, y2) = _xy(r.origin), _xy(r.destination)
        ax.plot([x1, x2], [y1, y2], color=SERIES[1], linewidth=1.8, linestyle=(0, (4, 3)), zorder=1)
    for city, (lat, lon, pop, cc) in C.CITIES.items():
        x, y = _xy(city)
        ax.scatter(x, y, s=12 + pop / 40, color=SURFACE, edgecolor=TEXT_PRIMARY, linewidth=1.2, zorder=3)
        ax.text(x + 0.12, y + 0.08, city, fontsize=7.5, color=TEXT_SECONDARY, zorder=4)
    ax.plot([], [], color=LOAD_CMAP(0.9), linewidth=6, label="Busy segment (width = passengers on board)")
    ax.plot([], [], color=SERIES[1], linewidth=1.8, linestyle=(0, (4, 3)), label="Demand gap: no direct line yet")
    ax.legend(frameon=False, fontsize=8.5, labelcolor=TEXT_SECONDARY, loc="upper left")
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)
    _style(ax, "Network, October 2025 to September 2026", "Schematic, projected from city coordinates", grid_axis="")
    return _save(fig, path)


def plot_line_matrix(k: pd.DataFrame, path: Path) -> Path:
    """Each line as a dot: seat use vs share of sold-out departures. Top right needs more seats, bottom left fewer."""
    fig, ax = plt.subplots(figsize=(8.5, 5.2))
    col = np.where(k["contribution_margin"] < 0, SERIES[7], SERIES[0])
    ax.scatter(k["load_factor"] * 100, k["sold_out_share"] * 100, s=40 + k["pax"] / 1200, color=col, alpha=0.85, edgecolor=SURFACE, linewidth=1.5)
    for r in k.itertuples():
        ax.text(r.load_factor * 100 + 0.8, r.sold_out_share * 100 + 0.6, r.line, fontsize=8, color=TEXT_SECONDARY)
    ax.axvline(40, color=GRID, linestyle=(0, (4, 3)))
    ax.axhline(25, color=GRID, linestyle=(0, (4, 3)))
    ax.text(41, ax.get_ylim()[1] * 0.97, "too many seats\n(left of 40%)", fontsize=8, color=TEXT_SECONDARY, va="top")
    ax.text(ax.get_xlim()[1] * 0.99, 26, "too few seats (above 25% sold out)", fontsize=8, color=TEXT_SECONDARY, ha="right")
    ax.set_xlabel("Load factor (passenger-km / seat-km), %", color=TEXT_SECONDARY, fontsize=9)
    ax.set_ylabel("Departures sold out, %", color=TEXT_SECONDARY, fontsize=9)
    ax.scatter([], [], color=SERIES[7], label="Line loses money after bus costs")
    ax.scatter([], [], color=SERIES[0], label="Line covers its bus costs")
    ax.legend(frameon=False, fontsize=8.5, labelcolor=TEXT_SECONDARY, loc="lower right", bbox_to_anchor=(1, 0.08))
    _style(ax, "Line performance, last 12 months", "Dot size = passengers")
    return _save(fig, path)


def plot_plan(pt: pd.DataFrame, path: Path) -> Path:
    a = pt[pt["direction"] == "A"].copy()
    a = a.set_index("line")
    b = pt[pt["direction"] == "B"].set_index("line")
    for c in ["contribution_delta", "sold_out_now", "sold_out_plan"]:
        a[c] = (a[c] + b[c]) if c == "contribution_delta" else (a[c] + b[c]) / 2
    a = a[a["change"] == "change"].sort_values("contribution_delta")
    fig, ax = plt.subplots(figsize=(9, 4.6))
    y = np.arange(len(a))
    ax.barh(y, a["contribution_delta"] / 1000, color=np.where(a["contribution_delta"] >= 0, SERIES[0], SERIES[1]), height=0.6)
    for yi, (cur, new, s0, s1, v) in enumerate(zip(a["current"], a["proposed"], a["sold_out_now"], a["sold_out_plan"], a["contribution_delta"])):
        ax.text(v / 1000 + (2 if v >= 0 else -2), yi, f"{cur} → {new} | sold out {s0:.0%} → {s1:.0%}", va="center",
                ha="left" if v >= 0 else "right", fontsize=8, color=TEXT_SECONDARY)
    ax.set_yticks(y)
    ax.set_yticklabels(a.index, fontsize=9)
    ax.axvline(0, color=TEXT_SECONDARY, linewidth=0.8)
    lim = max(abs(a["contribution_delta"]).max() / 1000 * 2.1, 10)
    ax.set_xlim(-lim, lim)
    ax.set_xlabel("Change in contribution over the winter season, EUR thousand", color=TEXT_SECONDARY, fontsize=9)
    _style(ax, "Winter 2026/27: lines where the plan changes the offer", "Departures per day and direction x bus type; both directions combined", grid_axis="x")
    return _save(fig, path)


def plot_backtest(bt_weekly: pd.DataFrame, path: Path) -> Path:
    w = bt_weekly.groupby("week")[["unconstrained_pax", "pax", "pred", "naive"]].sum()
    w = w.iloc[1:-1]                                                   # drop the part weeks at the season edges
    fig, ax = plt.subplots(figsize=(9, 3.8))
    x = np.arange(len(w))
    ax.plot(x, w["unconstrained_pax"] / 1000, color=TEXT_PRIMARY, linewidth=2, label="True demand (synthetic truth)")
    ax.plot(x, w["pax"] / 1000, color=NEUTRAL, linewidth=2, label="Bookings (capped by seats)")
    ax.plot(x, w["pred"] / 1000, color=SERIES[0], linewidth=2, linestyle=(0, (4, 2)), label="Model forecast")
    ax.plot(x, w["naive"] / 1000, color=SERIES[1], linewidth=1.5, linestyle=(0, (1, 2)), label="Last year, same departure")
    ax.set_xticks(x[::3])
    ax.set_xticklabels(w.index[::3], fontsize=8)
    ax.set_ylabel("Passengers per week, thousand", color=TEXT_SECONDARY, fontsize=9)
    ax.legend(frameon=False, fontsize=8, labelcolor=TEXT_SECONDARY, ncol=2, loc="upper center", bbox_to_anchor=(0.5, -0.15))
    _style(ax, "Forecast backtest: winter 2025/26, whole network", "Model trained on data before 14 December 2025")
    return _save(fig, path)


# ---------------------------------------------------------------------------- GeoJSON and HTML map
def geojson(G, gaps: pd.DataFrame, path: Path) -> Path:
    feats = []
    for city, (lat, lon, pop, cc) in C.CITIES.items():
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]},
                      "properties": {"name": city, "population_k": pop, "country": cc, "marker-size": "small", "marker-color": "#1F3864"}})
    for a, b, d in G.edges(data=True):
        feats.append({"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[C.CITIES[a][1], C.CITIES[a][0]], [C.CITIES[b][1], C.CITIES[b][0]]]},
                      "properties": {"segment": f"{a} - {b}", "lines": ", ".join(d["lines"]), "avg_passengers_on_board": round(d["pax_proxy"], 1),
                                     "km": d["km"], "stroke": "#2a78d6", "stroke-width": round(1 + 8 * d["pax_proxy"] / 400, 1)}})
    for r in gaps.head(5).itertuples():
        feats.append({"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[C.CITIES[r.origin][1], C.CITIES[r.origin][0]], [C.CITIES[r.destination][1], C.CITIES[r.destination][0]]]},
                      "properties": {"demand_gap": f"{r.origin} - {r.destination}", "expected_pax_per_day_each_way": r.expected_pax_per_day_each_way,
                                     "stroke": "#eb6834", "stroke-width": 2}})
    path.write_text(json.dumps({"type": "FeatureCollection", "features": feats}, indent=1))
    return path


def html_map(geo_path: Path, path: Path) -> Path:
    data = geo_path.read_text()
    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Bus network map (synthetic data)</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>html,body,#map{{height:100%;margin:0;font-family:system-ui,sans-serif}}</style></head>
<body><div id="map"></div><script>
const data = {data};
const map = L.map('map').setView([51.0, 10.5], 6);
L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{attribution: '&copy; OpenStreetMap contributors'}}).addTo(map);
L.geoJSON(data, {{
  style: f => ({{color: f.properties.stroke || '#2a78d6', weight: f.properties['stroke-width'] || 2,
                dashArray: f.properties.demand_gap ? '6 4' : null}}),
  pointToLayer: (f, ll) => L.circleMarker(ll, {{radius: 4 + Math.sqrt(f.properties.population_k) / 8, color: '#1F3864', fillColor: '#fff', fillOpacity: 1}}),
  onEachFeature: (f, layer) => layer.bindPopup(Object.entries(f.properties).filter(([k]) => !['stroke','stroke-width','marker-size','marker-color'].includes(k)).map(([k, v]) => `<b>${{k}}</b>: ${{v}}`).join('<br>'))
}}).addTo(map);
</script></body></html>"""
    path.write_text(html, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------- Excel
HEAD = PatternFill("solid", fgColor="1F3864")
HFONT = Font(bold=True, color="FFFFFF")
INPUT = Font(color="1F4E79")


def _head(ws, headers, widths=None):
    for j, h in enumerate(headers, start=1):
        c = ws.cell(row=1, column=j, value=h)
        c.fill, c.font = HEAD, HFONT
        c.alignment = Alignment(wrap_text=True, horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 32
    ws.freeze_panes = "B2"
    for j, w in enumerate(widths or [], start=1):
        ws.column_dimensions[ws.cell(row=1, column=j).column_letter].width = w


def write_excel(path: Path, *, issues, kpis, plan, gaps, monthly) -> Path:
    wb = Workbook()
    ws = wb.active
    ws.title = "Read me"
    for i, (k, v) in enumerate([
        ("Network planning report", "Fictional intercity bus operator; synthetic data. City coordinates are public geography."),
        ("Inputs", "Blue numbers come from ticketing, the operations log and the planning tool. Black numbers are formulas."),
        ("Sheets", "Issue log · Line KPIs · Winter plan · Demand gaps · Monthly passengers"),
        ("Load factor", "Passenger-km divided by seat-km over the whole line, so short busy segments do not hide empty ones."),
    ], start=1):
        ws.cell(row=i, column=1, value=k).font = Font(bold=True, color="1F3864", size=14 if i == 1 else 11)
        ws.cell(row=i, column=2, value=v)
    ws.column_dimensions["A"].width = 24
    ws.column_dimensions["B"].width = 100

    ws = wb.create_sheet("Issue log")
    _head(ws, ["ID", "Check", "Status", "Issues", "Example", "Owner", "Action", "Fixed (x)"], [6, 44, 8, 8, 40, 26, 60, 9])
    for i, r in enumerate(issues.itertuples(index=False), start=2):
        for j, v in enumerate([r.check_id, r.check, r.status, r.issues, r.example, r.owner, r.action], start=1):
            ws.cell(row=i, column=j, value=v).alignment = Alignment(wrap_text=True, vertical="top")
    n = len(issues) + 1
    ws.cell(row=n + 2, column=2, value="Open issues").font = Font(bold=True)
    ws.cell(row=n + 2, column=3, value=f'=COUNTIFS(C2:C{n},"FAIL",H2:H{n},"<>x")')
    red = PatternFill("solid", fgColor="F8D7DA")
    grn = PatternFill("solid", fgColor="D4EDDA")
    ws.conditional_formatting.add(f"C2:C{n}", CellIsRule(operator="equal", formula=['"FAIL"'], fill=red))
    ws.conditional_formatting.add(f"C2:C{n}", CellIsRule(operator="equal", formula=['"PASS"'], fill=grn))

    ws = wb.create_sheet("Line KPIs")
    _head(ws, ["Line", "Route", "Trips", "Passengers", "Passenger-km", "Seat-km", "Revenue EUR", "Bus cost EUR",
               "Load factor", "Contribution EUR", "Margin", "Sold-out share", "Under 35% share", "Revenue per bus-km"],
          [7, 44, 9, 12, 14, 14, 13, 13, 10, 14, 9, 10, 10, 11])
    from .analysis import route_label
    for i, r in enumerate(kpis.itertuples(), start=2):
        ws.cell(row=i, column=1, value=r.line)
        ws.cell(row=i, column=2, value=route_label(r.line))
        for j, v in zip(range(3, 9), [r.trips, r.pax, r.pax_km, r.seat_km, r.revenue_eur, r.bus_cost_eur]):
            c = ws.cell(row=i, column=j, value=float(v))
            c.font, c.number_format = INPUT, "#,##0"
        ws[f"I{i}"], ws[f"J{i}"], ws[f"K{i}"] = f"=E{i}/F{i}", f"=G{i}-H{i}", f"=J{i}/G{i}"
        ws[f"L{i}"], ws[f"M{i}"] = float(r.sold_out_share), float(r.under_35pct_share)
        ws[f"N{i}"] = f"=G{i}/(C{i}*{r.line_km})"
        for col in "IKLM":
            ws[f"{col}{i}"].number_format = "0.0%"
        ws[f"J{i}"].number_format = "#,##0"
        ws[f"N{i}"].number_format = "0.00"
    t = len(kpis) + 2
    ws[f"A{t}"] = "Network"
    ws[f"A{t}"].font = Font(bold=True)
    for col in "CDEFGH":
        ws[f"{col}{t}"] = f"=SUM({col}2:{col}{t - 1})"
        ws[f"{col}{t}"].number_format = "#,##0"
    ws[f"I{t}"], ws[f"J{t}"], ws[f"K{t}"] = f"=E{t}/F{t}", f"=G{t}-H{t}", f"=J{t}/G{t}"
    ws[f"I{t}"].number_format = ws[f"K{t}"].number_format = "0.0%"
    ws.conditional_formatting.add(f"I2:I{t - 1}", ColorScaleRule(start_type="num", start_value=0.3, start_color="F8D7DA",
                                                                 mid_type="num", mid_value=0.55, mid_color="FFFFFF", end_type="num", end_value=0.8, end_color="D4EDDA"))
    ws.conditional_formatting.add(f"J2:J{t - 1}", CellIsRule(operator="lessThan", formula=["0"], fill=red))

    ws = wb.create_sheet("Winter plan")
    _head(ws, ["Line", "Dir", "Current", "Proposed", "Change", "Served now", "Served plan", "Sold out now", "Sold out plan",
               "Contribution now", "Contribution plan", "Contribution change", "Bus-hours now", "Bus-hours plan"],
          [7, 5, 12, 12, 8, 11, 11, 10, 10, 14, 14, 14, 11, 11])
    for i, r in enumerate(plan.itertuples(), start=2):
        for j, v in enumerate([r.line, r.direction, r.current, r.proposed, r.change], start=1):
            ws.cell(row=i, column=j, value=v)
        for col, v in zip("FGHIJKMN", [r.served_now, r.served_plan, r.sold_out_now, r.sold_out_plan, r.contribution_now,
                                         r.contribution_plan, r.bus_hours_now, r.bus_hours_plan]):
            ws[f"{col}{i}"], ws[f"{col}{i}"].font = float(v), INPUT
            ws[f"{col}{i}"].number_format = "0.0%" if col in "HI" else "#,##0"
        ws[f"L{i}"], ws[f"L{i}"].number_format = f"=K{i}-J{i}", "#,##0"
    t = len(plan) + 2
    ws[f"A{t}"] = "Total"
    for col in "FGJKLMN":
        ws[f"{col}{t}"], ws[f"{col}{t}"].number_format = f"=SUM({col}2:{col}{t - 1})", "#,##0"
    ws[f"A{t + 1}"] = "Changes"
    ws[f"E{t + 1}"] = f'=COUNTIF(E2:E{t - 1},"change")'
    ws[f"A{t + 2}"] = "Bus-hours change"
    ws[f"N{t + 2}"], ws[f"N{t + 2}"].number_format = f"=N{t}/M{t}-1", "0.0%"
    ws.conditional_formatting.add(f"L2:L{t - 1}", CellIsRule(operator="lessThan", formula=["0"], font=Font(color="C00000")))

    ws = wb.create_sheet("Demand gaps")
    cols = list(gaps.columns)
    _head(ws, [c.replace("_", " ") for c in cols], [14, 14, 10, 14, 14, 10, 10])
    for i, r in enumerate(gaps.itertuples(index=False), start=2):
        for j, v in enumerate(r, start=1):
            ws.cell(row=i, column=j, value=None if (isinstance(v, float) and np.isnan(v)) else v)

    ws = wb.create_sheet("Monthly passengers")
    piv = monthly.pivot(index="line", columns="month", values="pax").fillna(0)
    _head(ws, ["Line"] + list(piv.columns) + ["Total"], [7] + [9] * (len(piv.columns) + 1))
    from openpyxl.utils import get_column_letter
    last = get_column_letter(len(piv.columns) + 1)
    for i, (line, row) in enumerate(piv.iterrows(), start=2):
        ws.cell(row=i, column=1, value=line)
        for j, v in enumerate(row.values, start=2):
            c = ws.cell(row=i, column=j, value=int(v))
            c.font, c.number_format = INPUT, "#,##0"
        ws.cell(row=i, column=len(piv.columns) + 2, value=f"=SUM(B{i}:{last}{i})").number_format = "#,##0"
    for s in wb.worksheets:
        s.sheet_view.showGridLines = s.title == "Read me"
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path
