"""Charts, the monthly watchlist and the model card."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.metrics import precision_recall_curve  # noqa: E402

from . import config as C  # noqa: E402

SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
TEXT_PRIMARY, TEXT_SECONDARY, GRID, SURFACE, NEUTRAL = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb", "#9b9a95"
MODEL_COLORS = {"Outlook only": NEUTRAL, "Ratings + financials": SERIES[3], "+ keyword rules": SERIES[1],
                "+ NLP news scores": SERIES[0]}


def _style(ax, title: str, subtitle: str = "", grid_axis: str = "y") -> None:
    ax.set_facecolor(SURFACE)
    ax.figure.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=TEXT_SECONDARY, labelsize=9)
    ax.grid(axis=grid_axis, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.set_title(title, loc="left", fontsize=12, color=TEXT_PRIMARY, pad=22 if subtitle else 8, fontweight="bold")
    if subtitle:
        ax.text(0, 1.02, subtitle, transform=ax.transAxes, fontsize=9, color=TEXT_SECONDARY)


def plot_model_comparison(ev: pd.DataFrame, path: Path) -> Path:
    fig, ax = plt.subplots(figsize=(9.5, 4.4))
    x = np.arange(len(ev))
    w = 0.38
    ax.bar(x - w / 2, ev["alert_precision"] * 100, width=w - 0.04, color=SERIES[0], label="Alerts that were right (%)")
    ax.bar(x + w / 2, ev["event_recall"] * 100, width=w - 0.04, color=SERIES[2], label="Downgrades flagged in advance (%)")
    for xi, (p, r) in enumerate(zip(ev["alert_precision"], ev["event_recall"])):
        ax.text(xi - w / 2, p * 100 + 1, f"{p:.0%}", ha="center", fontsize=8.5, color=TEXT_PRIMARY)
        ax.text(xi + w / 2, r * 100 + 1, f"{r:.0%}", ha="center", fontsize=8.5, color=TEXT_PRIMARY)
    labels = [f"{m}\n({a:.0f} alerts/month)" for m, a in zip(ev["model"], ev["alerts_per_month"])]
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=8.5)
    ax.legend(frameon=False, fontsize=8.5, labelcolor=TEXT_SECONDARY, loc="upper left")
    ax.set_ylim(0, max(ev["event_recall"].max(), ev["alert_precision"].max()) * 100 * 1.25)
    _style(ax, "Out-of-time test, July 2025 to June 2026",
           f"{int(ev['downgrades'].iloc[0])} downgrades; models other than the outlook rule flag the top {C.ALERT_THRESHOLD_TOP_K} names each month")
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def plot_pr_curves(test: pd.DataFrame, results: dict, path: Path) -> Path:
    fig, ax = plt.subplots(figsize=(7.5, 4.6))
    for name, r in results.items():
        if name == "Outlook only":
            continue
        p, rc, _ = precision_recall_curve(test["y"], r.scores)
        ax.plot(rc, p, color=MODEL_COLORS[name], linewidth=2, label=name)
    ax.axhline(test["y"].mean(), color=NEUTRAL, linestyle=(0, (4, 3)), linewidth=1.5, label="Base rate")
    ax.set_xlabel("Share of downgrade months caught (recall)", color=TEXT_SECONDARY, fontsize=9)
    ax.set_ylabel("Precision", color=TEXT_SECONDARY, fontsize=9)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.legend(frameon=False, fontsize=8.5, labelcolor=TEXT_SECONDARY)
    _style(ax, "Precision and recall, issuer-months in the test period", "Higher and further right is better")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def plot_issuer_story(panel: pd.DataFrame, scored: pd.DataFrame, scores_all: pd.Series, issuer_id: str,
                      issuer_name: str, alert_cut: pd.Series, path: Path) -> Path:
    """Two panels on one time axis: the agency rating and the early-warning score with article markers."""
    p = panel[panel["issuer_id"] == issuer_id].sort_values("month")
    s = scores_all.reindex(p.index)
    window = p["month"] >= (pd.Period(C.TEST_START, freq="M") - 9).strftime("%Y-%m")
    p, s = p[window], s[window]
    x = np.arange(len(p))
    months = p["month"].tolist()
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(9.5, 5.6), sharex=True, gridspec_kw={"height_ratios": [0.7, 1.6]})
    a1.step(x, p["notch"], where="post", color=TEXT_PRIMARY, linewidth=2)
    a1.set_yticks(sorted(p["notch"].unique()))
    a1.set_yticklabels([C.RATINGS[n] for n in sorted(p["notch"].unique())])
    a1.invert_yaxis()
    _style(a1, f"{issuer_name}: rating and early-warning score", "Agency rating (lower on the chart = worse)")
    a2.plot(x, s.values, color=SERIES[0], linewidth=2.2, marker="o", markersize=4, label="Model score")
    cut = alert_cut.reindex(months).values
    a2.plot(x, cut, color=SERIES[1], linewidth=1.5, linestyle=(0, (4, 3)), label=f"Alert line (top {C.ALERT_THRESHOLD_TOP_K})")
    arts = scored[(scored["issuer_id"] == issuer_id) & (scored["p_article"] > 0.6)]
    for m, g in arts.groupby(arts["date"].str[:7]):
        if m in months:
            a2.scatter([months.index(m)] * len(g), [-0.04] * len(g), marker="|", s=120, color=SERIES[7])
    a2.scatter([], [], marker="|", s=120, color=SERIES[7], label="High-risk article")
    a2.set_ylim(-0.08, max(1.0, np.nanmax(s.values) * 1.1))
    a2.legend(frameon=False, fontsize=8, labelcolor=TEXT_SECONDARY, loc="upper left")
    _style(a2, "")
    step = max(1, len(x) // 9)
    a2.set_xticks(x[::step])
    a2.set_xticklabels([pd.Period(m, freq="M").strftime("%b %y") for m in months][::step])
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def plot_topic_scores(ts: pd.DataFrame, path: Path) -> Path:
    colors = {"negative": SERIES[1], "noise": SERIES[3], "neutral": NEUTRAL, "positive": SERIES[2], "agency": SERIES[6]}
    t = ts.iloc[::-1]
    fig, ax = plt.subplots(figsize=(8.5, 7))
    ax.barh(np.arange(len(t)), t["mean_score"], color=[colors[g] for g in t["group"]], height=0.7)
    for i, (sc, dg) in enumerate(zip(t["mean_score"], t["downgraded_within_3m"])):
        ax.text(sc + 0.005, i, f"{dg:.0%} downgraded", va="center", fontsize=7.5, color=TEXT_SECONDARY)
    ax.set_yticks(np.arange(len(t)))
    ax.set_yticklabels(t["true_topic"].str.replace("_", " "), fontsize=8.5)
    ax.set_xlim(0, t["mean_score"].max() * 1.3)
    from matplotlib.patches import Patch
    ax.legend(handles=[Patch(color=c, label=g) for g, c in colors.items()], frameon=False, fontsize=8,
              labelcolor=TEXT_SECONDARY, loc="lower right", title="Topic group", title_fontsize=8)
    _style(ax, "Average article score by hidden topic, test period",
           "Labels: share of articles followed by a downgrade within 3 months", grid_axis="x")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def watchlist_md(wl: pd.DataFrame, month: str, path: Path) -> Path:
    lines = [f"# Credit watchlist, as of {month}", "",
             f"Top {len(wl)} issuers by downgrade risk over the next three months. Synthetic data. "
             "Each line shows the article that weighs most and the words behind its score.", "",
             "| # | Issuer | Sector | Rating | Outlook | Risk score | Strongest article | Why |",
             "|---|---|---|---|---|---|---|---|"]
    for i, r in enumerate(wl.itertuples(), start=1):
        lines.append(f"| {i} | {r.issuer_name} | {r.sector} | {r.rating} | {r.outlook} | {r.score:.0%} | "
                     f"{r.headline} ({r.date}) | {r.why} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def model_card(path: Path, *, ev: pd.DataFrame, bt: pd.DataFrame, lang: pd.DataFrame, groups: pd.DataFrame,
               base_rate: float, n_articles: int, n_train: int, n_test: int) -> Path:
    full = ev.set_index("model").loc["+ NLP news scores"]
    kw = ev.set_index("model").loc["+ keyword rules"]
    lines = [
        "# Model card: credit downgrade early warning", "",
        "## Purpose", "",
        "Rank rated corporate issuers by the chance of a downgrade in the next three months, so credit analysts can "
        "decide which names to review first. The model supports a human review; it does not take rating or lending decisions.", "",
        "## Data", "",
        f"Synthetic: {C.N_ISSUERS} European issuers, {n_articles:,} news articles in English and German from "
        f"{C.START} to {C.END}, quarterly financials, share prices and agency rating actions. No real company or person appears.", "",
        "## Design", "",
        "1. Article model: TF-IDF on words, word pairs and character n-grams, logistic regression. Issuer names, sectors, "
        "cities, quarters and numbers are masked, and words after a negation are marked. Training articles get "
        "out-of-fold scores (5 folds grouped by issuer).",
        "2. Issuer-month model: gradient boosting on rating and outlook, financials and share price, keyword counts and the "
        "aggregated article scores.", "",
        f"Training: {n_train:,} issuer-months up to 2025-03. Test: {n_test:,} issuer-months from {C.TEST_START}, after a "
        "three-month gap so no training label overlaps the test period. Base rate in test: " f"{base_rate:.1%}.", "",
        "## Results (out of time)", "",
        ev.to_markdown(index=False), "",
        f"With the same review budget of {C.ALERT_THRESHOLD_TOP_K} names a month, the full model's alerts were right "
        f"{full.alert_precision:.0%} of the time against {kw.alert_precision:.0%} for keyword rules, and it flagged "
        f"{full.event_recall:.0%} of downgrades in the three months before they happened.", "",
        "Feature groups, drop in PR-AUC when shuffled:", "", groups.to_markdown(index=False), "",
        "## Validation", "", bt.to_markdown(index=False), "", lang.to_markdown(index=False), "",
        "## Limits", "",
        "- The news is generated from templates. A bag-of-words model learns those phrasings well and generalises poorly "
        "to new wording (see the unseen-paraphrase test). On real news it would need human-labelled articles and most likely "
        "a multilingual transformer or an LLM classifier, validated with the same behavioural tests.",
        "- Denials are scored as risky. In this data that is correct (issuers denying problems were downgraded far more often "
        "than average), but it should be checked on real data before anyone relies on it.",
        "- Scores are rankings first. Calibrated probabilities would need a calibration step on recent data.",
        "- One agency, one rating scale, monthly granularity.", "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
