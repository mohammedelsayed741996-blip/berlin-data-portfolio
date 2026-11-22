"""Search the policy documents. Results are returned as untrusted data, never as instructions.

Each passage is wrapped with a marker so a model can tell document text from user and system text.
The guard does not rely on that: any action a document asks for still needs a permitted tool call
and, for side effects, a human approval (ADR 0003).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml
from sklearn.feature_extraction.text import TfidfVectorizer

INJECTION = re.compile(r"ignore (all )?(previous|prior) instructions|you are now|maintenance mode|send (them|it|all) to|"
                       r"approve all|disregard (the )?(rules|policy)", re.I)


@dataclass
class Passage:
    doc_id: str
    title: str
    section: str
    text: str

    @property
    def suspicious(self) -> bool:
        return bool(INJECTION.search(self.text))


def load(folder: Path) -> list[Passage]:
    out = []
    for f in sorted(folder.glob("*.md")):
        m = re.match(r"^---\n(.*?)\n---\n(.*)$", f.read_text(), re.S)
        meta, body = yaml.safe_load(m.group(1)), m.group(2)
        parts = re.split(r"^## +(.+)$", body, flags=re.M)
        for h, t in zip(parts[1::2], parts[2::2]):
            out.append(Passage(meta["doc_id"], meta["title"], h.strip(), " ".join(t.split())))
    return out


class DocSearch:
    def __init__(self, folder: Path):
        self.passages = load(folder)
        self.vec = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, stop_words="english")
        self.X = self.vec.fit_transform([f"{p.title} {p.section} {p.text}" for p in self.passages])

    def search(self, query: str, k: int = 3) -> list[dict]:
        s = (self.X @ self.vec.transform([query]).T).toarray().ravel()
        order = s.argsort()[::-1][:k]
        return [{"doc_id": self.passages[i].doc_id, "title": self.passages[i].title, "section": self.passages[i].section,
                 "score": round(float(s[i]), 3), "suspicious_instructions": self.passages[i].suspicious,
                 "text": f"<document untrusted=\"true\">{self.passages[i].text}</document>"} for i in order if s[i] > 0]
