"""Run the whole analysis: data quality, model fits, cross-validation, effects, text pilot, figures.

Cross-validation takes a few minutes, so its predictions are cached in outputs/cv_predictions.csv.gz.
Use --refresh to recompute them.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import config as C, data, effects as F, evaluate as E, models as M, nlp as N, quality as Q, reporting as R


def run(root: Path | None = None, regenerate: bool = False, refresh_cv: bool = False) -> dict:
    paths = C.Paths(root) if root else C.Paths()
    if regenerate or not (paths.data / "trials.csv.gz").exists():
        data.save(data.generate(), paths.data)
    t = data.load(paths.data)
    paths.figures.mkdir(parents=True, exist_ok=True)

    clean, qlog, rules = Q.apply(t)
    flow = Q.flow(t, rules)
    excluded = sorted(set(rules[1].flagged) | set(rules[2].flagged))
    fits = M.fit_all(clean)
    best = M.best_model(fits).merge(t["truth"][["pid", "type"]], on="pid")

    cv_file = paths.outputs / "cv_predictions.csv.gz"
    if refresh_cv or regenerate or not cv_file.exists():
        cv = E.cross_validate(clean)
        cv.to_csv(cv_file, index=False)
    cv = pd.read_csv(cv_file)
    board = E.scoreboard(cv)
    types = E.by_type(cv, t["truth"])
    ci = {"itch_minus_hyperbolic": E.bootstrap_ci(cv, "itch", "hyperbolic"),
          "itch_eb_minus_ml_person": E.bootstrap_ci(cv, "itch_eb", "ml_person"),
          "hybrid_minus_ml_person": E.bootstrap_ci(cv, "hybrid", "ml_person")}

    people = F.person_table(clean, fits)
    framing = F.framing_effect(people)
    mag = F.magnitude_effect(clean)
    robust = F.with_careless(t["trials"][t["trials"]["submission"] == 1], None, excluded)

    posts = N.simulate_posts()
    text = N.evaluate_text(posts["annotations"])
    weekly = N.weekly_index(posts["posts"], text)
    phr = N.accuracy_by_phrasing(posts["posts"], text)

    figs = {"completeness": R.plot_completeness(board, paths.figures / "completeness.png"),
            "recovery": R.plot_recovery(fits, t["truth"], paths.figures / "parameter_recovery.png"),
            "framing": R.plot_framing(people, framing, paths.figures / "framing_effect.png"),
            "weekly": R.plot_weekly(weekly, paths.figures / "future_orientation_index.png")}

    h = fits[fits["model"] == "hyperbolic"].merge(t["truth"], on="pid")
    hh = h[h["type"] == "hyperbolic"]
    b = board.set_index("model")
    summary = {
        "submissions": int(len(t["participants"])), "analysed": int(clean["pid"].nunique()), "choices": int(len(clean)),
        "excluded": len(excluded), "careless_caught": int(t["truth"].query("careless != 'no'")["pid"].isin(excluded).sum()),
        "completeness": {m: round(float(b.loc[m, "completeness"]), 3) for m in b.index},
        "accuracy": {m: round(float(b.loc[m, "accuracy"]), 3) for m in b.index},
        "log_loss": {m: round(float(b.loc[m, "log_loss"]), 4) for m in b.index},
        "ci": {k: [round(x, 4) for x in v] for k, v in ci.items()},
        "recovery_r_log_k": round(float(np.corrcoef(hh["log_k"], hh["theta0"])[0, 1]), 3),
        "recovery_bias_log_k": round(float((hh["theta0"] - hh["log_k"]).mean()), 3),
        "type_classification_accuracy": round(float((best["best"] == best["type"]).mean()), 3),
        "framing": framing.set_index("outcome")[["diff", "ci_low", "ci_high", "p_perm", "cohens_d"]].round(3).to_dict("index"),
        "magnitude": {k: round(v, 3) if isinstance(v, float) else v for k, v in mag.items() if k != "table"},
        "text": {k: round(v, 3) if isinstance(v, float) else v for k, v in text.items() if k not in ("confusion", "model")},
        "weekly_r_classifier": round(float(np.corrcoef(weekly["classifier_index"], weekly["true_index"])[0, 1]), 3),
        "weekly_r_lexicon": round(float(np.corrcoef(weekly["lexicon_index"], weekly["true_index"])[0, 1]), 3),
    }
    (paths.outputs / "summary.json").write_text(json.dumps(summary, indent=2))
    board.to_csv(paths.outputs / "scoreboard.csv", index=False)
    qlog.to_csv(paths.outputs / "quality_log.csv", index=False)
    framing.to_csv(paths.outputs / "framing_effect.csv", index=False)
    fits.to_csv(paths.outputs / "model_fits.csv.gz", index=False)
    return {"tables": t, "clean": clean, "quality_log": qlog, "flow": flow, "rules": rules, "fits": fits, "best": best,
            "cv": cv, "board": board, "by_type": types, "ci": ci, "people": people, "framing": framing, "magnitude": mag,
            "robust": robust, "posts": posts, "text": text, "weekly": weekly, "phrasing": phr, "figures": figs, "summary": summary}


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Intertemporal choice: data quality, models, ML comparison, effects, text pilot.")
    ap.add_argument("--regenerate", action="store_true", help="rebuild the synthetic data (implies --refresh)")
    ap.add_argument("--refresh", action="store_true", help="recompute the cached cross-validation")
    a = ap.parse_args()
    print(json.dumps(run(regenerate=a.regenerate, refresh_cv=a.refresh)["summary"], indent=2))
