"""Model validation beyond one AUC number.

Behavioural tests check the text model the way you would test a chatbot or any
language model a bank wants to rely on: does it ignore the company name, does
it notice a denial, does a red flag raise the score, does it hold up on wording
it has never seen? The rest checks stability across languages and sectors and
calibration.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score

# Hand-written sentences that do not appear in the news templates.
NEGATION_PAIRS = [
    ("[co] faces liquidity problems as cash runs low.", "[co] denies it faces liquidity problems; cash is ample."),
    ("[co] is struggling to refinance its bonds.", "[co] says it has no difficulty refinancing its bonds."),
    ("Banks are concerned about a covenant breach at [co].", "[co] is comfortably within all covenants, banks say."),
    ("[co] hat Liquiditätsprobleme.", "[co] weist Berichte über Liquiditätsprobleme zurück."),
    ("[co] kann die Anleihe kaum refinanzieren.", "[co] hat die Refinanzierung bereits gesichert."),
]

DIRECTIONAL = [
    ("[co] reported quarterly results.", "[co] reported quarterly results and issued a profit warning."),
    ("[co] held its annual general meeting.", "[co] held its annual general meeting; the chief financial officer resigned."),
    ("[co] meldet Zahlen für das Quartal.", "[co] meldet Zahlen für das Quartal und senkt die Prognose."),
]

UNSEEN = [  # (text, 1 = credit risk, 0 = no credit risk); paraphrases the templates never use
    ("[co] said cash would only last until the spring unless lenders agree to new terms.", 1),
    ("Suppliers of [co] are demanding payment in advance.", 1),
    ("[co] hired restructuring advisers to talk to bondholders.", 1),
    ("Earnings at [co] collapsed and the company burned through cash.", 1),
    ("[co] ist mit der Tilgung eines Kredits in Verzug.", 1),
    ("Lieferanten von [co] verlangen Vorkasse.", 1),
    ("[co] opened a new research centre and is hiring engineers.", 0),
    ("[co] paid back a loan early from strong cash flow.", 0),
    ("Orders at [co] reached a record high.", 0),
    ("[co] eröffnet ein neues Werk und stellt Personal ein.", 0),
    ("[co] zahlt einen Kredit vorzeitig zurück.", 0),
    ("[co] wins a long-term supply deal with a carmaker.", 0),
]


def score_text(text_model, texts: list[str]) -> np.ndarray:
    """Score raw sentences with the same masking the model was trained with."""
    from .features import article_text
    df = pd.DataFrame({"issuer_id": "X", "headline": texts, "body": ""})
    masked = article_text(df, pd.DataFrame({"issuer_id": ["X"], "issuer_name": ["[co]"]}))
    return text_model.predict_proba(masked.str.rstrip(". "))[:, 1]


def behavioural_tests(text_model, issuers: pd.DataFrame) -> pd.DataFrame:
    p = lambda texts: score_text(text_model, texts)  # noqa: E731
    rows = []
    # 1. The company name does not change the score (names are masked before scoring).
    names = issuers["issuer_name"].head(20).tolist()
    base = "{} issues profit warning, cuts full-year outlook."
    from .features import mask_issuer
    texts = mask_issuer(pd.Series([base.format(n) for n in names]), pd.Series(names))
    s = p(texts.tolist())
    rows.append({"test": "Invariance: 20 company names", "passed": f"{int(np.ptp(s) < 1e-9) * 20}/20",
                 "detail": f"score range {np.ptp(s):.2e}"})
    # 2. Negation and denial lowers the score.
    neg = [(p([a])[0], p([b])[0]) for a, b in NEGATION_PAIRS]
    ok = sum(b < a for a, b in neg)
    rows.append({"test": "Negation: denial scores lower than the problem", "passed": f"{ok}/{len(neg)}",
                 "detail": "; ".join(f"{a:.2f}->{b:.2f}" for a, b in neg)})
    # 3. Adding a red flag raises the score.
    di = [(p([a])[0], p([b])[0]) for a, b in DIRECTIONAL]
    ok = sum(b > a for a, b in di)
    rows.append({"test": "Directional: red flag raises score", "passed": f"{ok}/{len(di)}",
                 "detail": "; ".join(f"{a:.2f}->{b:.2f}" for a, b in di)})
    # 4. Unseen wording.
    s = p([t for t, _ in UNSEEN])
    y = np.array([l for _, l in UNSEEN])
    thr = 0.5
    ok = int(((s > thr) == (y == 1)).sum())
    rows.append({"test": "Unseen paraphrases classified correctly", "passed": f"{ok}/{len(UNSEEN)}",
                 "detail": f"AUC {roc_auc_score(y, s):.2f}"})
    return pd.DataFrame(rows)


def unseen_detail(text_model) -> pd.DataFrame:
    s = score_text(text_model, [t for t, _ in UNSEEN])
    return pd.DataFrame({"sentence": [t for t, _ in UNSEEN], "label": [l for _, l in UNSEEN], "score": s.round(3)})


def by_language(scored: pd.DataFrame, test_start: str) -> pd.DataFrame:
    s = scored[(scored["date"].str[:7] >= test_start) & scored["y"].notna()]
    rows = []
    for lang, g in s.groupby("language"):
        rows.append({"language": lang, "articles": len(g), "positive_share": g["y"].mean(),
                     "roc_auc": roc_auc_score(g["y"], g["p_article"]), "pr_auc": average_precision_score(g["y"], g["p_article"])})
    return pd.DataFrame(rows).round(3)


def by_segment(test: pd.DataFrame, scores: pd.Series, col: str = "sector") -> pd.DataFrame:
    t = test.assign(score=scores)
    rows = []
    for seg, g in t.groupby(col):
        if g["y"].nunique() < 2:
            rows.append({col: seg, "rows": len(g), "downgrade_rate": g["y"].mean(), "roc_auc": np.nan, "pr_auc": np.nan})
            continue
        rows.append({col: seg, "rows": len(g), "downgrade_rate": g["y"].mean(),
                     "roc_auc": roc_auc_score(g["y"], g["score"]), "pr_auc": average_precision_score(g["y"], g["score"])})
    return pd.DataFrame(rows).round(3)


def calibration(test: pd.DataFrame, scores: pd.Series, bins: int = 10) -> pd.DataFrame:
    t = test.assign(score=scores)
    t["bucket"] = pd.qcut(t["score"].rank(method="first"), bins, labels=False)
    return t.groupby("bucket").agg(mean_score=("score", "mean"), observed=("y", "mean"), rows=("y", "size")).round(4)


def topic_scores(scored: pd.DataFrame, test_start: str) -> pd.DataFrame:
    """Average article score by the hidden true topic (test period), next to how often the issuer was
    actually downgraded within three months. The model never saw the topic labels."""
    from .news import NEGATIVE, NEUTRAL, NOISE, POSITIVE
    group = {**{t: "negative" for t in NEGATIVE}, **{t: "noise" for t in NOISE}, **{t: "neutral" for t in NEUTRAL},
             **{t: "positive" for t in POSITIVE}, "rating_outlook_negative": "agency", "rating_downgrade": "agency",
             "rating_outlook_positive": "agency"}
    s = scored[(scored["date"].str[:7] >= test_start) & scored["y"].notna()]
    out = s.groupby("true_topic").agg(articles=("article_id", "size"), mean_score=("p_article", "mean"),
                                      downgraded_within_3m=("y", "mean")).reset_index()
    out["group"] = out["true_topic"].map(group)
    return out.sort_values("mean_score", ascending=False).round(3).reset_index(drop=True)
