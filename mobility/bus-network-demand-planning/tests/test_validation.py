from bus_network import config as C, validation as V


def by_id(tables):
    return {c.check_id: c for c in V.run_all(tables)}


def test_swapped_coordinates_found(tables):
    rows = by_id(tables)["V01"].rows
    assert rows["stop_name"].str.contains(C.PLANTED["swapped_coordinates_stop"]).any()


def test_duplicate_stop_found(tables):
    assert len(by_id(tables)["V02"].rows) == 1


def test_unlogged_trips_found_exactly(tables):
    assert len(by_id(tables)["V03"].rows) == C.PLANTED["unlogged_trips"]


def test_orphan_bookings_found_exactly(tables):
    assert len(by_id(tables)["V04"].rows) == C.PLANTED["orphan_bookings"]


def test_capacity_mismatch_points_at_planted_line(tables):
    rows = by_id(tables)["V05"].rows
    assert set(rows["line"]) == {C.PLANTED["capacity_mismatch_line"]}


def test_expired_contract_found(tables):
    rows = by_id(tables)["V06"].rows
    assert set(rows["partner_id"]) == {C.PLANTED["expired_contract_partner"]}


def test_cancelled_trips_carry_no_passengers(tables):
    assert by_id(tables)["V07"].status == "PASS"


def test_clean_trips_excludes_cancelled_and_orphans(tables, trips):
    assert (trips["pax"] >= 0).all()
    assert not trips["trip_id"].str.endswith("0545").any()
    assert trips["trip_id"].is_unique
