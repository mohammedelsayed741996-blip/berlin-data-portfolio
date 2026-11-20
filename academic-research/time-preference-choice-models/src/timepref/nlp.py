"""Future orientation in social-media text: a synthetic pilot for the real-world data stream.

The question: does everyday talk about money lean towards now or later, and does that shift over
the year (Black Friday, the December spending season, New Year resolutions, payday)?

Posts are generated from templates, so they are fictional and contain no personal data. Authors
are random codes. Each post has a true orientation: present, future or neutral. A weekly pattern
is built in so the index can be checked against the truth.

Pipeline
1. Two simulated annotators label 900 posts; agreement is measured with Cohen's kappa and
   disagreements are settled by a third label (adjudication).
2. A word-list baseline (counts of future vs present words) is compared with TF-IDF + logistic
   regression on a held-out test set.
3. The classifier labels 15,000 unlabelled posts, including phrasings that did not exist when the
   labelled sample was drawn, and a weekly future-orientation index is compared with the truth.
   Adjusting the counts for classifier error was tried and dropped: with a neutral class that is
   rarely predicted, the error matrix is close to singular and the correction makes things worse.
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import cohen_kappa_score, confusion_matrix, f1_score
from sklearn.model_selection import train_test_split

from . import config as C

LABELS = ("present", "future", "neutral")

ITEMS = ["sneakers", "headphones", "phone", "jacket", "concert tickets", "game console", "laptop", "coffee machine", "watch", "bike"]
GOALS = ["a trip next summer", "my emergency fund", "a flat deposit", "my pension", "a new bike in spring", "my master's fees",
         "a car next year", "a rainy-day pot", "a holiday in August", "retirement"]
AMOUNTS = ["20", "30", "50", "75", "100", "150", "200", "250"]

TEMPLATES = {
    "present": [
        "just bought the {item}, couldn't wait for the sale",
        "treat yourself, life is short. ordered the {item} today",
        "payday means {item} time, no regrets",
        "why wait? got the {item} right now",
        "no point saving this month, buying the {item} now",
        "impulse buy of the week: {item}",
        "saw the {item} and had to have it today",
        "spent {amount} on {item} instantly, worth it",
        "forget saving for {goal}, I want the {item} now",
        "honestly can't be bothered to budget, ordered the {item}",
    ],
    "future": [
        "putting {amount} aside every month for {goal}",
        "skipped the {item} today, saving for {goal} instead",
        "set up a standing order of {amount} for {goal}",
        "waiting for next year to buy the {item}, saving first",
        "new rule: 48 hours before any purchase. saved {amount} already",
        "my future self will thank me for saving for {goal}",
        "slowly building {goal}, {amount} at a time",
        "said no to the {item}, the money goes to {goal}",
        "planning ahead: {amount} a week into {goal}",
        "not buying the {item} now, it can wait",
    ],
    "neutral": [
        "anyone know a good bank for students in Berlin",
        "prices for {item} seem higher than last year",
        "comparing two offers for a {item}, both around {amount}",
        "is the {item} worth {amount} or overpriced",
        "my rent went up again this month",
        "reading a book about how money works",
        "which app do you use to track spending",
        "got a refund of {amount} for the {item}",
        "the shop on the corner sells {item} now",
        "does anyone split bills with a shared account",
    ],
}

# phrasings that appear only after the labelled sample was drawn (language drift)
UNSEEN = {
    "present": ["yolo, the {item} is mine", "my bank account is crying but the {item} arrived",
                "black friday got me again, {item} in the basket", "couldn't resist, {item} delivered tomorrow",
                "one-click checkout is dangerous. new {item}"],
    "future": ["no-spend month, day 12. {goal} is growing", "the {item} stays in the wishlist until {goal} is done",
               "automated {amount} into {goal} on payday", "delayed gratification is paying off for {goal}",
               "moved {amount} to {goal} before I could spend it"],
    "neutral": ["how do people afford {item} in this city", "what's a normal price for a used {item}",
                "bank holiday, shops closed", "the {item} reviews are mixed", "anyone else get letters about tax returns"],
}
CONNECTORS = [" but ", ", then again ", " although "]

FUTURE_WORDS = {"save", "saving", "saved", "savings", "later", "next", "future", "plan", "planning", "wait", "waiting",
                "budget", "pension", "retirement", "fund", "aside"}
PRESENT_WORDS = {"now", "today", "instantly", "bought", "ordered", "impulse", "treat", "spent", "buying", "got", "right"}


def _make(rng, lab: str, unseen_share: float) -> tuple[str, str]:
    """One post of class lab; returns the text and its template group (for grouped splits)."""
    r = rng.random()
    if lab != "neutral" and r < 0.12:
        # mixed post: the clause after the connector decides the orientation
        other = "future" if lab == "present" else "present"
        a, b = rng.choice(TEMPLATES[other]), rng.choice(TEMPLATES[lab])
        return _fill(rng, a) + rng.choice(CONNECTORS) + _fill(rng, b), "mixed"
    pool = UNSEEN[lab] if rng.random() < unseen_share else TEMPLATES[lab]
    tpl = rng.choice(pool)
    return _fill(rng, tpl), f"{lab}:{pool.index(tpl)}:{'unseen' if pool is UNSEEN[lab] else 'seen'}"


def _fill(rng, template: str) -> str:
    s = template.format(item=rng.choice(ITEMS), goal=rng.choice(GOALS), amount=rng.choice(AMOUNTS))
    if rng.random() < 0.3:
        s = s.capitalize()
    if rng.random() < 0.25:
        s += rng.choice([" 😅", " 🙃", " lol", "!", " #money", " #budget"])
    return s


def weekly_truth(weeks: pd.DatetimeIndex) -> pd.DataFrame:
    """Share of present, future and neutral posts per week (the built-in seasonal pattern)."""
    present = np.full(len(weeks), 0.30)
    future = np.full(len(weeks), 0.30)
    for i, w in enumerate(weeks):
        if w.month == 11 and w.day >= 22:                 # Black Friday week
            present[i] += 0.18
            future[i] -= 0.08
        if w.month == 12:                                  # December spending
            present[i] += 0.08
            future[i] -= 0.05
        if w.month == 1 and w.day <= 21:                   # New Year resolutions
            future[i] += 0.15
            present[i] -= 0.08
        if w.day <= 7:                                     # week after payday
            present[i] += 0.05
    neutral = 1 - present - future
    return pd.DataFrame({"week": weeks, "present": present, "future": future, "neutral": neutral})


def simulate_posts(seed: int = C.SEED, n_unlabelled: int = 15000, n_labelled: int = 900) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(seed + 7)
    weeks = pd.date_range("2025-10-06", "2026-09-28", freq="W-MON")
    truth = weekly_truth(weeks)
    authors = ["U" + "".join(rng.choice(list("abcdefghjkmnpqrstuvwxyz23456789"), 7)) for _ in range(2500)]
    rows = []
    n = n_unlabelled + n_labelled
    wk = rng.integers(0, len(weeks), n)
    lab_idx = set(rng.choice(n, n_labelled, replace=False).tolist())
    for i in range(n):
        shares = truth.iloc[wk[i]][list(LABELS)].values.astype(float)
        lab = LABELS[int(rng.choice(3, p=shares / shares.sum()))]
        # the labelled sample was drawn before new phrasings spread; later posts use them 30% of the time
        text, group = _make(rng, lab, 0.0 if i in lab_idx else 0.30)
        rows.append({"post_id": f"T{i:06d}", "author": rng.choice(authors), "week": weeks[wk[i]],
                     "text": text, "template": group, "true_label": lab, "labelled": i in lab_idx})
    posts = pd.DataFrame(rows)
    # two annotators with different error rates; a third label settles disagreements
    ann = posts.loc[posts["labelled"]].copy()
    for a, err in (("annotator_a", 0.07), ("annotator_b", 0.11)):
        flip = rng.random(len(ann)) < err
        alt = [rng.choice([l for l in LABELS if l != t]) for t in ann["true_label"]]
        ann[a] = np.where(flip, alt, ann["true_label"])
    third = np.where(rng.random(len(ann)) < 0.95, ann["true_label"],
                     [rng.choice([l for l in LABELS if l != t]) for t in ann["true_label"]])
    ann["gold"] = np.where(ann["annotator_a"] == ann["annotator_b"], ann["annotator_a"], third)
    return {"posts": posts, "annotations": ann, "weekly_truth": truth}


# ------------------------------------------------------------------ models
def tokens(text: str) -> list[str]:
    return re.findall(r"[a-z']+", text.lower())


def lexicon_predict(texts) -> np.ndarray:
    out = []
    for t in texts:
        tok = tokens(t)
        f = sum(w in FUTURE_WORDS for w in tok)
        p = sum(w in PRESENT_WORDS for w in tok)
        out.append("future" if f > p else "present" if p > f else "neutral")
    return np.array(out)


def _groups(ann: pd.DataFrame) -> np.ndarray:
    return np.where(ann["template"] == "mixed", "mixed_" + (np.arange(len(ann)) % 5).astype(str), ann["template"])


def make_model():
    vec = TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True)
    clf = LogisticRegression(max_iter=2000, C=4.0, class_weight="balanced")
    return vec, clf


def evaluate_text(ann: pd.DataFrame, seed: int = C.SEED) -> dict:
    """Random split (optimistic), grouped 5-fold CV by template (honest), word-list baseline."""
    from sklearn.model_selection import GroupKFold

    y = ann["gold"].values
    tr, te = train_test_split(ann, test_size=0.3, random_state=seed, stratify=y)
    vec, clf = make_model()
    clf.fit(vec.fit_transform(tr["text"]), tr["gold"])
    f1_random = float(f1_score(te["gold"], clf.predict(vec.transform(te["text"])), average="macro"))

    oof = np.empty(len(ann), dtype=object)
    for tr_i, te_i in GroupKFold(n_splits=5).split(ann, groups=_groups(ann)):
        v, c = make_model()
        c.fit(v.fit_transform(ann["text"].iloc[tr_i]), y[tr_i])
        oof[te_i] = c.predict(v.transform(ann["text"].iloc[te_i]))
    oof = oof.astype(str)
    lex = lexicon_predict(ann["text"])
    vec, clf = make_model()
    clf.fit(vec.fit_transform(ann["text"]), y)                      # final model on all labelled posts
    return {
        "kappa_annotators": float(cohen_kappa_score(ann["annotator_a"], ann["annotator_b"])),
        "agreement_annotators": float((ann["annotator_a"] == ann["annotator_b"]).mean()),
        "gold_accuracy_vs_truth": float((ann["gold"] == ann["true_label"]).mean()),
        "f1_random_split": f1_random,
        "f1_grouped_cv": float(f1_score(y, oof, average="macro")),
        "f1_lexicon": float(f1_score(y, lex, average="macro")),
        "n_labelled": len(ann),
        "confusion": pd.DataFrame(confusion_matrix(y, oof, labels=list(LABELS)), index=LABELS, columns=LABELS),
        "model": (vec, clf),
    }


def weekly_index(posts: pd.DataFrame, res: dict) -> pd.DataFrame:
    """Future-orientation index per week: (future - present) / (future + present), from the
    classifier, the word list and the truth."""
    vec, clf = res["model"]
    unl = posts[~posts["labelled"]].copy()
    unl["pred"] = clf.predict(vec.transform(unl["text"]))
    unl["lex"] = lexicon_predict(unl["text"])
    rows = []
    for w, g in unl.groupby("week"):
        row = {"week": w, "n": len(g)}
        for name, col in (("classifier", "pred"), ("lexicon", "lex"), ("true", "true_label")):
            f, p = (g[col] == "future").mean(), (g[col] == "present").mean()
            row[f"{name}_index"] = (f - p) / (f + p)
        rows.append(row)
    return pd.DataFrame(rows)


def accuracy_by_phrasing(posts: pd.DataFrame, res: dict) -> pd.DataFrame:
    vec, clf = res["model"]
    unl = posts[~posts["labelled"]].copy()
    unl["pred"] = clf.predict(vec.transform(unl["text"]))
    unl["phrasing"] = np.where(unl["template"] == "mixed", "mixed (two clauses)",
                               np.where(unl["template"].str.endswith("unseen"), "new since labelling", "seen in labelling"))
    return unl.groupby("phrasing").apply(lambda g: pd.Series({"posts": len(g), "accuracy": (g["pred"] == g["true_label"]).mean()}),
                                         include_groups=False).reset_index()
