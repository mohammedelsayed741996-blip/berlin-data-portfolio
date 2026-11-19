import pandas as pd

from aml_oversight import config as C, monitoring


def test_feed_gap_only_drops_the_affected_card_deposits(tables):
    tx = tables["transactions"]
    missing = tx[~tx["tx_id"].isin(tables["tm_feed_ids"]["tx_id"])]
    assert len(missing) > 500
    assert (missing["channel"] == "CARD").all() and (missing["psp"] == C.FEED_GAP[2]).all()
    assert missing["date"].between(C.FEED_GAP[0], C.FEED_GAP[1]).all()


def test_rule_r01_threshold(tables):
    a = tables["alerts"]
    assert (a.loc[a["rule"] == "R01", "trigger_amount_eur"] >= 15_000).all()


def test_one_alert_per_client_rule_month(tables):
    a = tables["alerts"]
    assert not a.duplicated(["client_id", "rule", "month"]).any()


def test_r02_needs_more_deposits_after_the_change(tables):
    tx = tables["transactions"]
    feed = tx[tx["tx_id"].isin(tables["tm_feed_ids"]["tx_id"])]
    a = tables["alerts"]
    late = a[(a["rule"] == "R02") & (a["alert_date"] >= C.R02_CHANGE_DATE)]
    dep = feed[(feed["type"] == "DEPOSIT") & feed["amount_eur"].between(8_500, 9_999.99)]
    for r in late.itertuples():
        d = pd.Timestamp(r.alert_date)
        win = dep[(dep["client_id"] == r.client_id) & (pd.to_datetime(dep["date"]) <= d) & (pd.to_datetime(dep["date"]) > d - pd.Timedelta(days=30))]
        assert len(win) >= C.R02_COUNT_AFTER


def test_weak_analyst_closes_more_true_cases(tables):
    a = tables["alerts"]
    tp = a[a["true_suspicious"] & (a["l1_decision"] != "open")]
    miss = tp.groupby(tp["analyst"] == C.WEAK_ANALYST)["l1_decision"].apply(lambda s: (s == "closed_no_concern").mean())
    assert miss[True] > 3 * miss[False]


def test_sar_dates_follow_escalation(tables):
    a = tables["alerts"]
    s = a[a["sar_date"] != ""]
    assert (s["l1_decision"] == "escalated").all()
    assert (s["sar_date"] > s["l1_closed_date"]).all()
