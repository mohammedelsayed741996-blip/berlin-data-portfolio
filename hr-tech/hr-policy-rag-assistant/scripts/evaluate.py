"""Run the evaluation, write the report and figures, and fail if quality drops below the gate.

    PYTHONPATH=src python scripts/evaluate.py            # writes outputs/eval_report.md and outputs/eval.json
    PYTHONPATH=src python scripts/evaluate.py --gate     # also exits with 1 if a gate fails (used in CI)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from hrrag import evaluate as E  # noqa: E402
from hrrag.config import ROOT, Settings  # noqa: E402
from hrrag.corpus import load  # noqa: E402

GATES = {"answer_correct": 0.65, "hit_at_3": 0.90, "decline_rate_when_should": 0.95, "leaks": 0}
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]
TEXT, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"


def _style(ax, title, subtitle):
    ax.set_facecolor(SURFACE)
    ax.figure.set_facecolor(SURFACE)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=9)
    ax.set_axisbelow(True)
    ax.set_title(title, loc="left", fontsize=12, color=TEXT, pad=22, fontweight="bold")
    ax.text(0, 1.02, subtitle, transform=ax.transAxes, fontsize=9, color=MUTED)


def plot_ablation(ab_test, path: Path):
    fig, ax = plt.subplots(figsize=(8.5, 4.2))
    labels = [f"{r.retriever}{' + synonyms' if r.synonyms else ''}" for r in ab_test.itertuples()]
    x = range(len(ab_test))
    w = 0.26
    for j, (col, name) in enumerate([("hit_at_1", "Right passage ranked first"), ("hit_at_3", "Right passage in top 3"),
                                     ("answer_correct", "Answer fully correct")]):
        vals = ab_test[col] * 100
        ax.bar([i + (j - 1) * w for i in x], vals, width=w - 0.03, color=SERIES[j], label=name)
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, fontsize=9)
    ax.set_ylim(0, 105)
    ax.set_ylabel("% of answerable test questions", color=MUTED, fontsize=9)
    ax.grid(axis="y", color=GRID)
    ax.legend(frameon=False, fontsize=8.5, labelcolor=MUTED, ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.1))
    _style(ax, "Retriever comparison on held-out questions", "37 answerable test questions; no tuning on this split")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def plot_calibration(curve, thr, path: Path):
    fig, ax = plt.subplots(figsize=(7.5, 3.8))
    ax.plot(curve["threshold"], curve["answer_correct"] * 100, color=SERIES[0], linewidth=2, label="Answerable questions answered correctly")
    ax.plot(curve["threshold"], curve["declined_correctly"] * 100, color=SERIES[1], linewidth=2, label="Out-of-scope and restricted questions declined")
    ax.axvline(thr, color=MUTED, linestyle=(0, (3, 3)), linewidth=1)
    ax.text(thr + 0.003, 102, f"chosen {thr:.2f}", fontsize=8.5, color=MUTED, va="bottom")
    ax.set_xlabel("Confidence threshold below which the assistant declines", color=MUTED, fontsize=9)
    ax.set_xlim(curve["threshold"].min(), curve["threshold"].max() + 0.01)
    ax.set_ylabel("%", color=MUTED, fontsize=9)
    ax.set_ylim(0, 112)
    ax.grid(axis="y", color=GRID)
    ax.legend(frameon=False, fontsize=8.5, labelcolor=MUTED, loc="lower left", bbox_to_anchor=(0.0, 0.02))
    _style(ax, 'Choosing when to say "I don\'t know"', "Dev split only")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def main(gate: bool) -> int:
    passages = load(Settings().policies_dir)
    out = ROOT / "outputs"
    (out / "figures").mkdir(parents=True, exist_ok=True)
    f = E.full(passages)
    g = E.gold()
    ab_dev, ab_test = E.ablation(passages, g, "dev"), E.ablation(passages, g, "test")
    plot_ablation(ab_test, out / "figures" / "retriever_comparison.png")
    plot_calibration(f["calibration"], f["threshold"], out / "figures" / "decline_threshold.png")
    f["results"].to_csv(out / "eval_results.csv", index=False)
    report = {"threshold": f["threshold"], "dev": f["dev"], "test": f["test"], "gates": GATES,
              "ablation_dev": ab_dev.to_dict("records"), "ablation_test": ab_test.to_dict("records")}
    (out / "eval.json").write_text(json.dumps(report, indent=2))

    t, d = f["test"], f["dev"]
    misses = f["results"].query("split == 'test' and should_answer and not (answered and cited_expected)")
    lines = ["# Evaluation report", "",
             f"Hand-written questions: {t['questions'] + d['questions']} ({d['questions']} dev, {t['questions']} test). "
             f"The decline threshold ({f['threshold']:.2f}) was chosen on dev; the numbers below are for the test split.", "",
             "| Measure | Test | Dev | Gate |", "|---|---:|---:|---:|"]
    for k, lab in [("hit_at_1", "Right passage ranked first"), ("hit_at_3", "Right passage in top 3"), ("mrr", "Mean reciprocal rank"),
                   ("answer_correct", "Answer correct (cites the right passage and contains the facts)"),
                   ("wrongly_declined", "Answerable questions wrongly declined"),
                   ("decline_rate_when_should", "Out-of-scope and restricted questions declined"), ("leaks", "Restricted passages cited"),
                   ("latency_p95_ms", "Latency, 95th percentile (ms)")]:
        fmt = (lambda v: f"{v:.0f}") if k in ("leaks", "latency_p95_ms") else (lambda v: f"{v:.0%}" if k != "mrr" else f"{v:.2f}")
        gt = GATES.get(k)
        gs = "" if gt is None else (f"= {gt}" if k == "leaks" else f">= {gt:.0%}")
        lines.append(f"| {lab} | {fmt(t[k])} | {fmt(d[k])} | {gs} |")
    lines += ["", "## Retrievers on the test split", "", ab_test.round(3).to_markdown(index=False), "",
              "## Test questions where the right passage was not cited", "",
              "| Question | Expected | Rank |", "|---|---|---:|"]
    for r in misses.itertuples():
        lines.append(f"| {r.question} | {r.expected} | {'' if r.rank != r.rank or r.rank is None else int(r.rank)} |")
    (out / "eval_report.md").write_text("\n".join(lines) + "\n")

    failed = [k for k, v in GATES.items() if (t[k] != v if k == "leaks" else t[k] < v)]
    print(json.dumps({"test": {k: round(v, 3) for k, v in t.items()}, "failed_gates": failed}, indent=2))
    return 1 if gate and failed else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--gate", action="store_true")
    sys.exit(main(ap.parse_args().gate))
