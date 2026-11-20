"""Pre-registered data-quality rules, applied before any model sees the data.

Q1  duplicate submissions: keep the first submission of each participant code
Q2  catch trials: exclude anyone who picks the smaller, later option in 2 or more of 4
Q3  speed: exclude anyone whose median response time is under 450 ms
Q4  straightlining: flag anyone who gives the same answer on all 60 real trials (reported, Q2 removes them)
Q5  balance: conditions should stay balanced after exclusions (chi-square test)
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats

from . import config as C


@dataclass
class Rule:
    rule_id: str
    name: str
    flagged: list
    detail: str


def apply(tables: dict) -> tuple[pd.DataFrame, pd.DataFrame, list[Rule]]:
    tr = tables["trials"]
    rules = []
    dup = sorted(tr.loc[tr["submission"] > 1, "pid"].unique())
    rules.append(Rule("Q1", "Duplicate submissions (second attempt dropped)", dup, f"{len(dup)} codes submitted twice"))
    first = tr[tr["submission"] == 1]

    fails = first[first["catch"]].groupby("pid")["choice_ll"].sum()
    q2 = sorted(fails[fails > C.MAX_CATCH_FAILS].index)
    rules.append(Rule("Q2", "Failed 2 or more of 4 catch trials", q2, f"distribution of fails: {fails.value_counts().sort_index().to_dict()}"))

    med = first.groupby("pid")["rt_ms"].median()
    q3 = sorted(med[med < C.MIN_MEDIAN_RT_MS].index)
    rules.append(Rule("Q3", f"Median response time under {C.MIN_MEDIAN_RT_MS} ms", q3, f"fastest median {int(med.min())} ms"))

    real = first[~first["catch"]].groupby("pid")["choice_ll"].agg(["mean"])
    q4 = sorted(real[(real["mean"] == 0) | (real["mean"] == 1)].index)
    rules.append(Rule("Q4", "Same answer on all 60 real trials", q4, "flag only"))

    excluded = sorted(set(q2) | set(q3))
    keep = first[~first["pid"].isin(excluded)]
    ppl = tables["participants"]
    ppl = ppl[(ppl["submission"] == 1)]
    before = ppl["condition"].value_counts()
    after = ppl[~ppl["pid"].isin(excluded)]["condition"].value_counts()
    p = stats.chi2_contingency(np.array([before.values, after.values]))[1]
    rules.append(Rule("Q5", "Conditions balanced after exclusions", [], f"delay/date before {before.get('delay')}/{before.get('date')}, after {after.get('delay')}/{after.get('date')}, p = {p:.2f}"))

    log = pd.DataFrame([{"rule": r.rule_id, "check": r.name, "participants": len(r.flagged), "detail": r.detail} for r in rules])
    clean = keep[~keep["catch"]].reset_index(drop=True)
    return clean, log, rules


def flow(tables: dict, rules: list[Rule]) -> pd.DataFrame:
    """CONSORT-style participant flow for the paper."""
    total = tables["participants"]["pid"].nunique()
    subs = len(tables["participants"])
    q2, q3 = set(rules[1].flagged), set(rules[2].flagged)
    rows = [("Submissions received", subs), ("Unique participant codes", total),
            ("Excluded: catch trials only", len(q2 - q3)), ("Excluded: too fast only", len(q3 - q2)),
            ("Excluded: both", len(q2 & q3)), ("Analysed", total - len(q2 | q3))]
    return pd.DataFrame(rows, columns=["step", "n"])
