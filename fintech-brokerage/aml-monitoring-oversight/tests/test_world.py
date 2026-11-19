import re

import pandas as pd

from aml_oversight import config as C, world


def test_generation_is_deterministic():
    a, b = world.generate(), world.generate()
    pd.testing.assert_frame_equal(a["transactions"], b["transactions"])


def test_no_real_identifiers(tables):
    cl = tables["clients"]
    assert cl["client_id"].str.fullmatch(r"C\d{6}").all()
    assert cl["payout_account"].str.fullmatch(r"IBAN[0-9a-f]{12}").all()      # random hash, not an IBAN
    assert not tables["transactions"]["counterparty_country"].isin(["RU", "IR", "KP", "SY"]).any()
    assert set(tables["alerts"]["analyst"]) <= set(C.ANALYSTS)


def test_typologies_planted(tables):
    t = tables["typology_truth"]
    assert t["typology"].value_counts().to_dict() == C.TYPOLOGIES
    assert t["client_id"].is_unique


def test_mule_rings_share_payout_accounts(tables):
    cl = tables["clients"]
    mules = tables["typology_truth"].query("typology == 'T4 mule ring'")["client_id"]
    shared = cl[cl["client_id"].isin(mules)].groupby("payout_account").size()
    assert len(shared) == 6 and (shared == 6).all()


def test_sanctioned_clients_have_close_spelling(tables):
    from difflib import SequenceMatcher
    wl = tables["watchlist"].set_index("entry_id")
    cl = tables["clients"].set_index("client_id")
    for r in tables["sanctions_truth"].itertuples():
        a, b = cl.loc[r.client_id, "name"].lower(), wl.loc[r.entry_id, "name"].lower()
        assert a != b and SequenceMatcher(None, a, b).ratio() > 0.9
