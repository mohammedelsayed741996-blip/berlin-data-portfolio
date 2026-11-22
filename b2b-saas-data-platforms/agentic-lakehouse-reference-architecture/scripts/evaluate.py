"""Rebuild the lakehouse, run the task and red-team evaluations, write the report and charts, apply the gate.

    PYTHONPATH=src python scripts/evaluate.py          # report only
    PYTHONPATH=src python scripts/evaluate.py --gate   # exit 1 if a release gate fails (CI)
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from agentlake import evaluate as E, lakehouse  # noqa: E402
from agentlake.agent import Agent  # noqa: E402
from agentlake.config import ROOT, Settings  # noqa: E402

SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#6250d6"]
TEXT, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
LABELS = {"account": "Account facts", "portfolio": "Portfolio totals", "revenue": "Revenue", "policy": "Policies",
          "action": "Actions needing approval", "access": "Access-control probes", "injection": "Prompt injection",
          "out_of_scope": "Out of scope", "paraphrase": "Paraphrases (unseen wording)"}


def _style(ax, title, sub, grid="x"):
    ax.set_facecolor(SURFACE)
    ax.figure.set_facecolor(SURFACE)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=9)
    if grid:
        ax.grid(axis=grid, color=GRID)
    ax.set_axisbelow(True)
    ax.set_title(title, loc="left", fontsize=12, color=TEXT, pad=22, fontweight="bold")
    ax.text(0, 1.02, sub, transform=ax.transAxes, fontsize=9, color=MUTED)


def plot_tasks(t: pd.DataFrame, path: Path):
    g = t.groupby("category").agg(n=("passed", "size"), ok=("passed", "sum"))
    order = [c for c in LABELS if c in g.index]
    g = g.loc[order[::-1]]
    fig, ax = plt.subplots(figsize=(8.5, 4.6))
    y = np.arange(len(g))
    share = g["ok"] / g["n"] * 100
    ax.barh(y, share, color=[SERIES[1] if c == "paraphrase" else SERIES[0] for c in g.index], height=0.6)
    for yi, (ok, n) in enumerate(zip(g["ok"], g["n"])):
        ax.text(min(ok / n * 100, 100) + 1.5, yi, f"{ok} of {n}", va="center", fontsize=8.5, color=MUTED)
    ax.set_yticks(y)
    ax.set_yticklabels([LABELS[c] for c in g.index], fontsize=9)
    ax.set_xlim(0, 115)
    ax.set_xlabel("Tasks passed, %", color=MUTED, fontsize=9)
    _style(ax, "Rule planner on the evaluation tasks", "Orange: questions worded differently from the planner's rules; the gap a model like Claude has to close")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def plot_red_team(r: pd.DataFrame, path: Path):
    attacks = list(dict.fromkeys(r["attack"]))
    roles = ["AM01", "AM05", "FIN01"]
    fig, ax = plt.subplots(figsize=(9.5, 6.6))
    for i, a in enumerate(attacks):
        for j, u in enumerate(roles):
            row = r[(r.attack == a) & (r.user == u)].iloc[0]
            bad = row.leak or row.unauthorized_action
            label = row.outcome
            col = "#cfe0f5" if label.startswith("blocked") else "#fdf0d5" if label.startswith("allowed") else "#d9efe4"
            col = "#e34948" if bad else col
            ax.add_patch(plt.Rectangle((j, len(attacks) - 1 - i), 0.96, 0.9, color=col))
            ax.text(j + 0.48, len(attacks) - 1 - i + 0.45, label.replace("_", " "), ha="center", va="center", fontsize=7.5, color=TEXT)
    ax.set_xlim(0, len(roles))
    ax.set_ylim(0, len(attacks))
    ax.set_xticks([j + 0.48 for j in range(len(roles))])
    ax.set_xticklabels(["Account manager AM01", "Account manager AM05", "Finance"], fontsize=9)
    ax.set_yticks([len(attacks) - 1 - i + 0.45 for i in range(len(attacks))])
    ax.set_yticklabels(attacks, fontsize=8.5)
    ax.tick_params(length=0)
    _style(ax, "A hostile planner against the guard", f"{len(r)} attack runs: {int(r.leak.sum())} leaks, {int(r.unauthorized_action.sum())} unauthorised actions. "
           "Blue: blocked by a guard rule.\nGreen: nothing outside the user's scope came back. Amber: allowed for Finance, actions only as requests.", grid=None)
    ax.set_title(ax.get_title(loc="left"), loc="left", fontsize=12, color=TEXT, pad=40, fontweight="bold")
    for s in ax.spines.values():
        s.set_visible(False)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def span_summary(trace_dir: Path) -> pd.DataFrame:
    rows = [json.loads(line) for f in trace_dir.glob("*.jsonl") for line in f.read_text().splitlines()]
    d = pd.DataFrame(rows)
    tc = d[d.name == "tool.call"].copy()
    tc["tool"] = tc["attributes"].map(lambda a: a.get("tool"))
    tc["blocked_by"] = tc["attributes"].map(lambda a: a.get("blocked_by"))
    out = tc.groupby("tool").agg(calls=("tool", "size"), blocked=("blocked_by", lambda s: int(s.notna().sum())),
                                 p50_ms=("duration_ms", "median"), p95_ms=("duration_ms", lambda s: s.quantile(0.95))).round(2)
    return out.sort_values("calls", ascending=False)


def main(gate: bool) -> int:
    out = ROOT / "outputs"
    lake = ROOT / "lake"
    built = lakehouse.build_all(lake)
    trace_dir = out / "traces"
    shutil.rmtree(trace_dir, ignore_errors=True)
    agent = Agent(Settings(lake_dir=lake, trace_dir=trace_dir))
    t, r, ru = E.run_tasks(agent), E.run_red_team(agent), E.approval_rules()
    s = E.summary(t, r, ru)
    (out / "figures").mkdir(parents=True, exist_ok=True)
    plot_tasks(t, out / "figures" / "task_results.png")
    plot_red_team(r, out / "figures" / "red_team.png")
    spans = span_summary(trace_dir)
    E.write_tasks_file(E.load_gold(agent))
    t.drop(columns=["trace_id"]).to_csv(out / "task_results.csv", index=False)
    r.to_csv(out / "red_team_results.csv", index=False)
    s["lakehouse"] = {"silver": built["silver"], "gold": built["gold"], "quality_checks_passed": int(built["quality"].passed.sum()),
                      "quality_checks": len(built["quality"])}
    s["failed_gates"] = E.failed_gates(s)
    (out / "eval.json").write_text(json.dumps(s, indent=2, default=float))
    fails = t[~t.passed][["id", "category", "question", "reasons"]]
    lines = ["# Evaluation report", "",
             f"Planner: rules (deterministic stand-in for the model). Release gates: {E.GATES}.", "",
             f"- Core tasks passed: {s['task_success']:.0%} of {len(t[t.category != 'paraphrase'])}",
             f"- Paraphrases passed: {s['paraphrase_success']:.0%} of {len(t[t.category == 'paraphrase'])}",
             f"- Leaks in tasks: {s['leaks_in_tasks']}; red-team runs: {s['red_team_runs']}, leaks {s['red_team_leaks']}, unauthorised actions {s['red_team_unauthorized_actions']}",
             f"- Approval rules correct: {s['approval_rules_correct']:.0%}",
             f"- Latency p50 {s['latency_p50_ms']:.1f} ms, p95 {s['latency_p95_ms']:.1f} ms (no model call)", "",
             "## Tasks by category", "", t.groupby("category").passed.agg(["sum", "size"]).rename(columns={"sum": "passed", "size": "tasks"}).to_markdown(), "",
             "## Failed tasks", "", fails.to_markdown(index=False) if len(fails) else "None.", "",
             "## Red team", "", r.pivot_table(index="attack", columns="user", values="outcome", aggfunc="first").to_markdown(), "",
             "## Tool calls from the traces", "", spans.to_markdown(), ""]
    (out / "eval_report.md").write_text("\n".join(lines))
    print(json.dumps({k: v for k, v in s.items() if k != "lakehouse"}, indent=2, default=float))
    return 1 if gate and s["failed_gates"] else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--gate", action="store_true")
    sys.exit(main(ap.parse_args().gate))
