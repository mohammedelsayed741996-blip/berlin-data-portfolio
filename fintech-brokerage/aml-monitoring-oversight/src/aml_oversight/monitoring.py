"""The first line: transaction monitoring rules, name screening and alert handling.

This is the programme the oversight team has to check, so it contains the problems an
oversight function is there to find: a feed that silently dropped card deposits for a few
weeks, a rule threshold changed without approval, an analyst who closes too many real
cases, missing rationales, a summer backlog, a screening batch that ran late, and one
sanctions hit closed as a false positive.
"""

from __future__ import annotations

from difflib import SequenceMatcher

import numpy as np
import pandas as pd

from . import config as C


def tm_feed(tx: pd.DataFrame) -> pd.DataFrame:
    """What the monitoring system actually received from the core ledger."""
    start, end, psp = C.FEED_GAP
    lost = (tx["type"] == "DEPOSIT") & (tx["channel"] == "CARD") & (tx["psp"] == psp) & tx["date"].between(start, end)
    return tx[~lost].copy()


def _alert(rows, client, rule, date, amount):
    rows.append({"client_id": client, "rule": rule, "alert_date": date, "trigger_amount_eur": round(float(amount), 2)})


def run_rules(feed: pd.DataFrame, clients: pd.DataFrame) -> pd.DataFrame:
    """Run the six rules; at most one alert per client, rule and month (the usual de-duplication)."""
    rows = []
    f = feed.assign(d=pd.to_datetime(feed["date"]))
    dep = f[f["type"] == "DEPOSIT"]
    expected = clients.set_index("client_id")["expected_monthly_deposit_eur"]

    for r in dep[dep["amount_eur"] >= 15_000].itertuples():
        _alert(rows, r.client_id, "R01", r.date, r.amount_eur)

    near = dep[dep["amount_eur"].between(8_500, 9_999.99)]
    for cid, g in near.groupby("client_id"):
        days = g["d"].values
        for i, (d, amt, ds) in enumerate(zip(g["d"], g["amount_eur"], g["date"])):
            k = C.R02_COUNT_BEFORE if ds < C.R02_CHANGE_DATE else C.R02_COUNT_AFTER
            n = int(((days <= d.to_datetime64()) & (days > (d - pd.Timedelta(days=30)).to_datetime64())).sum())
            if n >= k:
                _alert(rows, cid, "R02", ds, amt)

    wd = f[f["type"] == "WITHDRAWAL"]
    buys = f[f["type"] == "BUY"]
    dep_by = {k: g for k, g in dep.groupby("client_id")}
    buy_by = {k: g for k, g in buys.groupby("client_id")}
    for r in wd.itertuples():
        g = dep_by.get(r.client_id)
        if g is None:
            continue
        win = g[(g["d"] <= r.d) & (g["d"] > r.d - pd.Timedelta(days=7))]
        D = win["amount_eur"].sum()
        if D < 3_000 or r.amount_eur < 0.8 * D:
            continue
        b = buy_by.get(r.client_id)
        traded = 0.0 if b is None else b[(b["d"] <= r.d) & (b["d"] > r.d - pd.Timedelta(days=7))]["amount_eur"].sum()
        if traded < 0.2 * D:
            _alert(rows, r.client_id, "R03", r.date, r.amount_eur)

    third = dep[~dep["own_account"]]
    for cid, g in third.groupby("client_id"):
        for d, ds, amt in zip(g["d"], g["date"], g["amount_eur"]):
            win = g[(g["d"] <= d) & (g["d"] > d - pd.Timedelta(days=30))]
            if win["counterparty"].nunique() >= 2:
                _alert(rows, cid, "R04", ds, amt)

    for r in dep[dep["counterparty_country"].isin(C.HIGH_RISK_JURISDICTIONS)].itertuples():
        _alert(rows, r.client_id, "R05", r.date, r.amount_eur)

    monthly = dep.assign(month=dep["date"].str[:7]).groupby(["client_id", "month"]).agg(
        total=("amount_eur", "sum"), last=("date", "max")).reset_index()
    monthly["expected"] = monthly["client_id"].map(expected)
    hit = monthly[(monthly["total"] > 20_000) & (monthly["total"] > 5 * monthly["expected"])]
    for r in hit.itertuples():
        _alert(rows, r.client_id, "R06", r.last, r.total)

    a = pd.DataFrame(rows)
    a["month"] = a["alert_date"].str[:7]
    a = a.sort_values("alert_date").drop_duplicates(["client_id", "rule", "month"]).reset_index(drop=True)
    a.insert(0, "alert_id", [f"AL{i:06d}" for i in range(1, len(a) + 1)])
    return a


def label_alerts(alerts: pd.DataFrame, truth: pd.DataFrame) -> pd.DataFrame:
    """Ground truth for testing only: the client's typology was active in the alert month (or next to it)."""
    t = truth.set_index("client_id")
    def is_true(r):
        if r.client_id not in t.index:
            return False
        row = t.loc[r.client_id]
        lo = (pd.Period(row["first_month"], freq="M") - 1).strftime("%Y-%m")
        hi = (pd.Period(row["last_month"], freq="M") + 1).strftime("%Y-%m")
        return lo <= r.month <= hi
    return alerts.assign(true_suspicious=[is_true(r) for r in alerts.itertuples()])


RATIONALES_FP = ["Activity consistent with declared income and trading history.",
                 "Source of funds evidenced by salary statements on file.",
                 "One-off transfer explained by client (property sale); documents on file.",
                 "Third-party deposit from spouse's account; relationship verified.",
                 "Deposits match recurring savings pattern seen over 12 months."]
RATIONALES_ESC = ["Pattern not explained by profile; escalated to L2 for investigation.",
                  "Funds withdrawn shortly after deposit with no investment purpose; escalated.",
                  "Multiple unrelated third-party payers; escalated for source of funds review."]


def handle_alerts(alerts: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Level 1 and level 2 decisions, dates and rationales."""
    a = alerts.copy()
    n = len(a)
    a["analyst"] = rng.choice(C.ANALYSTS, size=n)
    tp = a["true_suspicious"].values
    p_esc = np.where(tp, np.where(a["analyst"] == C.WEAK_ANALYST, 0.45, 0.95), 0.06)
    escalate = rng.random(n) < p_esc
    created = pd.to_datetime(a["alert_date"])
    days = rng.lognormal(np.log(6), 0.6, n)
    summer = a["month"].isin(["2026-07", "2026-08"]).values & (rng.random(n) < 0.45)
    days = days + summer * rng.uniform(20, 45, n)
    closed = created + pd.to_timedelta(np.round(days), unit="D")
    a["l1_decision"] = np.where(escalate, "escalated", "closed_no_concern")
    a["l1_closed_date"] = closed.dt.strftime("%Y-%m-%d")
    open_mask = closed > pd.Timestamp(C.END)
    a.loc[open_mask, "l1_decision"] = "open"
    a.loc[open_mask, "l1_closed_date"] = ""
    missing_p = np.where(a["analyst"] == C.SLOPPY_ANALYST, 0.22, 0.015)
    missing = rng.random(n) < missing_p
    a["l1_rationale"] = [("" if miss else (rng.choice(RATIONALES_ESC) if e else rng.choice(RATIONALES_FP)))
                         for miss, e in zip(missing, escalate)]
    a.loc[open_mask, "l1_rationale"] = ""
    # Level 2: SAR decision for escalated alerts
    esc = (a["l1_decision"] == "escalated").values
    p_sar = np.where(tp, 0.92, 0.12)
    sar = esc & (rng.random(n) < p_sar)
    sar_days = np.round(rng.lognormal(np.log(14), 0.5, n))
    sar_date = pd.to_datetime(a["l1_closed_date"].replace("", None)) + pd.to_timedelta(sar_days, unit="D")
    a["l2_decision"] = np.where(esc, np.where(sar, "SAR filed", "no SAR"), "")
    a["sar_date"] = np.where(sar, sar_date.dt.strftime("%Y-%m-%d"), "")
    late_sar = sar & (sar_date > pd.Timestamp(C.END)).values
    a.loc[late_sar, "l2_decision"] = "in investigation"
    a.loc[late_sar, "sar_date"] = ""
    return a


# ---------------------------------------------------------------------------- screening
def _norm(name: str) -> str:
    return name.lower().replace("ä", "a").replace("ö", "o").replace("ü", "u")


def screen(clients: pd.DataFrame, watchlist: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Fuzzy name screening at onboarding and when new list entries arrive, with level 1 decisions.

    Blocking on the first two letters of the surname keeps the comparison count small, as
    screening engines do."""
    wl = watchlist.assign(n=watchlist["name"].map(_norm))
    wl["block"] = wl["n"].str.split().str[-1].str[:2]
    cl = clients.assign(n=clients["name"].map(_norm))
    cl["block"] = cl["n"].str.split().str[-1].str[:2]
    added = {e: "2026-05-04" for e in wl["entry_id"] if e >= "W0900"}       # list update with new sanctions entries
    hits = []
    for b, cg in cl.groupby("block"):
        wg = wl[wl["block"] == b]
        for c in cg.itertuples():
            for w in wg.itertuples():
                sm = SequenceMatcher(None, c.n, w.n)
                if sm.real_quick_ratio() < C.SCREENING_THRESHOLD or sm.quick_ratio() < C.SCREENING_THRESHOLD:
                    continue
                s = sm.ratio()
                if s >= C.SCREENING_THRESHOLD:
                    hits.append((c.client_id, w.entry_id, w.list, round(s, 3), int(c.birth_year) == int(w.birth_year)))
    h = pd.DataFrame(hits, columns=["client_id", "entry_id", "list", "match_score", "birth_year_match"])
    onboard = clients.set_index("client_id")["onboarding_date"]
    h["screened_date"] = [max(onboard[c], added.get(e, "0000")) for c, e in zip(h["client_id"], h["entry_id"])]
    h.insert(0, "hit_id", [f"SH{i:05d}" for i in range(1, len(h) + 1)])
    return h


def screening_log(clients: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """When each client onboarded in the period was first screened. The batch outage delays a few days."""
    c = clients[clients["onboarding_date"].between(C.START, C.END)][["client_id", "onboarding_date"]].copy()
    d = pd.to_datetime(c["onboarding_date"])
    lag = np.where(rng.random(len(c)) < 0.995, 0, 1)
    out_start, out_end = C.SCREENING_OUTAGE
    outage = c["onboarding_date"].between(out_start, out_end).values
    lag = np.where(outage, rng.integers(4, 8, len(c)), lag)
    c["screened_date"] = (d + pd.to_timedelta(lag, unit="D")).dt.strftime("%Y-%m-%d")
    c["days_to_screen"] = lag
    return c.reset_index(drop=True)


def decide_hits(hits: pd.DataFrame, clients: pd.DataFrame, sanctions_truth: pd.DataFrame, rng) -> pd.DataFrame:
    h = hits.copy()
    true_pairs = set(zip(sanctions_truth["client_id"], sanctions_truth["entry_id"]))
    pep_names = set(clients.loc[clients["pep"], "client_id"])
    h["true_match"] = [(c, e) in true_pairs or (lst == "PEP" and c in pep_names and s >= 0.999)
                       for c, e, lst, s in zip(h["client_id"], h["entry_id"], h["list"], h["match_score"])]
    h["analyst"] = rng.choice(C.ANALYSTS, size=len(h))
    h["decision"] = np.where(h["true_match"], "true match", "false positive")
    # The planted miss: the weakest-spelled sanctions variant is closed as a false positive
    miss = h[(h["true_match"]) & (h["list"] == "sanctions")].sort_values("match_score").head(1).index
    h.loc[miss, "decision"] = "false positive"
    h.loc[miss, "analyst"] = C.WEAK_ANALYST
    h["decided_date"] = (pd.to_datetime(h["screened_date"]) + pd.to_timedelta(rng.integers(0, 3, len(h)), unit="D")).dt.strftime("%Y-%m-%d")
    return h


def run_programme(tables: dict, seed: int = C.SEED) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(seed + 1)
    feed = tm_feed(tables["transactions"])
    alerts = label_alerts(run_rules(feed, tables["clients"]), tables["typology_truth"])
    alerts = handle_alerts(alerts, rng)
    hits = decide_hits(screen(tables["clients"], tables["watchlist"], rng), tables["clients"], tables["sanctions_truth"], rng)
    return {"tm_feed_ids": feed[["tx_id"]], "alerts": alerts, "screening_hits": hits,
            "screening_log": screening_log(tables["clients"], rng)}
