"""Find the passages that answer a question, for one user role.

Access control comes first: passages the role may not read are removed before anything is ranked,
so they cannot leak through scores, snippets or citations.

Retrievers
    bm25      classic keyword ranking (Okapi BM25), implemented here in a few lines
    tfidf     cosine similarity on word and character n-gram TF-IDF (robust to typos and word forms)
    hybrid    reciprocal rank fusion of the two (Cormack et al. 2009), with synonym expansion

Every retriever returns a confidence for the best passage, used to decide whether to answer at all.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.sparse import hstack
from sklearn.feature_extraction.text import TfidfVectorizer

from .config import ROLE_LEVEL
from .corpus import Passage
from .text import expand, tokens


@dataclass
class Hit:
    passage: Passage
    score: float
    rank: int


def visible(passages: list[Passage], role: str) -> list[int]:
    if role not in ROLE_LEVEL:
        raise ValueError(f"unknown role {role!r}")
    lvl = ROLE_LEVEL[role]
    return [i for i, p in enumerate(passages) if ROLE_LEVEL[p.audience] <= lvl]


def _doc(p: Passage) -> str:
    # title and section heading are strong signals, so they are repeated in the indexed text
    return f"{p.title} {p.section} {p.section} {p.text}"


class BM25:
    def __init__(self, docs: list[str], k1: float = 1.4, b: float = 0.7):
        self.toks = [tokens(d) for d in docs]
        self.k1, self.b = k1, b
        self.len = np.array([len(t) for t in self.toks], float)
        self.avg = self.len.mean()
        vocab = sorted({w for t in self.toks for w in t})
        self.idx = {w: i for i, w in enumerate(vocab)}
        self.tf = np.zeros((len(docs), len(vocab)))
        for d, t in enumerate(self.toks):
            for w in t:
                self.tf[d, self.idx[w]] += 1
        df = (self.tf > 0).sum(axis=0)
        self.idf = np.log(1 + (len(docs) - df + 0.5) / (df + 0.5))

    def scores(self, query: str) -> np.ndarray:
        q = [self.idx[w] for w in tokens(query) if w in self.idx]
        if not q:
            return np.zeros(len(self.toks))
        tf = self.tf[:, q]
        denom = tf + self.k1 * (1 - self.b + self.b * self.len[:, None] / self.avg)
        return (self.idf[q] * tf * (self.k1 + 1) / denom).sum(axis=1)


class Retriever:
    def __init__(self, passages: list[Passage], method: str = "hybrid", synonyms: bool = True):
        if method not in ("bm25", "tfidf", "hybrid"):
            raise ValueError(method)
        self.passages, self.method, self.synonyms = passages, method, synonyms
        docs = [_doc(p) for p in passages]
        self.bm25 = BM25(docs)
        self.word = TfidfVectorizer(tokenizer=tokens, lowercase=False, token_pattern=None, ngram_range=(1, 2), sublinear_tf=True)
        self.char = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True, min_df=1)
        self.Xw = self.word.fit_transform(docs)
        self.Xc = self.char.fit_transform(docs)

    def _tfidf(self, q: str) -> np.ndarray:
        sw = (self.Xw @ self.word.transform([q]).T).toarray().ravel()
        sc = (self.Xc @ self.char.transform([q]).T).toarray().ravel()
        return 0.6 * sw + 0.4 * sc

    def search(self, question: str, role: str = "employee", k: int = 4) -> tuple[list[Hit], float]:
        """Top-k passages the role may read, and a confidence in [0, 1] for the best one."""
        allowed = np.array(visible(self.passages, role))
        q = expand(question) if self.synonyms else question
        tf = self._tfidf(q)[allowed]
        if self.method == "tfidf":
            score = tf
        else:
            bm = self.bm25.scores(q)[allowed]
            if self.method == "bm25":
                score = bm
            else:
                r_bm = np.argsort(np.argsort(-bm))
                r_tf = np.argsort(np.argsort(-tf))
                score = 1 / (60 + r_bm) + 1 / (60 + r_tf)
        order = np.argsort(-score)[:k]
        hits = [Hit(self.passages[allowed[i]], float(score[i]), r + 1) for r, i in enumerate(order)]
        confidence = float(tf.max()) if len(tf) else 0.0          # cosine scale is comparable across queries
        return hits, confidence
