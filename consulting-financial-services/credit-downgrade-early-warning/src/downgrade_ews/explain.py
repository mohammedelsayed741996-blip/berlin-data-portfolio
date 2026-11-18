"""Explanations an analyst or client can read: which words, which articles, which features."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score

from . import models as M


MASKS = {"co", "num", "sector", "city", "quarter", "year"}
STOP = {"the", "a", "an", "of", "on", "in", "to", "for", "and", "its", "at", "by", "with", "as", "is", "was", "this",
        "that", "next", "within", "from", "it", "be", "has", "are", "after", "eur", "million", "der", "die", "das", "und",
        "im", "für", "von", "mit", "den", "des", "auf", "bei", "um", "eine", "ein", "zur", "zum", "hat", "wurde", "euro",
        "millionen"}


def readable(term: str) -> bool:
    words = term.split()
    return not any(w in MASKS for w in words) and not all(w in STOP for w in words)


def word_weights(text_model) -> pd.DataFrame:
    """Logistic regression weights of the word and phrase features (character n-grams left out for readability)."""
    vec = text_model.named_steps["tfidf"]
    coef = text_model.named_steps["clf"].coef_[0]
    words = vec.transformer_list[0][1]
    names = words.get_feature_names_out()
    w = pd.DataFrame({"term": names, "weight": coef[: len(names)]})
    return w.sort_values("weight", ascending=False).reset_index(drop=True)


def top_terms(text_model, n: int = 15, language: str | None = None) -> pd.DataFrame:
    w = word_weights(text_model)
    w = w[w["term"].map(readable)]
    de_hint = r"ä|ö|ü|ß|\b(?:der|die|das|und|mit|für|von|zur|des|im|bei|auf|wird)\b|ung\b|keit\b|lich\b"
    if language == "de":
        w = w[w["term"].str.contains(de_hint, regex=True)]
    elif language == "en":
        w = w[~w["term"].str.contains(de_hint, regex=True)]
    return pd.concat([w.head(n).assign(direction="raises risk"), w.tail(n).iloc[::-1].assign(direction="lowers risk")])


def article_reasons(text_model, text: str, n: int = 4) -> list[str]:
    """Words and phrases in one article that pushed its score up the most."""
    vec = text_model.named_steps["tfidf"].transformer_list[0][1]
    coef = text_model.named_steps["clf"].coef_[0][: len(vec.get_feature_names_out())]
    x = vec.transform([text.lower()])
    contrib = x.multiply(coef).tocsr()
    idx = contrib.indices[np.argsort(contrib.data)[::-1]]
    names = vec.get_feature_names_out()
    out = []
    for i in idx:
        term = names[i]
        if not readable(term) or any(term in o or o in term for o in out):
            continue
        if contrib[0, i] <= 0:
            break
        out.append(term)
        if len(out) == n:
            break
    return out


def issuer_evidence(scored: pd.DataFrame, issuer_id: str, month: str, text_model, n: int = 3) -> pd.DataFrame:
    """The articles that drive an alert: the highest-scoring news of the last three months."""
    start = (pd.Period(month, freq="M") - 2).strftime("%Y-%m")
    a = scored[(scored["issuer_id"] == issuer_id) & (scored["date"].str[:7] >= start) & (scored["date"].str[:7] <= month)]
    a = a.nlargest(n, "p_article")[["date", "language", "source", "headline", "p_article", "text"]].copy()
    a["why"] = [", ".join(article_reasons(text_model, t)) for t in a["text"]]
    return a.drop(columns="text")


def feature_group_importance(result: M.Result, test: pd.DataFrame, seed: int = 0) -> pd.DataFrame:
    """Drop in PR-AUC when each feature group is shuffled together on the test set."""
    groups = {"Rating and outlook": M.RATING, "Financials and share price": M.FINANCIAL,
              "Keyword counts": M.KEYWORD, "NLP news scores": M.NLP}
    X = test[result.features]
    base = average_precision_score(test["y"], result.model.predict_proba(X)[:, 1])
    rng = np.random.default_rng(seed)
    rows = []
    for g, cols in groups.items():
        cols = [c for c in cols if c in result.features]
        drops = []
        for _ in range(10):
            Xp = X.copy()
            perm = rng.permutation(len(Xp))
            Xp[cols] = Xp[cols].values[perm]
            drops.append(base - average_precision_score(test["y"], result.model.predict_proba(Xp)[:, 1]))
        rows.append({"feature_group": g, "pr_auc_drop": float(np.mean(drops)), "sd": float(np.std(drops))})
    return pd.DataFrame(rows).sort_values("pr_auc_drop", ascending=False).round(4)
