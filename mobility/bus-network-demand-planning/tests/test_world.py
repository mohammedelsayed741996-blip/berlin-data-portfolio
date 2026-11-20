import numpy as np

from bus_network import config as C
from bus_network.world import haversine, road_km


def test_distances_are_plausible():
    straight = haversine(C.CITIES["Berlin"][:2], C.CITIES["Hamburg"][:2])
    assert 250 < straight < 270                                 # Berlin to Hamburg is about 255 km as the crow flies
    assert road_km("Berlin", "Hamburg") == round(straight * C.ROAD_FACTOR, 1)


def test_tables_have_expected_shape(tables):
    assert set(tables) == {"stops", "line_stops", "timetable", "partners", "operations", "bookings", "od_monthly", "truth_demand"}
    assert len(tables["timetable"]) == 80
    assert tables["operations"]["trip_id"].is_unique


def test_no_personal_data(tables):
    cols = {c for df in tables.values() for c in df.columns}
    assert not cols & {"name", "email", "phone", "customer_id", "passenger_name"}
    assert tables["partners"]["partner_name"].str.endswith("(fictional)").all()


def test_bookings_never_exceed_planned_double_decker(tables):
    b = tables["bookings"]
    assert b["peak_load"].max() <= max(C.BUS_TYPES.values())


def test_true_demand_at_least_bookings(tables):
    m = tables["bookings"].merge(tables["truth_demand"], on="trip_id")
    # whole-passenger rounding can add under one passenger per origin-destination pair
    assert (m["pax"] <= m["unconstrained_pax"] + 6).all()
    assert np.isclose(m.loc[~m["sold_out"].astype(bool), "pax"].sum(),
                      m.loc[~m["sold_out"].astype(bool), "unconstrained_pax"].sum(), rtol=0.02)
