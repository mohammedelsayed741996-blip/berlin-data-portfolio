"""Figures for the notebooks, README and paper."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
TEXT_PRIMARY, TEXT_SECONDARY, GRID, SURFACE, NEUTRAL = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb", "#9b9a95"

LABEL = {"oracle": "True probability (ceiling)", "ml_person": "Gradient boosting + person features", "hybrid": "Boosting + theory predictions",
         "itch_eb": "ITCH, shrunk to population", "hyperbolic_eb": "Hyperbolic, shrunk to population", "itch": "ITCH heuristic",
         "hyperbolic": "Hyperbolic", "exponential": "Exponential", "quasi_hyperbolic": "Quasi-hyperbolic (beta-delta)",
         "ml_pooled": "Gradient boosting, no person info", "base_rate": "Person's base rate (naive)"}


def _style(ax, title, subtitle="", grid_axis="y"):
    ax.set_facecolor(SURFACE)
    ax.figure.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=TEXT_SECONDARY, labelsize=9)
    if grid_axis:
        ax.grid(axis=grid_axis, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.set_title(title, loc="left", fontsize=12, color=TEXT_PRIMARY, pad=22 if subtitle else 8, fontweight="bold")
    if subtitle:
        ax.text(0, 1.02, subtitle, transform=ax.transAxes, fontsize=9, color=TEXT_SECONDARY)


def _save(fig, path: Path) -> Path:
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def plot_completeness(board: pd.DataFrame, path: Path) -> Path:
    b = board[board["model"] != "base_rate"].sort_values("completeness")
    fig, ax = plt.subplots(figsize=(8.5, 5.2))
    kind = {"oracle": NEUTRAL, "ml_person": SERIES[1], "hybrid": SERIES[1], "ml_pooled": SERIES[1]}
    cols = [kind.get(m, SERIES[0]) for m in b["model"]]
    y = np.arange(len(b))
    ax.barh(y, b["completeness"] * 100, color=cols, height=0.62)
    for yi, (c, ll) in enumerate(zip(b["completeness"], b["log_loss"])):
        ax.text(c * 100 + 1, yi, f"{c:.0%}  (log loss {ll:.3f})", va="center", fontsize=8.5, color=TEXT_SECONDARY)
    ax.set_yticks(y)
    ax.set_yticklabels([LABEL[m] for m in b["model"]], fontsize=9)
    ax.set_xlim(0, 125)
    ax.set_xlabel("Completeness: share of predictable variation captured, %", color=TEXT_SECONDARY, fontsize=9)
    from matplotlib.patches import Patch
    ax.legend(handles=[Patch(color=SERIES[0], label="Theory, fitted per participant"), Patch(color=SERIES[1], label="Machine learning"),
                       Patch(color=NEUTRAL, label="Ceiling (known only in simulation)")],
              frameon=False, fontsize=8.5, labelcolor=TEXT_SECONDARY, loc="upper center", bbox_to_anchor=(0.4, -0.13), ncol=3)
    _style(ax, "How much of the predictable choice behaviour each model captures",
           "Out-of-sample, 4-fold within participant, 399 participants, 23,940 choices", grid_axis="x")
    return _save(fig, path)


def plot_recovery(fits: pd.DataFrame, truth: pd.DataFrame, path: Path) -> Path:
    h = fits[fits["model"] == "hyperbolic"].merge(truth[truth["type"] == "hyperbolic"], on="pid")
    fig, ax = plt.subplots(figsize=(5.6, 5.2))
    for fr, g in h.groupby("condition"):
        ax.scatter(g["log_k"], g["theta0"], s=22, color=SERIES[0] if fr == "delay" else SERIES[1], alpha=0.8, edgecolor=SURFACE, linewidth=0.8, label=f"{fr} frame")
    lo, hi = min(h["log_k"].min(), h["theta0"].min()) - 0.3, max(h["log_k"].max(), h["theta0"].max()) + 0.3
    ax.plot([lo, hi], [lo, hi], color=NEUTRAL, linestyle=(0, (4, 3)), linewidth=1)
    r = np.corrcoef(h["log_k"], h["theta0"])[0, 1]
    ax.text(0.04, 0.94, f"r = {r:.2f}, n = {len(h)}", transform=ax.transAxes, fontsize=9, color=TEXT_SECONDARY)
    ax.set_xlabel("True log k (simulated)", color=TEXT_SECONDARY, fontsize=9)
    ax.set_ylabel("Estimated log k", color=TEXT_SECONDARY, fontsize=9)
    ax.legend(frameon=False, fontsize=8.5, labelcolor=TEXT_SECONDARY, loc="lower right")
    _style(ax, "Parameter recovery", "Hyperbolic-type participants; dashed line = perfect recovery", grid_axis="both")
    return _save(fig, path)


def plot_framing(people: pd.DataFrame, eff: pd.DataFrame, path: Path) -> Path:
    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    rng = np.random.default_rng(1)
    for i, fr in enumerate(("delay", "date")):
        v = people.loc[people["frame"] == fr, "log_k"].values
        ax.scatter(v, i + rng.uniform(-0.18, 0.18, len(v)), s=10, color=SERIES[i], alpha=0.45, edgecolor="none")
        ax.plot([v.mean()] * 2, [i - 0.3, i + 0.3], color=TEXT_PRIMARY, linewidth=2.2)
        ax.text(v.mean(), i + 0.36, f"mean {v.mean():.2f}", ha="center", fontsize=8.5, color=TEXT_PRIMARY)
    e = eff.set_index("outcome").loc["log_k"]
    ax.set_yticks([0, 1])
    ax.set_yticklabels(['Delay frame\n"in 30 days"', 'Date frame\n"on 21 December"'], fontsize=9)
    ax.set_xlabel("Fitted hyperbolic log k per participant (higher = more impatient)", color=TEXT_SECONDARY, fontsize=9)
    _style(ax, "Calendar dates make people more patient",
           f"Difference {e['diff']:.2f} (95% CI {e['ci_low']:.2f} to {e['ci_high']:.2f}), permutation p < 0.001, d = {abs(e['cohens_d']):.2f}",
           grid_axis="x")
    return _save(fig, path)


def plot_weekly(w: pd.DataFrame, path: Path) -> Path:
    fig, ax = plt.subplots(figsize=(9, 3.9))
    ax.plot(w["week"], w["true_index"], color=TEXT_PRIMARY, linewidth=2.2, label="True (simulated)")
    ax.plot(w["week"], w["classifier_index"], color=SERIES[0], linewidth=2, linestyle=(0, (4, 2)), label="TF-IDF + logistic regression")
    ax.plot(w["week"], w["lexicon_index"], color=SERIES[1], linewidth=1.5, linestyle=(0, (1, 2)), label="Word list")
    ax.axhline(0, color=GRID, linewidth=1)
    for d, lab in (("2025-11-24", "Black Friday"), ("2026-01-05", "New Year")):
        ax.axvline(pd.Timestamp(d), color=NEUTRAL, linewidth=0.8, linestyle=(0, (2, 3)))
        ax.text(pd.Timestamp(d), -0.36, " " + lab, fontsize=8, color=TEXT_SECONDARY, va="bottom")
    ax.set_ylabel("Future-orientation index", color=TEXT_SECONDARY, fontsize=9)
    ax.legend(frameon=False, fontsize=8.5, labelcolor=TEXT_SECONDARY, ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.12))
    _style(ax, "Talk about money over the year (synthetic posts)", "(future - present) / (future + present), weekly; about 290 posts per week")
    return _save(fig, path)
