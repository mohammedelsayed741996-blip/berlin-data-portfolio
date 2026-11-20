"""Line performance, network structure and demand gaps."""

from __future__ import annotations

import networkx as nx
import numpy as np
import pandas as pd

from . import config as C
from .world import road_km


def line_kpis(trips: pd.DataFrame, period: tuple[str, str] | None = None, by: list[str] | None = None) -> pd.DataFrame:
    by = by or ["line"]
    t = trips if period is None else trips[trips["date"].between(*period)]
    g = t.groupby(by).agg(trips=("trip_id", "size"), pax=("pax", "sum"), pax_km=("pax_km", "sum"), seat_km=("seat_km", "sum"),
                          revenue_eur=("revenue_eur", "sum"), bus_cost_eur=("bus_cost_eur", "sum"),
                          sold_out_share=("sold_out", "mean"), peak_load=("peak_load", "mean"), seats=("seats", "mean"),
                          line_km=("line_km", "first"))
    g["load_factor"] = g["pax_km"] / g["seat_km"]
    g["peak_load_factor"] = g["peak_load"] / g["seats"]
    g["revenue_per_bus_km"] = g["revenue_eur"] / (g["trips"] * g["line_km"])
    g["contribution_eur"] = g["revenue_eur"] - g["bus_cost_eur"]
    g["contribution_margin"] = g["contribution_eur"] / g["revenue_eur"]
    low = t.assign(low=t["peak_load"] / t["seats"] < 0.35).groupby(by)["low"].mean()
    g["under_35pct_share"] = low
    return g.round(4).reset_index()


def route_label(line: str) -> str:
    s = C.LINES[line]
    return f"{s[0]} - {s[-1]}" if len(s) == 2 else f"{s[0]} - {s[-1]} (via {', '.join(s[1:-1])})"


def network_graph(trips: pd.DataFrame, period: tuple[str, str]) -> nx.Graph:
    """Cities as nodes, line segments as edges weighted with passengers and seats in the period."""
    G = nx.Graph()
    for city, (lat, lon, pop, cc) in C.CITIES.items():
        G.add_node(city, lat=lat, lon=lon, pop=pop, country=cc)
    k = line_kpis(trips, period, ["line"]).set_index("line")
    for line, seq in C.LINES.items():
        if line not in k.index:
            continue
        for a, b in zip(seq[:-1], seq[1:]):
            e = G.get_edge_data(a, b, default={"lines": [], "seats": 0.0, "pax_proxy": 0.0, "km": road_km(a, b)})
            e["lines"] = e["lines"] + [line]
            e["seats"] += k.loc[line, "trips"] * k.loc[line, "seats"]
            e["pax_proxy"] += k.loc[line, "pax_km"] / k.loc[line, "line_km"]       # average passengers on board
            G.add_edge(a, b, **e)
    return G


def hub_table(G: nx.Graph) -> pd.DataFrame:
    btw = nx.betweenness_centrality(G, weight="km")
    return pd.DataFrame({"city": list(G.nodes), "lines": [len({l for _, _, d in G.edges(n, data=True) for l in d["lines"]}) for n in G.nodes],
                         "direct_destinations": [G.degree(n) for n in G.nodes],
                         "betweenness": [round(btw[n], 3) for n in G.nodes]}).sort_values("betweenness", ascending=False).reset_index(drop=True)


def fit_gravity(od: pd.DataFrame, period: tuple[str, str]) -> dict:
    """Log-linear gravity model on observed OD flows: log pax = a + b log(pop_o x pop_d) + c log km + border."""
    o = od[od["month"].between(period[0][:7], period[1][:7])].groupby(["origin", "destination"]).agg(pax=("pax", "sum"), km=("km", "first")).reset_index()
    o = o[o["pax"] > 0]
    days = (pd.Timestamp(period[1]) - pd.Timestamp(period[0])).days + 1
    y = np.log(o["pax"] / days)
    pp = np.log([C.CITIES[a][2] * C.CITIES[b][2] for a, b in zip(o["origin"], o["destination"])])
    lk = np.log(o["km"])
    border = np.array([C.CITIES[a][3] != C.CITIES[b][3] for a, b in zip(o["origin"], o["destination"])], dtype=float)
    X = np.column_stack([np.ones(len(o)), pp, lk, border])
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    pred = X @ beta
    r2 = 1 - ((y - pred) ** 2).sum() / ((y - y.mean()) ** 2).sum()
    return {"beta": beta, "r2": float(r2), "n": len(o)}


def demand_gaps(model: dict, G: nx.Graph, top: int = 10, min_km: float = 150, max_km: float = 900) -> pd.DataFrame:
    """City pairs without a direct line, ranked by the passengers the gravity model expects per day."""
    served = {(a, b) for line, seq in C.LINES.items() for i, a in enumerate(seq) for b in seq[i + 1:]}
    served |= {(b, a) for a, b in served}
    b = model["beta"]
    rows = []
    cities = list(C.CITIES)
    for i, a in enumerate(cities):
        for c in cities[i + 1:]:
            if (a, c) in served:
                continue
            km = road_km(a, c)
            if not (min_km <= km <= max_km):
                continue
            border = float(C.CITIES[a][3] != C.CITIES[c][3])
            per_dir = float(np.exp(b[0] + b[1] * np.log(C.CITIES[a][2] * C.CITIES[c][2]) + b[2] * np.log(km) + b[3] * border))
            try:
                path = nx.shortest_path(G, a, c, weight="km")
                via = len(path) - 2
                path_km = sum(G[path[k]][path[k + 1]]["km"] for k in range(len(path) - 1))
                changes = sum(1 for k in range(1, len(path) - 1)
                              if not set(G[path[k - 1]][path[k]]["lines"]) & set(G[path[k]][path[k + 1]]["lines"]))
            except nx.NetworkXNoPath:
                via, path_km, changes = None, None, None
            rows.append({"origin": a, "destination": c, "road_km": km, "expected_pax_per_day_each_way": round(per_dir, 1),
                         "current_best_path_km": round(path_km, 0) if path_km else None,
                         "detour_pct": round(path_km / km - 1, 2) if path_km else None, "changes_needed": changes})
    return pd.DataFrame(rows).sort_values("expected_pax_per_day_each_way", ascending=False).head(top).reset_index(drop=True)
