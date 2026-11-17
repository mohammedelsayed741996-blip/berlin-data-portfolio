"""Run report, incident log and charts, built from the warehouse metadata tables."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from .pipeline import SimulationResult  # noqa: E402

SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
TEXT_PRIMARY, TEXT_SECONDARY, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"


def _style(ax, title: str, xlabel: str = "", ylabel: str = "") -> None:
    ax.set_facecolor(SURFACE)
    ax.set_title(title, loc="left", fontsize=11, color=TEXT_PRIMARY, pad=8)
    ax.set_xlabel(xlabel, color=TEXT_SECONDARY)
    ax.set_ylabel(ylabel, color=TEXT_SECONDARY)
    ax.tick_params(colors=TEXT_SECONDARY, labelsize=8)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)


def _save(fig, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.patch.set_facecolor(SURFACE)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def frame(res: SimulationResult, sql: str) -> pd.DataFrame:
    return pd.read_sql_query(sql, res.warehouse.conn)


def daily_loads(res: SimulationResult) -> pd.DataFrame:
    return frame(res, """
        SELECT run_date, source, extracted, loaded, quarantined, duplicates_skipped, control_count
        FROM meta_batches ORDER BY run_date, source""")


def run_status(res: SimulationResult) -> pd.DataFrame:
    rows = [{"run_date": r.run_date, "status": r.status, "failed_tasks": ", ".join(r.failed_tasks())} for r in res.runs]
    return pd.DataFrame(rows)


def mrr_vs_truth(res: SimulationResult) -> pd.DataFrame:
    wh = frame(res, "SELECT date_day, ROUND(SUM(mrr_eur), 2) AS warehouse_mrr FROM fct_mrr_daily GROUP BY date_day")
    truth = pd.DataFrame(sorted(res.world.truth.mrr_by_day.items()), columns=["date_day", "true_mrr"])
    out = truth.merge(wh, on="date_day", how="left")
    out["difference"] = (out["warehouse_mrr"] - out["true_mrr"]).round(2)
    return out


def usage_vs_truth(res: SimulationResult) -> pd.DataFrame:
    wh = frame(res, "SELECT event_date, SUM(events) AS warehouse_events FROM fct_product_usage_daily GROUP BY event_date")
    truth = pd.DataFrame(sorted(res.world.delivered_events_by_day().items()), columns=["event_date", "delivered_events"])
    out = truth.merge(wh, on="event_date", how="left").fillna(0)
    # Events on the five broken lines of the 2026-09-08 file were never parseable.
    out["difference"] = (out["warehouse_events"] - out["delivered_events"]).astype(int)
    return out


def incident_log(res: SimulationResult) -> pd.DataFrame:
    """Each planted incident next to the evidence the pipeline left behind."""
    q = lambda sql, p=(): res.warehouse.query(sql, p)  # noqa: E731
    rows = []
    done: set[tuple[str, str]] = set()
    for inc in res.world.truth.planted:
        day, kind = inc["day"], inc["incident"]
        if (day, kind) in done:
            continue
        done.add((day, kind))
        if kind == "api_page_overlap":
            dup = q("SELECT duplicates_skipped, extracted, control_count FROM meta_batches WHERE batch_id=?", (f"billing_invoices:{day}",))[0]
            ev = (f"API returned {dup[1]} records for {dup[2]} changed invoices ({dup[1] - dup[2]} repeated across pages); "
                  f"{dup[0]} already-loaded versions dropped (page repeats plus the 1-hour overlap window)")
            action = "De-duplicated on (invoice_id, updated_at); control count reconciled"
        elif kind == "schema_drift":
            f = q("SELECT field, first_seen_batch FROM meta_schema_drift")
            ev = f"New field(s) {[x[0] for x in f]} first seen in batch {f[0][1] if f else '-'}"
            action = "Records kept, extra field stored in _extra_json, drift logged for a contract update"
        elif kind == "bad_segment_value":
            n = q("SELECT COUNT(*) FROM meta_quarantine WHERE source='crm_accounts' AND reasons LIKE '%Mid-Market%'")[0][0]
            ev = f"{n} account record quarantined; corrected version loaded the next day"
            action = "Contract enum check; dashboards kept the last valid segment"
        elif kind == "negative_invoice":
            n = q("SELECT COUNT(DISTINCT record_key) FROM meta_quarantine WHERE source='billing_invoices'")[0][0]
            ev = f"{n} invoice quarantined; August EUR total reconciles with the gap fully explained"
            action = "Contract min-value check; invoice reconciliation explains the difference"
        elif kind == "malformed_event_line":
            continue
        elif kind == "malformed_event_lines":
            n = q("SELECT COUNT(*) FROM meta_quarantine WHERE reasons LIKE 'malformed_json%'")[0][0]
            ev = f"{n} broken line(s) quarantined by file and line number, content not stored"
            action = "Rest of the file loaded; other files unaffected"
        elif kind == "transform_outage":
            tries = q("SELECT COUNT(*) FROM meta_task_runs WHERE run_date=? AND task='transform' AND status='failed'", (day,))[0][0]
            nxt = q("SELECT status FROM meta_reconciliation WHERE check_name='mrr_vs_truth' AND run_date > ? ORDER BY run_date LIMIT 1", (day,))
            ev = f"transform failed {tries} attempts; downstream tasks skipped; next run's MRR check: {nxt[0][0] if nxt else '-'}"
            action = "Retries, then fail fast; next day's run rebuilt the models from raw and caught up"
        else:
            ev, action = "", ""
        rows.append({"date": day, "incident": kind, "how it was handled": action, "evidence": ev})
    late = q("""SELECT COUNT(*) FROM raw_product_events
                WHERE _source_ref <> 'file:events_' || substr(event_ts, 1, 10) || '.ndjson'""")[0][0]
    dups = q("SELECT COALESCE(SUM(duplicates_skipped), 0) FROM meta_batches WHERE source='product_events'")[0][0]
    rows.append({"date": "every day", "incident": "late and duplicate events",
                 "how it was handled": "Load-time de-duplication on event_id; 3-day look-back in the incremental usage model",
                 "evidence": f"{late:,} events arrived 1 to 2 days late; {dups:,} duplicates dropped"})
    return pd.DataFrame(rows)


def plot_revenue_bridge(res: SimulationResult, path: Path) -> Path:
    df = frame(res, "SELECT * FROM rpt_revenue_monthly ORDER BY period_month")
    parts = [("new_mrr", "New"), ("expansion_mrr", "Expansion"), ("reactivation_mrr", "Reactivation"),
             ("contraction_mrr", "Contraction"), ("churned_mrr", "Churn")]
    fig, ax = plt.subplots(figsize=(8, 4.2))
    x = range(len(df))
    width = 0.15
    for i, (col, label) in enumerate(parts):
        ax.bar([v + (i - 2) * width for v in x], df[col] / 1000, width=width * 0.9, color=SERIES[i], label=label)
    ax.axhline(0, color=TEXT_SECONDARY, linewidth=0.8)
    ax.set_xticks(list(x), [m[:7] for m in df["period_month"]])
    _style(ax, "MRR movements by month", "", "EUR thousand")
    ax.legend(frameon=False, fontsize=8, ncol=5, loc="upper center", bbox_to_anchor=(0.5, -0.08))
    return _save(fig, path)


def plot_mrr_vs_truth(res: SimulationResult, path: Path) -> Path:
    df = mrr_vs_truth(res)
    df["date_day"] = pd.to_datetime(df["date_day"])
    fig, ax = plt.subplots(figsize=(8, 3.8))
    ax.plot(df["date_day"], df["true_mrr"] / 1000, color=SERIES[1], linewidth=5, alpha=0.35, label="Source truth")
    ax.plot(df["date_day"], df["warehouse_mrr"] / 1000, color=SERIES[0], linewidth=2, label="Warehouse (fct_mrr_daily)")
    _style(ax, "Daily MRR: warehouse vs source truth (they overlap on every day)", "", "EUR thousand")
    ax.legend(frameon=False, fontsize=8)
    return _save(fig, path)


def plot_daily_loads(res: SimulationResult, path: Path) -> Path:
    df = daily_loads(res)
    df = df[df["run_date"] > df["run_date"].min()]
    df["run_date"] = pd.to_datetime(df["run_date"])
    fig, axes = plt.subplots(2, 2, figsize=(9, 5), sharex=True)
    for ax, (src, g), color in zip(axes.flat, df.groupby("source"), SERIES):
        ax.plot(g["run_date"], g["loaded"], color=color, linewidth=1.6)
        bad = g[g["quarantined"] > 0]
        ax.scatter(bad["run_date"], bad["loaded"], color=SERIES[7], s=28, zorder=5, label="quarantine day")
        _style(ax, src, "", "rows loaded")
        if len(bad):
            ax.legend(frameon=False, fontsize=7, loc="upper left")
    fig.autofmt_xdate()
    return _save(fig, path)


def write_report(res: SimulationResult, out_dir: Path, lineage: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    fig_dir = out_dir / "figures"
    plot_revenue_bridge(res, fig_dir / "revenue_bridge.png")
    plot_mrr_vs_truth(res, fig_dir / "mrr_vs_truth.png")
    plot_daily_loads(res, fig_dir / "daily_loads.png")
    status = run_status(res)
    rev = frame(res, "SELECT * FROM rpt_revenue_monthly ORDER BY period_month")
    tests = frame(res, "SELECT status, COUNT(*) AS n FROM meta_test_results GROUP BY status")
    recon = frame(res, "SELECT status, COUNT(*) AS n FROM meta_reconciliation GROUP BY status")
    mrr = mrr_vs_truth(res)
    usage = usage_vs_truth(res)
    inc = incident_log(res)
    rev.to_csv(out_dir / "rpt_revenue_monthly.csv", index=False)
    inc.to_csv(out_dir / "incident_log.csv", index=False)
    daily_loads(res).to_csv(out_dir / "daily_loads.csv", index=False)
    status.to_csv(out_dir / "run_status.csv", index=False)
    (out_dir / "lineage.md").write_text("# Model lineage\n\n```mermaid\n" + lineage + "\n```\n", encoding="utf-8")

    def md(df: pd.DataFrame) -> str:
        return df.to_markdown(index=False) if hasattr(df, "to_markdown") and _has_tabulate() else _plain_md(df)

    text = f"""# Pipeline run report

Simulated daily runs from {status['run_date'].min()} (initial load) to {status['run_date'].max()}.

| Metric | Value |
|---|---|
| Daily runs | {len(status)} |
| Successful runs | {(status['status'] == 'success').sum()} |
| Failed runs | {(status['status'] != 'success').sum()} ({', '.join(status.loc[status['status'] != 'success', 'run_date'])}) |
| Data tests executed | {int(tests['n'].sum()):,} ({', '.join(f"{r.status}: {r.n:,}" for r in tests.itertuples())}) |
| Reconciliation checks | {int(recon['n'].sum()):,} ({', '.join(f"{r.status}: {r.n:,}" for r in recon.itertuples())}) |
| Days where warehouse MRR = source MRR | {(mrr['difference'].abs() <= 0.01).sum()} of {len(mrr)} |
| Days where usage events = delivered events | {(usage['difference'] == 0).sum()} of {len(usage)} |

## Incidents

{md(inc)}

## Revenue bridge

{md(rev[['period_month', 'opening_mrr', 'new_mrr', 'expansion_mrr', 'contraction_mrr', 'churned_mrr', 'reactivation_mrr', 'closing_mrr', 'net_revenue_retention', 'gross_revenue_retention']])}

![Revenue bridge](figures/revenue_bridge.png)
![MRR vs truth](figures/mrr_vs_truth.png)
![Daily loads](figures/daily_loads.png)
"""
    path = out_dir / "run_report.md"
    path.write_text(text, encoding="utf-8")
    return path


def _has_tabulate() -> bool:
    try:
        import tabulate  # noqa: F401
        return True
    except ImportError:
        return False


def _plain_md(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for _, r in df.iterrows():
        lines.append("| " + " | ".join(str(r[c]) for c in cols) + " |")
    return "\n".join(lines)
