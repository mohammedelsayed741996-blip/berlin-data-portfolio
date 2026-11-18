"""Panel of issuer-months with the target, text scores, keyword counts and financial features.

Everything is computed "as of" the end of each month: only articles dated in or
before that month, only financials already published, only past share prices.
The target is whether the agency downgrades the issuer in the next three months.
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import FeatureUnion, Pipeline

from . import config as C

# A typical starter list of credit red-flag words in English and German, the kind many credit teams
# keep in a spreadsheet. It was written as a generic list, not tuned to this news feed, and it fires
# on denials and sector stories as well.
KEYWORDS = {
    "kw_profit_warning": r"profit warning|gewinnwarnung",
    "kw_covenant": r"covenant",
    "kw_refinancing": r"refinanc|refinanzierung",
    "kw_liquidity": r"liquidity|liquidität",
    "kw_restructuring": r"restructuring|restrukturierung|sparprogramm",
    "kw_impairment": r"impairment|write.?down|abschreibung",
    "kw_default_insolvency": r"default|insolven",
    "kw_downgrade": r"downgrade|herabgestuft|herabstufung",
    "kw_negative_outlook": r"negative outlook|outlook to negative|ausblick .*negativ",
}


def months_between(start: str, end: str) -> list[str]:
    return [p.strftime("%Y-%m") for p in pd.period_range(start, end, freq="M")]


def mask_issuer(text: pd.Series, names: pd.Series) -> pd.Series:
    """Replace the issuer's own name with a token, so the model learns language, not names."""
    return pd.Series([t.replace(n, "[co]") for t, n in zip(text, names)], index=text.index)


SECTOR_TERMS = r"real estate|automotive|chemicals|retail|utilities|telecoms|industrials|transport & logistics|healthcare|consumer goods"
CITY_TERMS = r"hamburg|lyon|rotterdam|turin|linz|bilbao|leipzig|dortmund|lille|graz"


def article_text(news: pd.DataFrame, issuers: pd.DataFrame) -> pd.Series:
    """Headline and body, lower-cased, with the issuer name, sector, city, quarter and numbers masked.

    The first version of the model left these in and learned that "utilities" or "Q2" meant risk,
    because sector shocks and reporting seasons line up with downgrades in the training years.
    That is a shortcut that will not hold next year, so the tokens are replaced."""
    names = news["issuer_id"].map(dict(zip(issuers["issuer_id"], issuers["issuer_name"])))
    t = mask_issuer(news["headline"] + ". " + news["body"], names).str.lower()
    t = t.str.replace(SECTOR_TERMS, "[sector]", regex=True).str.replace(CITY_TERMS, "[city]", regex=True)
    t = t.str.replace(r"\bq[1-4]\b", "[quarter]", regex=True).str.replace(r"\b20\d\d\b", "[year]", regex=True)
    t = t.str.replace(r"\d+", "[num]", regex=True)
    return t.map(mark_negation)


NEGATION_CUES = {"no", "not", "denies", "deny", "denied", "rejects", "rejected", "without", "never",
                 "kein", "keine", "keinen", "nicht", "weist", "zurückgewiesen", "dementiert"}


def mark_negation(text: str, scope: int = 4) -> str:
    """Prefix the few words after a negation cue with "neg_", so "denies liquidity problems" and
    "liquidity problems" become different features. Bag-of-words models cannot see this otherwise."""
    out, left = [], 0
    for tok in text.split():
        word = tok.strip(".,;:!?")
        if left > 0 and word and not word.startswith("["):
            out.append("neg_" + tok)
            left -= 1
        else:
            out.append(tok)
        if word in NEGATION_CUES:
            left = scope
        if tok.endswith((".", ";", "!", "?")):
            left = 0
    return " ".join(out)


def targets(tables) -> pd.DataFrame:
    """One row per issuer and as-of month with the 3-month downgrade target."""
    r = tables["ratings"][["issuer_id", "month", "rating", "notch", "outlook"]].copy()
    dg = tables["rating_actions"]
    dg = dg[dg["action"] == "downgrade"][["issuer_id", "month"]].assign(dg=1)
    allm = months_between(C.START, C.END)
    idx = {m: i for i, m in enumerate(allm)}
    events = dg.groupby("issuer_id")["month"].apply(lambda s: sorted(idx[m] for m in s)).to_dict()
    ys, lead = [], []
    for row in r.itertuples():
        t = idx[row.month]
        ev = [e for e in events.get(row.issuer_id, []) if t < e <= t + C.HORIZON_MONTHS]
        ys.append(int(bool(ev)))
        lead.append(min(ev) - t if ev else np.nan)
    r["y"] = ys
    r["months_to_downgrade"] = lead
    r["labelled"] = r["month"].map(idx) + C.HORIZON_MONTHS <= len(allm) - 1
    return r


# ---------------------------------------------------------------------------- text model
def make_vectorizer() -> FeatureUnion:
    return FeatureUnion([
        ("words", TfidfVectorizer(ngram_range=(1, 2), min_df=5, max_features=40_000, sublinear_tf=True,
                                  token_pattern=r"(?u)\b[\w\[\]]+\b")),
        ("chars", TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=5, max_features=30_000, sublinear_tf=True)),
    ])


def make_classifier() -> LogisticRegression:
    return LogisticRegression(C=0.5, max_iter=3000, class_weight="balanced")


def make_text_model() -> Pipeline:
    return Pipeline([("tfidf", make_vectorizer()), ("clf", make_classifier())])


def article_labels(news: pd.DataFrame, panel: pd.DataFrame) -> pd.Series:
    key = panel.set_index(["issuer_id", "month"])["y"]
    m = news["date"].str[:7]
    return pd.Series(key.reindex(list(zip(news["issuer_id"], m))).values, index=news.index)


def score_articles(tables, panel: pd.DataFrame, train_end: str, seed: int = C.SEED):
    """Train the article classifier on articles up to `train_end` and score every article.

    Training articles get out-of-fold scores (folds grouped by issuer), so the second-stage
    model never sees a score the text model produced for an article it was trained on.
    """
    news = tables["news"].copy()
    news["text"] = article_text(news, tables["issuers"])
    news["y"] = article_labels(news, panel)
    news["month"] = news["date"].str[:7]
    train = news[(news["month"] <= train_end) & news["y"].notna()]
    # The vocabulary and IDF weights use no labels, so they are fitted once on the training articles.
    vec = make_vectorizer().fit(train["text"])
    X_train = vec.transform(train["text"])
    oof = pd.Series(np.nan, index=news.index)
    for tr, va in GroupKFold(n_splits=5).split(X_train, train["y"], groups=train["issuer_id"]):
        clf = make_classifier().fit(X_train[tr], train["y"].iloc[tr])
        oof.loc[train.index[va]] = clf.predict_proba(X_train[va])[:, 1]
    clf = make_classifier().fit(X_train, train["y"])
    model = Pipeline([("tfidf", vec), ("clf", clf)])
    rest = news.index.difference(train.index)
    oof.loc[rest] = model.predict_proba(news.loc[rest, "text"])[:, 1]
    news["p_article"] = oof
    return model, news


# ---------------------------------------------------------------------------- aggregation
def text_features(news: pd.DataFrame, panel: pd.DataFrame) -> pd.DataFrame:
    """Aggregate article scores and keyword hits over the last 1 and 3 months for each issuer-month."""
    allm = months_between(C.START, C.END)
    idx = {m: i for i, m in enumerate(allm)}
    n = news.assign(t=news["date"].str[:7].map(idx))
    for k, pat in KEYWORDS.items():
        n[k] = n["text"].str.contains(pat, regex=True).astype(int)
    n["high"] = (n["p_article"] > 0.5).astype(int)
    g = n.groupby(["issuer_id", "t"]).agg(
        n_articles=("article_id", "size"), p_sum=("p_article", "sum"), p_max=("p_article", "max"),
        n_high=("high", "sum"), **{k: (k, "sum") for k in KEYWORDS})
    out = []
    for issuer, gi in g.groupby(level=0):
        gi = gi.droplevel(0).reindex(range(len(allm)), fill_value=0)
        gi["p_max"] = gi["p_max"].replace(0, np.nan)
        r1 = gi
        r3 = gi.rolling(3, min_periods=1).sum()
        r3max = gi["p_max"].rolling(3, min_periods=1).max()
        prev = gi.shift(3).rolling(3, min_periods=1).sum()
        df = pd.DataFrame({
            "issuer_id": issuer, "month": allm,
            "news_1m": r1["n_articles"].values, "news_3m": r3["n_articles"].values,
            "p_mean_1m": (r1["p_sum"] / r1["n_articles"].replace(0, np.nan)).values,
            "p_mean_3m": (r3["p_sum"] / r3["n_articles"].replace(0, np.nan)).values,
            "p_max_3m": r3max.values,
            "high_1m": r1["n_high"].values, "high_3m": r3["n_high"].values,
            "high_trend": (r3["n_high"] - prev["n_high"]).values,
            "news_trend": (r3["n_articles"] - prev["n_articles"]).values,
        })
        for k in KEYWORDS:
            df[k] = r3[k].values
        out.append(df)
    return pd.concat(out, ignore_index=True)


def financial_features(tables, panel: pd.DataFrame) -> pd.DataFrame:
    """Latest published quarter as of each month (no look-ahead), plus share price momentum."""
    grid = panel[["issuer_id", "month"]].drop_duplicates()
    grid = grid.assign(t=pd.to_datetime(grid["month"])).sort_values("t")
    fin = tables["financials"].sort_values(["issuer_id", "quarter_end"]).copy()
    g = fin.groupby("issuer_id")
    fin["leverage_chg_1y"] = fin["net_debt_to_ebitda"] - g["net_debt_to_ebitda"].shift(4)
    fin["coverage_chg_1y"] = fin["interest_coverage"] - g["interest_coverage"].shift(4)
    fin = fin.assign(t=pd.to_datetime(fin["published"])).sort_values("t")
    f = pd.merge_asof(grid, fin[["issuer_id", "t", "net_debt_to_ebitda", "interest_coverage", "leverage_chg_1y",
                                 "coverage_chg_1y"]], on="t", by="issuer_id", direction="backward")
    f = f.rename(columns={"net_debt_to_ebitda": "leverage", "interest_coverage": "coverage"}).drop(columns="t")
    eq = tables["equity"].sort_values(["issuer_id", "month"]).copy()
    gp = eq.groupby("issuer_id")["close"]
    eq["ret_3m"] = gp.pct_change(3)
    eq["ret_6m"] = gp.pct_change(6)
    eq["drawdown_12m"] = eq["close"] / gp.transform(lambda s: s.rolling(12, min_periods=1).max()) - 1
    return f.merge(eq[["issuer_id", "month", "ret_3m", "ret_6m", "drawdown_12m"]], on=["issuer_id", "month"], how="left")


def rating_features(tables, panel: pd.DataFrame) -> pd.DataFrame:
    p = panel[["issuer_id", "month", "notch", "outlook"]].copy()
    p["outlook_negative"] = (p["outlook"] == "negative").astype(int)
    p["outlook_positive"] = (p["outlook"] == "positive").astype(int)
    p["notches_above_hy"] = C.RATINGS.index(C.INVESTMENT_GRADE_FLOOR) - p["notch"]
    dg = tables["rating_actions"]
    dg = dg[dg["action"] == "downgrade"]
    allm = months_between(C.START, C.END)
    idx = {m: i for i, m in enumerate(allm)}
    last = {}
    since = []
    dgs = set(zip(dg["issuer_id"], dg["month"]))
    for r in p.sort_values(["issuer_id", "month"]).itertuples():
        if (r.issuer_id, r.month) in dgs:
            last[r.issuer_id] = idx[r.month]
        since.append(idx[r.month] - last[r.issuer_id] if r.issuer_id in last else 99)
    p = p.sort_values(["issuer_id", "month"])
    p["months_since_downgrade"] = since
    return p.drop(columns=["outlook"])


def build_panel(tables, train_end: str):
    panel = targets(tables)
    model, scored = score_articles(tables, panel, train_end)
    tf = text_features(scored, panel)
    ff = financial_features(tables, panel)
    rf = rating_features(tables, panel)
    sectors = tables["issuers"][["issuer_id", "sector", "country", "listed"]]
    out = (panel.merge(rf, on=["issuer_id", "month", "notch"]).merge(tf, on=["issuer_id", "month"], how="left")
           .merge(ff, on=["issuer_id", "month"], how="left").merge(sectors, on="issuer_id"))
    return out, model, scored
