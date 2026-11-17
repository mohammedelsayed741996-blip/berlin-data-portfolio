"""Charts and the markdown investor report."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

# Validated categorical order (blue, orange, aqua, yellow) and text tokens.
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
TEXT_PRIMARY = "#0b0b0b"
TEXT_SECONDARY = "#52514e"
GRID = "#e4e3df"
SURFACE = "#fcfcfb"
SEQ_BLUE = ["#cfe0f6", "#9cc0ec", "#5f9ae0", "#2a78d6", "#1b5aa8"]


def _style(ax: plt.Axes, title: str, xlabel: str = "", ylabel: str = "") -> None:
    ax.set_facecolor(SURFACE)
    ax.set_title(title, loc="left", fontsize=12, color=TEXT_PRIMARY, pad=10)
    ax.set_xlabel(xlabel, color=TEXT_SECONDARY)
    ax.set_ylabel(ylabel, color=TEXT_SECONDARY)
    ax.tick_params(colors=TEXT_SECONDARY, labelsize=9)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)


def _save(fig: plt.Figure, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.patch.set_facecolor(SURFACE)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def plot_vintage_curves(vintages: pd.DataFrame, path: Path) -> Path:
    """Cumulative default rate by half-year vintage (quarters grouped to keep 6 lines)."""
    df = vintages.copy()
    year = df["vintage"].str[:4]
    half = np.where(df["vintage"].str[-1].astype(int) <= 2, "H1", "H2")
    df["cohort"] = year + "-" + half
    # Only plot ages that every quarter in the half-year has reached, otherwise
    # the line jumps when one quarter drops out of the average.
    reach = df.groupby(["cohort", "vintage"])["months_on_book"].max().groupby("cohort").min()
    df = df.loc[df["months_on_book"] <= df["cohort"].map(reach)]
    agg = (
        df.groupby(["cohort", "months_on_book"])
        .agg(loans=("loans", "sum"), defaults=("cumulative_defaults", "sum"))
        .reset_index()
    )
    agg["rate"] = agg["defaults"] / agg["loans"]
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for i, (cohort, g) in enumerate(agg.groupby("cohort")):
        ax.plot(g["months_on_book"], g["rate"] * 100, color=SERIES[i % len(SERIES)], linewidth=2, label=cohort)
        last = g.iloc[-1]
        ax.annotate(cohort, (last["months_on_book"], last["rate"] * 100), xytext=(4, 0),
                    textcoords="offset points", fontsize=8, color=TEXT_SECONDARY, va="center")
    _style(ax, "Cumulative default rate by origination half-year", "Months on book", "Cumulative default rate (%)")
    ax.legend(frameon=False, fontsize=8, ncol=3, loc="upper left")
    return _save(fig, path)


def plot_delinquency_trend(trend: pd.DataFrame, path: Path) -> Path:
    df = trend.dropna(subset=["dpd30_plus_share"]).copy()
    df["as_of_date"] = pd.to_datetime(df["as_of_date"])
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(df["as_of_date"], df["dpd30_plus_share"] * 100, color=SERIES[0], linewidth=2, label="30+ DPD")
    ax.plot(df["as_of_date"], df["dpd60_plus_share"].fillna(0) * 100, color=SERIES[1], linewidth=2, label="60+ DPD")
    _style(ax, "Share of open balance past due", "", "% of open balance")
    ax.legend(frameon=False, fontsize=9)
    return _save(fig, path)


def plot_calibration(tables: dict[str, pd.DataFrame], path: Path) -> Path:
    fig, ax = plt.subplots(figsize=(6, 5))
    top = 0.0
    for i, (name, t) in enumerate(tables.items()):
        ax.plot(t["predicted_pd"] * 100, t["observed_dr"] * 100, marker="o", markersize=6,
                linewidth=2, color=SERIES[i], label=name)
        top = max(top, t["predicted_pd"].max() * 100, t["observed_dr"].max() * 100)
    ax.plot([0, top * 1.05], [0, top * 1.05], color=TEXT_SECONDARY, linewidth=1, linestyle="--", label="Perfect calibration")
    _style(ax, "Out-of-time calibration by risk decile", "Predicted 12m PD (%)", "Observed 12m default rate (%)")
    ax.legend(frameon=False, fontsize=9)
    return _save(fig, path)


def plot_strategy(strategy: pd.DataFrame, chosen: int, path: Path) -> Path:
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.plot(strategy["approval_rate"] * 100, strategy["approved_bad_rate"] * 100, color=SERIES[0],
            linewidth=2, marker="o", markersize=6)
    last_x = None
    for _, r in strategy.sort_values("approval_rate").iterrows():
        if last_x is not None and r["approval_rate"] - last_x < 0.03:
            continue  # skip labels that would sit on top of each other
        last_x = r["approval_rate"]
        ax.annotate(str(int(r["cutoff"])), (r["approval_rate"] * 100, r["approved_bad_rate"] * 100),
                    xytext=(5, 4), textcoords="offset points", fontsize=8, color=TEXT_SECONDARY)
    sel = strategy.loc[strategy["cutoff"] == chosen].iloc[0]
    ax.scatter([sel["approval_rate"] * 100], [sel["approved_bad_rate"] * 100], s=110, color=SERIES[1],
               zorder=5, edgecolor=SURFACE, linewidth=2, label=f"Chosen cut-off {chosen}")
    _style(ax, "Approval rate vs bad rate of approved loans (labels = score cut-off)",
           "Approval rate (%)", "12m bad rate of approved (%)")
    ax.legend(frameon=False, fontsize=9)
    return _save(fig, path)


def plot_stress(stress: pd.DataFrame, path: Path) -> Path:
    fig, ax = plt.subplots(figsize=(7, 4))
    vals = stress["ecl_coverage"] * 100
    colors = [SEQ_BLUE[min(i + 1, len(SEQ_BLUE) - 1)] for i in range(len(stress))]
    bars = ax.barh(stress["scenario"], vals, color=colors, height=0.55)
    for b, v, e in zip(bars, vals, stress["ecl_eur"]):
        ax.text(b.get_width() + 0.03, b.get_y() + b.get_height() / 2, f"{v:.2f}%  (EUR {e / 1e6:.2f}m)",
                va="center", fontsize=9, color=TEXT_PRIMARY)
    ax.invert_yaxis()
    _style(ax, "ECL coverage of open exposure by scenario", "ECL / exposure (%)")
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.grid(axis="y", visible=False)
    ax.set_xlim(0, vals.max() * 1.45)
    return _save(fig, path)


def plot_sensitivity(sens: pd.DataFrame, path: Path) -> Path:
    df = sens.iloc[::-1]
    fig, ax = plt.subplots(figsize=(7, 4))
    colors = [SERIES[7] if v > 0 else SERIES[0] for v in df["change_pct"]]
    ax.barh(df["shock"], df["change_pct"] * 100, color=colors, height=0.55)
    for y, v in enumerate(df["change_pct"] * 100):
        ax.text(v + (0.6 if v >= 0 else -0.6), y, f"{v:+.1f}%", va="center",
                ha="left" if v >= 0 else "right", fontsize=9, color=TEXT_PRIMARY)
    ax.axvline(0, color=TEXT_SECONDARY, linewidth=1)
    _style(ax, "Change in total ECL, one driver at a time", "Change vs baseline ECL (%)")
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.grid(axis="y", visible=False)
    lim = max(abs(df["change_pct"]).max() * 100 * 1.35, 5)
    ax.set_xlim(-lim, lim)
    return _save(fig, path)


def plot_installer_concentration(inst: pd.DataFrame, path: Path, limit: float = 0.10) -> Path:
    top = inst.head(10).iloc[::-1]
    fig, ax = plt.subplots(figsize=(7, 4.5))
    colors = [SERIES[1] if s > limit else SERIES[0] for s in top["share_of_book"]]
    ax.barh(top["installer_id"], top["share_of_book"] * 100, color=colors, height=0.6)
    ax.axvline(limit * 100, color=TEXT_SECONDARY, linestyle="--", linewidth=1)
    ax.text(limit * 100 + 0.3, len(top) - 0.6, f"{limit:.0%} single-name limit", fontsize=8, color=TEXT_SECONDARY)
    _style(ax, "Top 10 installer partners by open exposure", "Share of open book (%)")
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.grid(axis="y", visible=False)
    return _save(fig, path)


def _md_table(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for _, r in df.iterrows():
        lines.append("| " + " | ".join(str(r[c]) for c in cols) + " |")
    return "\n".join(lines)


def eur(x: float) -> str:
    return f"EUR {x / 1e6:,.2f}m" if abs(x) >= 1e6 else f"EUR {x:,.0f}"


def investor_report(ctx: dict, path: Path) -> Path:
    """Write the monthly investor and lender report as markdown."""
    s = ctx["snapshot"]
    stress = ctx["stress"].copy()
    stress_view = stress[["scenario", "avg_pd_12m", "stage2_share_of_exposure", "ecl_eur", "ecl_coverage", "ecl_vs_baseline"]].copy()
    stress_view["avg_pd_12m"] = (stress_view["avg_pd_12m"] * 100).map("{:.2f}%".format)
    stress_view["stage2_share_of_exposure"] = (stress_view["stage2_share_of_exposure"] * 100).map("{:.1f}%".format)
    stress_view["ecl_eur"] = stress_view["ecl_eur"].map(eur)
    stress_view["ecl_coverage"] = (stress_view["ecl_coverage"] * 100).map("{:.2f}%".format)
    stress_view["ecl_vs_baseline"] = stress_view["ecl_vs_baseline"].map("{:.2f}x".format)

    stage = ctx["ecl_by_stage"].copy()
    stage["exposure_eur"] = stage["exposure_eur"].map(eur)
    stage["ecl_eur"] = stage["ecl_eur"].map(eur)
    stage["coverage"] = (stage["coverage"] * 100).map("{:.2f}%".format)

    top_inst = ctx["installers"].head(5)[["installer_id", "installer_region", "open_loans", "exposure_eur", "share_of_book", "lifetime_default_rate"]].copy()
    top_inst["exposure_eur"] = top_inst["exposure_eur"].map(eur)
    top_inst["share_of_book"] = (top_inst["share_of_book"] * 100).map("{:.1f}%".format)
    top_inst["lifetime_default_rate"] = (top_inst["lifetime_default_rate"] * 100).map("{:.1f}%".format)

    m = ctx["metrics"]
    text = f"""# Residential energy loan portfolio: investor report

As of {ctx['as_of']}. Synthetic data, built to show the reporting workflow.

## Portfolio at a glance

| Metric | Value |
|---|---|
| Open loans | {s['open_loans']:,} |
| Open exposure | {eur(s['exposure_eur'])} |
| 30+ DPD share of balance | {s['dpd30_share']:.2%} |
| Loans in open workout (defaulted) | {s['open_workouts']:,} |
| Lifetime defaults to date | {s['defaults_to_date']:,} ({s['default_rate_to_date']:.2%} of loans written) |
| Largest installer share of book | {s['top_installer_share']:.1%} |
| Installer HHI | {s['hhi']:,.0f} |

## Expected credit loss (IFRS 9 style, baseline)

{_md_table(stage)}

Total ECL is {eur(ctx['ecl_total'])}, or {ctx['ecl_coverage']:.2%} of exposure.

## Stress tests

{_md_table(stress_view)}

The severe scenario raises ECL to {stress.loc[stress['scenario'] == 'Severe recession', 'ecl_vs_baseline'].iloc[0]:.2f}x the baseline.
The largest single driver in the sensitivity run is "{ctx['sensitivity'].iloc[0]['shock']}" ({ctx['sensitivity'].iloc[0]['change_pct']:+.1%} ECL).

## Model performance (12-month PD, out-of-time test)

| Model | AUC | Gini | KS | Brier | Predicted DR | Observed DR |
|---|---|---|---|---|---|---|
| Scorecard (champion) | {m['scorecard']['auc']} | {m['scorecard']['gini']} | {m['scorecard']['ks']} | {m['scorecard']['brier']} | {m['scorecard']['predicted_dr']:.2%} | {m['scorecard']['observed_dr']:.2%} |
| Gradient boosting (challenger) | {m['gbm']['auc']} | {m['gbm']['gini']} | {m['gbm']['ks']} | {m['gbm']['brier']} | {m['gbm']['predicted_dr']:.2%} | {m['gbm']['observed_dr']:.2%} |

Underwriting cut-off: score {ctx['cutoff']} (approval rate {ctx['cutoff_row']['approval_rate']:.1%}, 12m bad rate of approved loans {ctx['cutoff_row']['approved_bad_rate']:.2%} on the test vintages).

## Concentration: top 5 installers

{_md_table(top_inst)}

## Charts

![Vintage curves](figures/vintage_curves.png)
![Delinquency trend](figures/delinquency_trend.png)
![Stress scenarios](figures/stress_scenarios.png)
![Sensitivity](figures/sensitivity_tornado.png)
![Installer concentration](figures/installer_concentration.png)
"""
    path.write_text(text, encoding="utf-8")
    return path
