"""Run everything: generate or load data, validate, analyse, forecast, plan, report."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from . import analysis as A, config as C, data, db, planning as P, reporting as R, validation as V

LAST_12M = ("2025-10-01", "2026-09-30")


def run(root: Path | None = None, regenerate: bool = False) -> dict:
    paths = C.Paths(root) if root else C.Paths()
    if regenerate or not any(paths.data.glob("*.csv*")):
        data.save(data.generate(), paths.data)
    t = data.load(paths.data)
    paths.figures.mkdir(parents=True, exist_ok=True)

    checks = V.run_all(t)
    issues = V.issue_log(checks)
    trips = V.clean_trips(t)

    con = db.connect(t)
    sql = {f.stem: db.run(con, f, **({"start": LAST_12M[0], "end": LAST_12M[1]} if "kpis" in f.stem else {}))
           for f in sorted(paths.sql.glob("*.sql"))}

    kpis = A.line_kpis(trips, LAST_12M)
    G = A.network_graph(trips, LAST_12M)
    hubs = A.hub_table(G)
    grav = A.fit_gravity(t["od_monthly"], LAST_12M)
    gaps = A.demand_gaps(grav, G)

    bt, bt_weekly = P.backtest(trips, t["truth_demand"], t["timetable"])
    model = P.DemandModel().fit(trips)
    opts = P.optimise(P.options(model, trips, t["timetable"], C.PLAN_SEASON), t["partners"])
    plan = P.plan_table(opts)

    monthly = trips.groupby(["line", "month"])["pax"].sum().reset_index()
    figs = {
        "network_map": R.plot_network_map(G, gaps, paths.figures / "network_map.png"),
        "line_matrix": R.plot_line_matrix(kpis, paths.figures / "line_matrix.png"),
        "winter_plan": R.plot_plan(plan, paths.figures / "winter_plan.png"),
        "backtest": R.plot_backtest(bt_weekly, paths.figures / "forecast_backtest.png"),
    }
    geo = R.geojson(G, gaps, paths.outputs / "network.geojson")
    R.html_map(geo, paths.outputs / "network_map.html")
    xlsx = R.write_excel(paths.outputs / "network_planning_report.xlsx", issues=issues, kpis=kpis, plan=plan,
                         gaps=gaps, monthly=monthly)
    issues.to_csv(paths.outputs / "issue_log.csv", index=False)
    plan.to_csv(paths.outputs / "winter_plan.csv", index=False)
    kpis.to_csv(paths.outputs / "line_kpis.csv", index=False)

    tot = plan[["served_now", "served_plan", "contribution_now", "contribution_plan", "bus_hours_now", "bus_hours_plan"]].sum()
    summary = {
        "checks_failed": int((issues["status"] == "FAIL").sum()), "checks": len(issues),
        "network_load_factor": round(float(kpis["pax_km"].sum() / kpis["seat_km"].sum()), 3),
        "loss_making_lines": kpis.loc[kpis["contribution_eur"] < 0, "line"].tolist(),
        "top_hub": hubs.iloc[0]["city"], "gravity_r2": round(grav["r2"], 3),
        "top_gap": f'{gaps.iloc[0]["origin"]} - {gaps.iloc[0]["destination"]}',
        "backtest": {k: round(v, 3) if isinstance(v, float) else v for k, v in bt.items()},
        "plan_line_directions_changed": int((plan["change"] == "change").sum()),
        "plan_contribution_change_pct": round(float(tot["contribution_plan"] / tot["contribution_now"] - 1), 3),
        "plan_bus_hours_change_pct": round(float(tot["bus_hours_plan"] / tot["bus_hours_now"] - 1), 3),
        "plan_passengers_change_pct": round(float(tot["served_plan"] / tot["served_now"] - 1), 4),
        "sold_out_share_now": round(float(plan["sold_out_now"].mean()), 3),
        "sold_out_share_plan": round(float(plan["sold_out_plan"].mean()), 3),
    }
    (paths.outputs / "summary.json").write_text(json.dumps(summary, indent=2))
    return {"tables": t, "checks": checks, "issues": issues, "trips": trips, "sql": sql, "kpis": kpis, "graph": G,
            "hubs": hubs, "gravity": grav, "gaps": gaps, "backtest": bt, "backtest_weekly": bt_weekly, "model": model,
            "options": opts, "plan": plan, "figures": figs, "excel": xlsx, "summary": summary}


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Validate, analyse, forecast and plan the synthetic bus network.")
    ap.add_argument("--regenerate", action="store_true", help="rebuild the synthetic data first")
    out = run(regenerate=ap.parse_args().regenerate)
    print(json.dumps(out["summary"], indent=2))
