from timepref import config as C, quality as Q


def test_every_careless_responder_is_excluded(tables, cleaned):
    _, _, rules = cleaned
    excluded = set(rules[1].flagged) | set(rules[2].flagged)
    careless = set(tables["truth"].query("careless != 'no'")["pid"])
    assert careless <= excluded
    assert len(excluded - careless) <= 3                    # few genuine participants lost


def test_duplicates_found(cleaned):
    assert len(cleaned[2][0].flagged) == C.PLANTED["duplicate_submissions"]


def test_clean_table(clean):
    assert not clean["catch"].any()
    assert (clean.groupby("pid").size() == C.N_TRIALS).all()
    assert clean.groupby(["pid", "trial"]).size().max() == 1


def test_flow_adds_up(tables, cleaned):
    f = Q.flow(tables, cleaned[2]).set_index("step")["n"]
    excl = f["Excluded: catch trials only"] + f["Excluded: too fast only"] + f["Excluded: both"]
    assert f["Unique participant codes"] - excl == f["Analysed"]
