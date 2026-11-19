"""Second-line oversight of the monitoring and screening programme.

Each function answers one question an AML oversight team asks every month:
did the monitoring system receive all the data, are alerts handled in time and documented,
are the decisions right, do the rules still work and cover the risks, are clients screened
on time, are periodic reviews up to date, and what goes to senior management.

Ground-truth columns (true_suspicious, true_match) stand in for the QA reviewer's own
judgement when a sampled case is re-reviewed. They are used only for those re-reviews and
for testing, never to compute the first-line KPIs.
"""

from __future__ import annotations

import math

import networkx as nx
import numpy as np
import pandas as pd
from scipy import stats

from . import config as C


# ---------------------------------------------------------------------------- data completeness
def completeness(tx: pd.DataFrame, feed_ids: pd.DataFrame) -> pd.DataFrame:
    """Core ledger vs monitoring feed, by month and channel."""
    t = tx.assign(month=tx["date"].str[:7], in_feed=tx["tx_id"].isin(feed_ids["tx_id"]))
    t["source"] = np.where(t["channel"] == "CARD", "CARD " + t["psp"], t["channel"])
    g = t.groupby(["month", "source"]).agg(ledger_count=("tx_id", "size"), feed_count=("in_feed", "sum"),
                                           ledger_eur=("amount_eur", "sum"))
    g["missing_count"] = g["ledger_count"] - g["feed_count"]
    g["missing_eur"] = t[~t["in_feed"]].groupby(["month", "source"])["amount_eur"].sum().reindex(g.index).fillna(0)
    return g.reset_index().round(2)


def missing_transactions(tx: pd.DataFrame, feed_ids: pd.DataFrame) -> pd.DataFrame:
    return tx[~tx["tx_id"].isin(feed_ids["tx_id"])]


# ---------------------------------------------------------------------------- alert handling KPIs
def alert_kpis(alerts: pd.DataFrame) -> pd.DataFrame:
    """Monthly first-line KPIs, computed only from what the case system records."""
    a = alerts.copy()
    created = pd.to_datetime(a["alert_date"])
    closed = pd.to_datetime(a["l1_closed_date"].replace("", None))
    rows = []
    for m in C.MONTHS:
        me = pd.Period(m, freq="M").end_time.normalize()
        created_m = a["month"] == m
        open_at_me = (created <= me) & (closed.isna() | (closed > me))
        age = (me - created[open_at_me]).dt.days
        closed_m = closed.dt.strftime("%Y-%m") == m
        handling = (closed - created).dt.days[closed_m]
        sar_m = a["sar_date"].str[:7] == m
        to_sar = (pd.to_datetime(a.loc[sar_m, "sar_date"]) - created[sar_m]).dt.days
        rows.append({
            "month": m, "alerts_created": int(created_m.sum()), "alerts_closed": int(closed_m.sum()),
            "backlog_month_end": int(open_at_me.sum()), "backlog_over_sla": int((age > C.ALERT_SLA_DAYS).sum()),
            "closed_over_sla_pct": float((handling > C.ALERT_SLA_DAYS).mean()) if len(handling) else 0.0,
            "median_handling_days": float(handling.median()) if len(handling) else np.nan,
            "escalation_rate": float((a.loc[closed_m, "l1_decision"] == "escalated").mean()) if closed_m.any() else np.nan,
            "missing_rationale_pct": float((a.loc[closed_m, "l1_rationale"] == "").mean()) if closed_m.any() else np.nan,
            "sars_filed": int(sar_m.sum()),
            "median_days_alert_to_sar": float(to_sar.median()) if len(to_sar) else np.nan,
        })
    return pd.DataFrame(rows).round(4)


# ---------------------------------------------------------------------------- QA sampling
def zero_failure_sample_size(confidence: float = C.QA_CONFIDENCE, tolerable: float = C.QA_TOLERABLE_ERROR) -> int:
    """Smallest n such that finding no errors shows the error rate is below `tolerable` with `confidence`."""
    return math.ceil(math.log(1 - confidence) / math.log(1 - tolerable))


def qa_sample(alerts: pd.DataFrame, quarter_months: list[str], rng: np.random.Generator) -> pd.DataFrame:
    """Stratified random sample of alerts closed with no concern in a quarter, at least 4 per analyst."""
    closed = alerts[(alerts["l1_decision"] == "closed_no_concern") & alerts["l1_closed_date"].str[:7].isin(quarter_months)]
    n = zero_failure_sample_size()
    alloc = (closed["analyst"].value_counts(normalize=True) * n).round().astype(int).clip(lower=4)
    parts = [g.sample(min(len(g), alloc.get(a, 4)), random_state=int(rng.integers(1e9))) for a, g in closed.groupby("analyst")]
    return pd.concat(parts) if parts else closed.head(0)


def qa_review(sample: pd.DataFrame) -> pd.DataFrame:
    """Re-review: a decision error is a closed case the reviewer would have escalated;
    a documentation error is a missing rationale."""
    s = sample.copy()
    s["decision_error"] = s["true_suspicious"]
    s["documentation_error"] = s["l1_rationale"] == ""
    s["any_error"] = s["decision_error"] | s["documentation_error"]
    return s


def clopper_pearson(k: int, n: int, conf: float = 0.95) -> tuple[float, float]:
    a = 1 - conf
    lo = stats.beta.ppf(a / 2, k, n - k + 1) if k > 0 else 0.0
    hi = stats.beta.ppf(1 - a / 2, k + 1, n - k) if k < n else 1.0
    return float(lo), float(hi)


def qa_programme(alerts: pd.DataFrame, seed: int = C.SEED) -> pd.DataFrame:
    rng = np.random.default_rng(seed + 7)
    quarters = {"Q4 2025": C.MONTHS[0:3], "Q1 2026": C.MONTHS[3:6], "Q2 2026": C.MONTHS[6:9], "Q3 2026": C.MONTHS[9:12]}
    out = []
    for q, ms in quarters.items():
        out.append(qa_review(qa_sample(alerts, ms, rng)).assign(quarter=q))
    return pd.concat(out, ignore_index=True)


def qa_by(reviewed: pd.DataFrame, by: str) -> pd.DataFrame:
    rows = []
    for key, g in reviewed.groupby(by):
        n = len(g)
        for kind in ["decision_error", "documentation_error"]:
            k = int(g[kind].sum())
            lo, hi = clopper_pearson(k, n)
            rows.append({by: key, "error_type": kind, "sampled": n, "errors": k, "error_rate": k / n, "ci_low": lo, "ci_high": hi})
    return pd.DataFrame(rows).round(4)


def targeted_lookback(alerts: pd.DataFrame, analyst: str) -> pd.DataFrame:
    """After a QA finding: re-review every case the analyst closed with no concern."""
    g = alerts[(alerts["analyst"] == analyst) & (alerts["l1_decision"] == "closed_no_concern")]
    return g[g["true_suspicious"]][["alert_id", "client_id", "rule", "alert_date", "l1_rationale"]]


# ---------------------------------------------------------------------------- rules
def rule_effectiveness(alerts: pd.DataFrame) -> pd.DataFrame:
    a = alerts[alerts["l1_decision"] != "open"]
    g = a.groupby("rule").agg(alerts=("alert_id", "size"),
                              escalated=("l1_decision", lambda s: (s == "escalated").sum()),
                              sars=("l2_decision", lambda s: (s == "SAR filed").sum()))
    g["escalation_rate"] = g["escalated"] / g["alerts"]
    g["sar_conversion"] = g["sars"] / g["alerts"]
    g.insert(0, "description", [C.RULES[r] for r in g.index])
    return g.round(3).reset_index()


def typology_coverage(alerts: pd.DataFrame, truth: pd.DataFrame) -> pd.DataFrame:
    """Share of clients of each typology alerted by each rule while the behaviour was going on."""
    hit = alerts[alerts["true_suspicious"]]
    rows = []
    for typ, g in truth.groupby("typology"):
        ids = set(g["client_id"])
        row = {"typology": typ, "clients": len(ids)}
        for r in C.RULES:
            row[r] = len(ids & set(hit.loc[hit["rule"] == r, "client_id"])) / len(ids)
        row["any_rule"] = len(ids & set(hit["client_id"])) / len(ids)
        rows.append(row)
    return pd.DataFrame(rows).round(3)


def volume_change(alerts: pd.DataFrame, rule: str, change_month: str) -> dict:
    """Did a rule's monthly alert volume shift? Poisson rate comparison before and after a month."""
    m = alerts[alerts["rule"] == rule].groupby("month").size().reindex(C.MONTHS, fill_value=0)
    before, after = m[m.index < change_month], m[m.index >= change_month]
    k1, n1, k2, n2 = before.sum(), len(before), after.sum(), len(after)
    # conditional binomial test for equal rates
    p = stats.binomtest(int(k2), int(k1 + k2), n2 / (n1 + n2)).pvalue
    return {"rule": rule, "rate_before": k1 / n1, "rate_after": k2 / n2, "change_pct": (k2 / n2) / (k1 / n1) - 1, "p_value": float(p)}


def below_the_line(feed_tx: pd.DataFrame, alerts: pd.DataFrame, truth: pd.DataFrame, since: str = C.R02_CHANGE_DATE,
                   counts=(3, 4, 5)) -> pd.DataFrame:
    """Re-run the structuring rule after the change with lower counts and see what the current setting misses."""
    dep = feed_tx[(feed_tx["type"] == "DEPOSIT") & feed_tx["amount_eur"].between(8_500, 9_999.99) & (feed_tx["date"] >= since)]
    dep = dep.assign(d=pd.to_datetime(dep["date"]))
    t = truth.set_index("client_id")["typology"]
    rows = []
    for k in counts:
        flagged = set()
        for cid, g in dep.groupby("client_id"):
            days = g["d"].values
            for d in g["d"]:
                if ((days <= d.to_datetime64()) & (days > (d - pd.Timedelta(days=30)).to_datetime64())).sum() >= k:
                    flagged.add(cid)
                    break
        structuring = {c for c in flagged if t.get(c) == "T1 structuring"}
        rows.append({"min_deposits": k, "clients_alerted": len(flagged), "structuring_clients": len(structuring),
                     "other_clients": len(flagged) - len(structuring)})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------- network
def shared_attribute_networks(clients: pd.DataFrame, tx: pd.DataFrame, min_size: int = 3) -> pd.DataFrame:
    """Clients linked by a shared payout account or device. Groups of three or more are a mule-ring signal
    the transaction rules cannot see."""
    G = nx.Graph()
    for col in ["payout_account", "device_id"]:
        for val, g in clients.groupby(col):
            ids = g["client_id"].tolist()
            if len(ids) > 1:
                for i in range(1, len(ids)):
                    G.add_edge(ids[0], ids[i], via=col)
    rows = []
    wd = tx[tx["type"] == "WITHDRAWAL"].groupby("client_id")["amount_eur"].sum()
    dep = tx[tx["type"] == "DEPOSIT"].groupby("client_id")["amount_eur"].agg(["sum", "count"])
    for i, comp in enumerate(sorted(nx.connected_components(G), key=lambda c: sorted(c)[0]), start=1):
        if len(comp) < min_size:
            continue
        ids = sorted(comp)
        sub = clients[clients["client_id"].isin(ids)]
        rows.append({"network_id": f"N{i:03d}", "clients": len(ids), "client_ids": ", ".join(ids),
                     "shared_payout": sub["payout_account"].nunique() == 1, "shared_device": sub["device_id"].nunique() == 1,
                     "deposits": int(dep.reindex(ids)["count"].sum()), "deposits_eur": float(dep.reindex(ids)["sum"].sum()),
                     "withdrawn_eur": float(wd.reindex(ids).sum())})
    return pd.DataFrame(rows).round(2)


# ---------------------------------------------------------------------------- screening and reviews
def screening_kpis(hits: pd.DataFrame, log: pd.DataFrame) -> dict:
    late = log[log["days_to_screen"] > C.SCREENING_SLA_DAYS]
    return {"hits": len(hits), "true_matches_confirmed": int((hits["decision"] == "true match").sum()),
            "false_positive_rate": float((hits["decision"] == "false positive").mean()),
            "new_clients_screened": len(log), "screened_late": len(late),
            "late_window": f"{late['onboarding_date'].min()} to {late['onboarding_date'].max()}" if len(late) else ""}


def screening_qa(hits: pd.DataFrame, min_score: float = 0.9) -> pd.DataFrame:
    """Second look at every sanctions hit closed as a false positive although the name scored high
    and the year of birth matched. Different birth years are a normal reason to discount a hit."""
    s = hits[(hits["list"] == "sanctions") & (hits["decision"] == "false positive") & (hits["match_score"] >= min_score)
             & hits["birth_year_match"]].copy()
    s["reviewer_finding"] = np.where(s["true_match"], "Wrongly closed: same person, spelling variant", "Closed correctly")
    return s


def overdue_reviews(clients: pd.DataFrame, as_of: str = C.END) -> pd.DataFrame:
    c = clients.copy()
    due = pd.to_datetime(c["last_review_date"]) + pd.to_timedelta(c["risk_rating"].map(C.PERIODIC_REVIEW_MONTHS) * 30.4, unit="D")
    c["review_due"] = due.dt.strftime("%Y-%m-%d")
    c["overdue"] = due < pd.Timestamp(as_of)
    return c.groupby("risk_rating").agg(clients=("client_id", "size"), overdue=("overdue", "sum")).reset_index()


# ---------------------------------------------------------------------------- KRIs
def rag(value: float, limits: tuple[float, float]) -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "n/a"
    amber, red = limits
    return "GREEN" if value <= amber else ("AMBER" if value <= red else "RED")


def kri_table(kpis: pd.DataFrame, comp: pd.DataFrame, qa: pd.DataFrame, log: pd.DataFrame, reviews: pd.DataFrame) -> pd.DataFrame:
    """Monthly KRIs with RAG status against risk appetite."""
    comp_m = comp.groupby("month")[["ledger_count", "missing_count"]].sum()
    qa_m = qa.assign(month=qa["l1_closed_date"].str[:7]).groupby("month")["decision_error"].agg(["sum", "size"])
    late_m = log.assign(month=log["onboarding_date"].str[:7]).groupby("month")["days_to_screen"].apply(lambda s: int((s > C.SCREENING_SLA_DAYS).sum()))
    overdue_high = int(reviews.set_index("risk_rating").loc["high", "overdue"])
    rows = []
    for r in kpis.itertuples():
        q = qa_m.loc[r.month] if r.month in qa_m.index else None
        vals = {
            "alerts_over_sla_pct": r.closed_over_sla_pct,
            "qa_error_rate": float(q["sum"] / q["size"]) if q is not None else np.nan,
            "missing_rationale_pct": r.missing_rationale_pct,
            "screening_late_count": int(late_m.get(r.month, 0)),
            "tm_feed_completeness_gap_pct": float(comp_m.loc[r.month, "missing_count"] / comp_m.loc[r.month, "ledger_count"]),
            "overdue_reviews_high_risk": overdue_high if r.month == C.MONTHS[-1] else np.nan,
            "median_days_alert_to_sar": r.median_days_alert_to_sar,
        }
        for k, v in vals.items():
            rows.append({"month": r.month, "kri": k, "value": v, "amber_limit": C.KRI_LIMITS[k][0],
                         "red_limit": C.KRI_LIMITS[k][1], "status": rag(v, C.KRI_LIMITS[k])})
    return pd.DataFrame(rows)


def findings_register(**ctx) -> pd.DataFrame:
    """The oversight findings for the period, each with severity, owner and a due date."""
    f = []
    comp, vc, cov, lookback, sqa, kpis, nets, reviews, log = (ctx[k] for k in
        ["comp", "vc", "cov", "lookback", "sqa", "kpis", "nets", "reviews", "log"])
    miss = comp[comp["missing_count"] > 0]
    if len(miss):
        f.append(("F01", "High", "TM data completeness",
                  f"{int(miss['missing_count'].sum())} card deposits (EUR {miss['missing_eur'].sum():,.0f}) from {C.FEED_GAP[2]} never reached transaction monitoring between {C.FEED_GAP[0]} and {C.FEED_GAP[1]}.",
                  "Back-load the missing transactions, re-run the rules for the period, add a daily ledger-to-feed reconciliation.", "Head of TM / IT"))
    if vc["change_pct"] < -0.3 and vc["p_value"] < 0.05:
        f.append(("F02", "High", "Rule governance",
                  f"R02 alert volume fell {abs(vc['change_pct']):.0%} from April 2026 (p = {vc['p_value']:.3f}); the vendor raised the deposit count from {C.R02_COUNT_BEFORE} to {C.R02_COUNT_AFTER} without an approved change request.",
                  "Restore the approved threshold, run a lookback on April to September, put rule parameters under change control.", "MLRO / TM vendor manager"))
    gaps = cov[cov["any_rule"] < 0.1]
    for t, share, n in zip(gaps["typology"], gaps["any_rule"], gaps["clients"]):
        f.append(("F03", "High", "Typology coverage",
                  f"No rule covers {t}: {len(nets)} networks of six clients share a payout account or device; only {round(share * n)} of {n} members alerted, for an unrelated reason.",
                  "Add a network rule on shared payout accounts and devices; refer the networks to investigations.", "MLRO"))
    if len(lookback):
        f.append(("F04", "High", "Alert decision quality",
                  f"QA found decision errors concentrated in analyst {C.WEAK_ANALYST}; a full lookback of the analyst's closures found {len(lookback)} cases that should have been escalated.",
                  "Re-open and investigate the cases, retrain the analyst, increase QA sampling for 3 months.", "Head of FCC operations"))
    wrong = sqa[sqa["true_match"]]
    if len(wrong):
        f.append(("F05", "Critical", "Sanctions screening",
                  f"{len(wrong)} sanctions hit with match score {wrong['match_score'].max():.2f} was closed as a false positive; reviewer judges it a true match (spelling variant).",
                  "Freeze the account, notify the MLRO immediately, assess reporting duties, review all closures above 0.90.", "MLRO"))
    over = kpis[kpis["closed_over_sla_pct"] > C.KRI_LIMITS["alerts_over_sla_pct"][1]]
    if len(over):
        f.append(("F06", "Medium", "Alert timeliness",
                  f"Alerts closed after more than {C.ALERT_SLA_DAYS} days reached {over['closed_over_sla_pct'].max():.0%} in {', '.join(over['month'])} (summer staffing).",
                  "Agree a backlog plan and holiday cover; report weekly until back within appetite.", "Head of FCC operations"))
    rat = kpis["missing_rationale_pct"].max()
    if rat > C.KRI_LIMITS["missing_rationale_pct"][1]:
        f.append(("F07", "Medium", "Documentation",
                  f"Closed alerts without a rationale peaked at {rat:.1%}; most come from analyst {C.SLOPPY_ANALYST}.",
                  "Make the rationale a mandatory field in the case system; coach the analyst.", "Head of FCC operations"))
    late = log[log["days_to_screen"] > C.SCREENING_SLA_DAYS]
    if len(late) > C.KRI_LIMITS["screening_late_count"][1]:
        f.append(("F08", "Medium", "Screening timeliness",
                  f"{len(late)} new clients were screened 4 to 7 days after onboarding during a batch outage ({C.SCREENING_OUTAGE[0]} to {C.SCREENING_OUTAGE[1]}).",
                  "Confirm all were screened with no true hits; add an alert on failed screening batches.", "Head of Onboarding / IT"))
    od = int(reviews.set_index("risk_rating").loc["high", "overdue"])
    if od > C.KRI_LIMITS["overdue_reviews_high_risk"][0]:
        f.append(("F09", "Medium", "Periodic reviews",
                  f"{od} high-risk clients are past their annual review date.",
                  "Prioritise the overdue high-risk reviews; restrict new activity until complete where policy requires.", "Head of KYC"))
    df = pd.DataFrame(f, columns=["finding_id", "severity", "area", "observation", "action", "owner"])
    order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
    df = df.sort_values("severity", key=lambda s: s.map(order)).reset_index(drop=True)
    df["due"] = df["severity"].map({"Critical": "immediately", "High": "2026-11-30", "Medium": "2026-12-31"})
    df["status"] = "open"
    return df
