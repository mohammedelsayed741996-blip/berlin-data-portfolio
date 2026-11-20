import numpy as np
import pytest

from bus_network import analysis as A, config as C, db, planning as P
from bus_network.config import Paths

PERIOD = ("2025-10-01", "2026-09-30")


def test_load_factor_bounds(trips):
    k = A.line_kpis(trips, PERIOD)
    assert k["load_factor"].between(0, 1).all()
    assert (k["peak_load_factor"] >= k["load_factor"] - 1e-9).all()


def test_sql_kpis_match_python(tables, trips):
    con = db.connect(tables)
    s = db.run(con, Paths().sql / "04_line_kpis.sql", start=PERIOD[0], end=PERIOD[1]).set_index("line")
    k = A.line_kpis(trips, PERIOD).set_index("line")
    assert np.allclose(s["load_factor"], k.loc[s.index, "load_factor"], atol=0.005)


def test_sql_checks_agree_with_python(tables):
    con = db.connect(tables)
    assert len(db.run(con, Paths().sql / "01_unlogged_trips.sql")) == C.PLANTED["unlogged_trips"]
    cap = db.run(con, Paths().sql / "02_capacity_mismatch.sql")
    assert cap["line"].tolist() == [C.PLANTED["capacity_mismatch_line"]]


def test_gravity_model_fits(tables):
    g = A.fit_gravity(tables["od_monthly"], PERIOD)
    assert g["r2"] > 0.8
    assert 0.5 < g["beta"][1] < 1.0          # elasticity to population, simulated at 0.72


def test_demand_gaps_have_no_direct_line(tables, trips):
    G = A.network_graph(trips, PERIOD)
    gaps = A.demand_gaps(A.fit_gravity(tables["od_monthly"], PERIOD), G)
    assert not any(G.has_edge(a, b) for a, b in zip(gaps["origin"], gaps["destination"]))


@pytest.fixture(scope="module")
def plan_run(tables, trips):
    m = P.DemandModel().fit(trips)
    o = P.optimise(P.options(m, trips, tables["timetable"], C.PLAN_SEASON, draws=60), tables["partners"])
    return o, P.plan_table(o)


def test_backtest_beats_naive(tables, trips):
    bt, _ = P.backtest(trips, tables["truth_demand"], tables["timetable"])
    assert bt["model_wape_vs_true_demand"] < bt["naive_wape_vs_true_demand"]
    assert abs(bt["model_bias_pct"]) < 0.05


def test_plan_respects_constraints(plan_run, tables):
    o, pt = plan_run
    assert (o.groupby(["line", "direction"])["chosen"].sum() == 1).all()
    assert o.loc[o["chosen"], "bus_hours"].sum() <= o.loc[o["is_current"], "bus_hours"].sum() * 1.03 + 1e-6
    assert o.loc[o["chosen"], "served_pax"].sum() >= o.loc[o["is_current"], "served_pax"].sum() - 1e-6
    a = pt[pt["direction"] == "A"].set_index("line")["proposed"]
    b = pt[pt["direction"] == "B"].set_index("line")["proposed"]
    assert (a == b.loc[a.index]).all()                     # round trips: same offer both ways


def test_plan_does_not_lose_contribution(plan_run):
    _, pt = plan_run
    assert pt["contribution_plan"].sum() >= pt["contribution_now"].sum()
