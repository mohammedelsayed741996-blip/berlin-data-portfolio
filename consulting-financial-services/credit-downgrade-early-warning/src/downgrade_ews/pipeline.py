"""Run everything: data, features, models, validation, outputs.

    PYTHONPATH=src python -m downgrade_ews.pipeline              # uses data/ if present
    PYTHONPATH=src python -m downgrade_ews.pipeline --regenerate # rebuild the synthetic data first
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass

import pandas as pd

from . import config as C, data, explain, features, models, reporting, validation


@dataclass
class Run:
    tables: dict
    panel: pd.DataFrame
    scored: pd.DataFrame
    text_model: object
    train: pd.DataFrame
    test: pd.DataFrame
    results: dict
    evaluation: pd.DataFrame
    scores_all: pd.Series
    alert_cut: pd.Series


def load_tables(regenerate: bool = False, paths: C.Paths | None = None) -> dict:
    paths = paths or C.Paths()
    if regenerate or not (paths.data / "news.csv.gz").exists():
        data.save(data.generate(), paths.data)
    return data.load(paths.data)


def run(tables: dict) -> Run:
    train_end = models.train_end()
    panel, text_model, scored = features.build_panel(tables, train_end)
    train, test, _ = models.split(panel)
    results = models.fit_all(train, test)
    ev = models.evaluate(results, test, tables["rating_actions"])
    full = results[models.FULL]
    eligible = panel[(panel["month"] >= "2022-04") & (panel["notch"] < len(C.RATINGS) - 1)]
    scores_all = pd.Series(full.model.predict_proba(eligible[full.features])[:, 1], index=eligible.index)
    cut = eligible.assign(s=scores_all).groupby("month")["s"].apply(
        lambda s: s.nlargest(C.ALERT_THRESHOLD_TOP_K).min())
    return Run(tables, panel, scored, text_model, train, test, results, ev, scores_all, cut)


def story_issuer(r: Run) -> str:
    """A test-period downgrade the model flagged three months ahead while the outlook was still stable."""
    fl = models.alerts(r.test, r.results[models.FULL].scores)
    hits = fl[(fl["y"] == 1) & (fl["months_to_downgrade"] == C.HORIZON_MONTHS) & (fl["outlook_negative"] == 0)]
    if hits.empty:
        hits = fl[(fl["y"] == 1) & (fl["months_to_downgrade"] == C.HORIZON_MONTHS)]
    best = hits.sort_values(["p_max_3m", "issuer_id"], ascending=[False, True])
    return best["issuer_id"].iloc[0]


def watchlist(r: Run, month: str = C.END) -> pd.DataFrame:
    """Live list for the latest month (no label yet). The issuer model is refitted on every labelled month."""
    full = r.results[models.FULL]
    labelled = r.panel[r.panel["labelled"] & (r.panel["month"] >= "2022-04") & (r.panel["notch"] < len(C.RATINGS) - 1)]
    m = models.make_model(models.FULL).fit(labelled[full.features], labelled["y"])
    now = r.panel[(r.panel["month"] == month) & (r.panel["notch"] < len(C.RATINGS) - 1)].copy()
    now["score"] = m.predict_proba(now[full.features])[:, 1]
    top = now.nlargest(C.ALERT_THRESHOLD_TOP_K, "score")
    names = dict(zip(r.tables["issuers"]["issuer_id"], r.tables["issuers"]["issuer_name"]))
    rows = []
    for t in top.itertuples():
        ev = explain.issuer_evidence(r.scored, t.issuer_id, month, r.text_model, n=1)
        e = ev.iloc[0] if len(ev) else None
        rows.append({"issuer_id": t.issuer_id, "issuer_name": names[t.issuer_id], "sector": t.sector,
                     "rating": t.rating, "outlook": "negative" if t.outlook_negative else ("positive" if t.outlook_positive else "stable"),
                     "score": t.score, "date": e["date"] if e is not None else "",
                     "headline": e["headline"] if e is not None else "no recent news",
                     "why": e["why"] if e is not None else ""})
    return pd.DataFrame(rows)


def write_outputs(r: Run, paths: C.Paths | None = None) -> dict:
    paths = paths or C.Paths()
    f = paths.figures
    f.mkdir(parents=True, exist_ok=True)
    full = r.results[models.FULL]
    bt = validation.behavioural_tests(r.text_model, r.tables["issuers"])
    lang = validation.by_language(r.scored, C.TEST_START)
    groups = explain.feature_group_importance(full, r.test)
    ts = validation.topic_scores(r.scored, C.TEST_START)
    iss = story_issuer(r)
    name = r.tables["issuers"].set_index("issuer_id").loc[iss, "issuer_name"]
    wl = watchlist(r)
    out = {
        "model_comparison": reporting.plot_model_comparison(r.evaluation, f / "model_comparison.png"),
        "pr_curves": reporting.plot_pr_curves(r.test, r.results, f / "pr_curves.png"),
        "issuer_story": reporting.plot_issuer_story(r.panel, r.scored, r.scores_all, iss, name, r.alert_cut, f / "issuer_story.png"),
        "topic_scores": reporting.plot_topic_scores(ts, f / "topic_scores.png"),
        "watchlist": reporting.watchlist_md(wl, C.END, paths.outputs / f"watchlist_{C.END}.md"),
        "model_card": reporting.model_card(paths.outputs / "model_card.md", ev=r.evaluation, bt=bt, lang=lang, groups=groups,
                                           base_rate=models.base_rate(r.test), n_articles=len(r.tables["news"]),
                                           n_train=len(r.train), n_test=len(r.test)),
    }
    wl.to_csv(paths.outputs / f"watchlist_{C.END}.csv", index=False)
    r.evaluation.to_csv(paths.outputs / "evaluation.csv", index=False)
    summary = {"evaluation": r.evaluation.to_dict("records"), "behavioural_tests": bt.to_dict("records"),
               "story_issuer": iss, "n_articles": len(r.tables["news"]), "test_base_rate": models.base_rate(r.test)}
    (paths.outputs / "summary.json").write_text(json.dumps(summary, indent=2, default=float))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--regenerate", action="store_true")
    args = ap.parse_args()
    r = run(load_tables(args.regenerate))
    out = write_outputs(r)
    print(r.evaluation.to_string(index=False))
    for k, v in out.items():
        print(f"wrote {k}: {v}")


if __name__ == "__main__":
    main()
