"""Evaluate the assistant on the hand-written question set (eval/gold.jsonl).

Measures
    retrieval   hit@1, hit@3 and MRR for questions that have an answer in the policies
    answers     share answered correctly: the answer cites the expected passage and contains every
                expected fact (a number, a date or a key phrase)
    declining   share of out-of-scope questions and permission probes that were declined, and the
                share of answerable questions wrongly declined
    leaks       citations of passages above the user's role: must be zero
    latency     median and 95th percentile per question

The confidence threshold for declining is tuned on the dev split only. Results are reported on the
test split, so the numbers are not fitted to the questions they are measured on.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from .answer import Assistant
from .config import ROLE_LEVEL, ROOT, Settings
from .corpus import Passage, load
from .retrieval import Retriever

GOLD = ROOT / "eval" / "gold.jsonl"


def gold(path: Path = GOLD) -> pd.DataFrame:
    return pd.DataFrame([json.loads(line) for line in path.read_text().splitlines() if line.strip()])


def run(assistant: Assistant, g: pd.DataFrame, passages: list[Passage]) -> pd.DataFrame:
    audience = {p.pid: p.audience for p in passages}
    rows = []
    for r in g.itertuples():
        expected = r.expected if isinstance(r.expected, str) else None
        hits, conf = assistant.r.search(r.question, role=r.role, k=10)
        ranked = [h.passage.pid for h in hits]
        a = assistant.ask(r.question, role=r.role)
        cited = [c["pid"] for c in a.citations]
        text = a.text.lower()
        rows.append({
            "id": r.id, "split": r.split, "role": r.role, "question": r.question, "expected": expected,
            "should_answer": expected is not None, "answered": a.answered, "confidence": conf,
            "rank": ranked.index(expected) + 1 if expected in ranked else None,
            "cited_expected": expected in cited,
            "facts_ok": all(f.lower() in text for f in r.must_include) if expected else None,
            "leak": any(ROLE_LEVEL[audience[c]] > ROLE_LEVEL[r.role] for c in cited),
            "latency_ms": a.latency_ms, "answer": a.text, "citations": ";".join(cited),
        })
    return pd.DataFrame(rows)


def metrics(res: pd.DataFrame) -> dict:
    ans = res[res["should_answer"]]
    dec = res[~res["should_answer"]]
    rank = ans["rank"].fillna(99)
    correct = ans["answered"] & ans["cited_expected"] & ans["facts_ok"].astype(bool)
    return {
        "questions": len(res), "answerable": len(ans), "should_decline": len(dec),
        "hit_at_1": float((rank <= 1).mean()), "hit_at_3": float((rank <= 3).mean()), "mrr": float((1 / rank).mean()),
        "answer_correct": float(correct.mean()),
        "answer_cites_expected": float((ans["answered"] & ans["cited_expected"]).mean()),
        "wrongly_declined": float((~ans["answered"]).mean()),
        "decline_rate_when_should": float((~dec["answered"]).mean()) if len(dec) else float("nan"),
        "leaks": int(res["leak"].sum()),
        "latency_p50_ms": float(res["latency_ms"].median()), "latency_p95_ms": float(res["latency_ms"].quantile(0.95)),
    }


def calibrate(res_dev: pd.DataFrame, grid=np.round(np.arange(0.10, 0.36, 0.01), 2)) -> tuple[float, pd.DataFrame]:
    """Pick the decline threshold on dev: maximise correct answers plus correct declines (equal weight)."""
    rows = []
    for t in grid:
        answer = res_dev["confidence"] >= t
        ok_ans = (answer & res_dev["should_answer"] & res_dev["cited_expected"] & res_dev["facts_ok"].map(bool))
        ok_dec = (~answer & ~res_dev["should_answer"])
        a, d = res_dev["should_answer"].sum(), (~res_dev["should_answer"]).sum()
        rows.append({"threshold": float(t), "answer_correct": float(ok_ans.sum() / a), "declined_correctly": float(ok_dec.sum() / d),
                     "score": float(ok_ans.sum() / a + ok_dec.sum() / d)})
    tab = pd.DataFrame(rows)
    best = tab.loc[tab["score"].idxmax(), "threshold"]
    return float(best), tab


def ablation(passages: list[Passage], g: pd.DataFrame, split: str = "dev") -> pd.DataFrame:
    rows = []
    for method in ("bm25", "tfidf", "hybrid"):
        for syn in (False, True):
            s = Settings(min_score=0.0)
            a = Assistant(Retriever(passages, method, synonyms=syn), s)
            m = metrics(run(a, g[g["split"] == split], passages))
            rows.append({"retriever": method, "synonyms": syn, **{k: m[k] for k in ("hit_at_1", "hit_at_3", "mrr", "answer_correct")}})
    return pd.DataFrame(rows)


def full(passages: list[Passage] | None = None, method: str = "hybrid") -> dict:
    passages = passages or load(Settings().policies_dir)
    g = gold()
    r = Retriever(passages, method)
    raw = run(Assistant(r, Settings(min_score=0.0)), g[g["split"] == "dev"], passages)
    thr, curve = calibrate(raw)
    a = Assistant(r, Settings(min_score=thr))
    res = run(a, g, passages)
    return {"threshold": thr, "calibration": curve, "results": res,
            "dev": metrics(res[res["split"] == "dev"]), "test": metrics(res[res["split"] == "test"]), "all": metrics(res)}
