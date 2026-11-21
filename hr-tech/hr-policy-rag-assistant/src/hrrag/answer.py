"""Turn retrieved passages into an answer with citations, or decline.

Two answerers share one interface:

ExtractiveAnswerer (default, no external service)
    Picks the sentences from the top passages that best match the question and quotes them with
    numbered citations. It never says anything that is not in a policy, which makes it a safe
    baseline and lets the whole system run offline, in CI and in a locked-down network.

LLMAnswerer (optional)
    Sends the question and the numbered passages to any OpenAI-compatible chat endpoint, with
    instructions to answer only from the passages and cite them. The reply is checked: if it cites
    nothing, or cites a passage it was not given, the extractive answer is returned instead.

Both decline when retrieval confidence is low, and point the user to HR.
"""

from __future__ import annotations

import json
import re
import time
import urllib.request
from dataclasses import dataclass, field

from .config import Settings
from .retrieval import Hit, Retriever
from .text import expand, tokens

DECLINE = ("I could not find this in the HR policies I have access to. Please ask your HR business partner "
           "or open a ticket in the HR portal.")


@dataclass
class Answer:
    text: str
    citations: list[dict] = field(default_factory=list)
    answered: bool = True
    confidence: float = 0.0
    engine: str = "extractive"
    latency_ms: float = 0.0

    def to_dict(self) -> dict:
        return {"answer": self.text, "citations": self.citations, "answered": self.answered,
                "confidence": round(self.confidence, 3), "engine": self.engine, "latency_ms": round(self.latency_ms, 1)}


NUMERIC_INTENT = re.compile(r"\b(how (many|much|long|far|early|fast|wide|soon)|when|until|by when|what time|percent|percentage|rate|limit|max|minimum|budget|allowance|per diem|zuschlag|hours?|days?)\b", re.I)
HAS_NUMBER = re.compile(r"\d|\b(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|fifteen|twenty|half|twelfth|first|second|third|fourth)\b", re.I)


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", text) if s.strip()]


def _cite(hit: Hit, n: int) -> dict:
    p = hit.passage
    return {"n": n, "pid": p.pid, "policy_id": p.policy_id, "title": p.title, "section": p.section,
            "version": p.version, "effective_date": p.effective_date, "source": p.source}


class ExtractiveAnswerer:
    name = "extractive"

    def __init__(self, max_sentences: int = 2, idf: dict | None = None):
        self.max_sentences, self.idf = max_sentences, idf or {}

    def _weight(self, words: set) -> float:
        return sum(self.idf.get(w, 1.0) for w in words)

    def compose(self, question: str, hits: list[Hit]) -> tuple[str, list[dict]]:
        """Quote the best-matching sentences, weighting rare words more (idf), mostly from the top passage."""
        q = set(tokens(expand(question)))
        numeric = bool(NUMERIC_INTENT.search(question))
        candidates = []
        for h_i, h in enumerate(hits[:2]):
            for s_i, s in enumerate(_sentences(h.passage.text)):
                score = self._weight(q & set(tokens(s)))
                if numeric and HAS_NUMBER.search(s):
                    score += 3.0                     # the question asks for a number, a date or a duration
                if h_i == 1:
                    score -= 3.0 if h.passage.policy_id == hits[0].passage.policy_id else 6.0
                candidates.append((score - 0.05 * s_i, h_i, s_i, s))
        candidates.sort(key=lambda c: -c[0])
        best = candidates[0][0]
        # second sentence only if it is nearly as relevant as the first
        picked = [c for c in candidates[: self.max_sentences] if c is candidates[0] or c[0] >= 0.6 * best]
        picked = sorted(picked, key=lambda c: (c[1], c[2]))
        used = sorted({c[1] for c in picked})
        num = {h_i: n + 1 for n, h_i in enumerate(used)}
        text = " ".join(f"{c[3]} [{num[c[1]]}]" for c in picked)
        return text, [_cite(hits[h_i], num[h_i]) for h_i in used]


class LLMAnswerer:
    name = "llm"

    def __init__(self, settings: Settings, transport=None, timeout: float = 20.0):
        self.s, self.timeout = settings, timeout
        self.transport = transport or self._http
        self.fallback = ExtractiveAnswerer()

    def _http(self, payload: dict) -> dict:
        req = urllib.request.Request(self.s.llm_base_url.rstrip("/") + "/chat/completions", data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.s.llm_api_key}"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.loads(r.read())

    @staticmethod
    def prompt(question: str, hits: list[Hit]) -> list[dict]:
        ctx = "\n\n".join(f"[{i + 1}] {h.passage.title}, section {h.passage.section}:\n{h.passage.text}" for i, h in enumerate(hits))
        system = ("You answer employees' questions about company HR policies. Use only the numbered passages. "
                  "Cite every statement with its passage number in square brackets, like [1]. Keep the answer under 80 words. "
                  "If the passages do not contain the answer, reply exactly: NOT_FOUND. Never guess numbers or dates.")
        return [{"role": "system", "content": system}, {"role": "user", "content": f"Passages:\n{ctx}\n\nQuestion: {question}"}]

    def compose(self, question: str, hits: list[Hit]) -> tuple[str, list[dict]]:
        try:
            out = self.transport({"model": self.s.llm_model, "temperature": 0, "messages": self.prompt(question, hits)})
            text = out["choices"][0]["message"]["content"].strip()
        except Exception:                                                     # network, auth, format: fall back
            return self.fallback.compose(question, hits)
        if text == "NOT_FOUND":
            return "", []
        cited = sorted({int(n) for n in re.findall(r"\[(\d+)\]", text)})
        if not cited or any(n < 1 or n > len(hits) for n in cited):          # guardrail: must cite real passages
            return self.fallback.compose(question, hits)
        return text, [_cite(hits[n - 1], n) for n in cited]


class Assistant:
    def __init__(self, retriever: Retriever, settings: Settings | None = None, answerer=None):
        self.r, self.s = retriever, settings or Settings()
        if answerer is not None:
            self.a = answerer
        elif self.s.llm_base_url and self.s.llm_model:
            self.a = LLMAnswerer(self.s)
        else:
            self.a = ExtractiveAnswerer()
        idf = {w: float(self.r.bm25.idf[i]) for w, i in self.r.bm25.idx.items()}
        for a in (self.a, getattr(self.a, "fallback", None)):
            if isinstance(a, ExtractiveAnswerer):
                a.idf = idf

    def ask(self, question: str, role: str = "employee") -> Answer:
        t0 = time.perf_counter()
        question = (question or "").strip()[:500]
        if len(tokens(question)) == 0:
            return Answer(DECLINE, answered=False, engine=self.a.name, latency_ms=(time.perf_counter() - t0) * 1000)
        hits, conf = self.r.search(question, role=role, k=self.s.top_k)
        if conf < self.s.min_score or not hits:
            return Answer(DECLINE, answered=False, confidence=conf, engine=self.a.name, latency_ms=(time.perf_counter() - t0) * 1000)
        text, cites = self.a.compose(question, hits)
        if not text:
            return Answer(DECLINE, answered=False, confidence=conf, engine=self.a.name, latency_ms=(time.perf_counter() - t0) * 1000)
        return Answer(text, cites, True, conf, self.a.name, (time.perf_counter() - t0) * 1000)
