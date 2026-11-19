"""Charts, the Excel MI pack and the management report (English, with a German summary)."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import networkx as nx  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.colors import ListedColormap  # noqa: E402
from openpyxl import Workbook  # noqa: E402
from openpyxl.formatting.rule import CellIsRule, FormulaRule  # noqa: E402
from openpyxl.styles import Alignment, Font, PatternFill  # noqa: E402

from . import config as C  # noqa: E402

SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
TEXT_PRIMARY, TEXT_SECONDARY, GRID, SURFACE, NEUTRAL = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb", "#9b9a95"
RAG = {"GREEN": "#1baf7a", "AMBER": "#eda100", "RED": "#e34948", "n/a": "#e4e3df"}
KRI_LABELS = {
    "tm_feed_completeness_gap_pct": "TM feed: transactions missing",
    "alerts_over_sla_pct": "Alerts closed after 30 days",
    "missing_rationale_pct": "Closed alerts without rationale",
    "qa_error_rate": "QA decision error rate",
    "median_days_alert_to_sar": "Median days alert to SAR",
    "screening_late_count": "New clients screened late",
    "overdue_reviews_high_risk": "High-risk reviews overdue",
}


def _style(ax, title: str, subtitle: str = "", grid_axis: str = "y") -> None:
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


def plot_kri_heatmap(kri: pd.DataFrame, path: Path) -> Path:
    order = list(KRI_LABELS)
    piv = kri.pivot(index="kri", columns="month", values="status").reindex(order)
    codes = {"n/a": 0, "GREEN": 1, "AMBER": 2, "RED": 3}
    M = piv.replace(codes).astype(float).values
    fig, ax = plt.subplots(figsize=(10, 3.8))
    cmap = ListedColormap([RAG["n/a"], RAG["GREEN"], RAG["AMBER"], RAG["RED"]])
    ax.imshow(M, cmap=cmap, vmin=0, vmax=3, aspect="auto")
    ax.set_xticks(range(len(piv.columns)))
    ax.set_xticklabels([pd.Period(m, freq="M").strftime("%b %y") for m in piv.columns], fontsize=8.5)
    ax.set_yticks(range(len(order)))
    ax.set_yticklabels([KRI_LABELS[k] for k in order], fontsize=9)
    ax.set_xticks(np.arange(-0.5, len(piv.columns)), minor=True)
    ax.set_yticks(np.arange(-0.5, len(order)), minor=True)
    ax.grid(which="minor", color=SURFACE, linewidth=2.5)
    ax.tick_params(which="minor", length=0)
    for s in ax.spines.values():
        s.set_visible(False)
    for i in range(M.shape[0]):
        for j in range(M.shape[1]):
            lab = {1: "G", 2: "A", 3: "R"}.get(int(M[i, j]), "")
            ax.text(j, i, lab, ha="center", va="center", fontsize=8, color="white", fontweight="bold")
    _style(ax, "Key risk indicators against risk appetite", "G green, A amber, R red; grey = not measured that month", grid_axis="")
    return _save(fig, path)


def plot_feed_gap(tx: pd.DataFrame, feed_ids: pd.DataFrame, path: Path) -> Path:
    psp = C.FEED_GAP[2]
    t = tx[(tx["channel"] == "CARD") & (tx["psp"] == psp) & (tx["type"] == "DEPOSIT")]
    t = t[t["date"].between("2026-05-01", "2026-08-15")]
    led = t.groupby("date").size()
    fed = t[t["tx_id"].isin(feed_ids["tx_id"])].groupby("date").size().reindex(led.index, fill_value=0)
    x = pd.to_datetime(led.index)
    fig, ax = plt.subplots(figsize=(9.5, 3.8))
    ax.plot(x, led.values, color=NEUTRAL, linewidth=2, label="Core ledger")
    ax.plot(x, fed.values, color=SERIES[0], linewidth=2, label="Received by monitoring")
    ax.axvspan(pd.Timestamp(C.FEED_GAP[0]), pd.Timestamp(C.FEED_GAP[1]), color=SERIES[7], alpha=0.08)
    ax.text(pd.Timestamp(C.FEED_GAP[0]) + pd.Timedelta(days=1), ax.get_ylim()[1] * 0.92, "Feed gap", color=SERIES[7], fontsize=9)
    ax.legend(frameon=False, fontsize=8.5, labelcolor=TEXT_SECONDARY, loc="lower left")
    ax.set_ylabel("Deposits per day", color=TEXT_SECONDARY, fontsize=9)
    _style(ax, f"Card deposits via {psp}: ledger vs monitoring feed", "Daily counts; the rules never saw the deposits in the shaded period")
    return _save(fig, path)


def plot_rule_volume(alerts: pd.DataFrame, rule: str, path: Path) -> Path:
    m = alerts[alerts["rule"] == rule].groupby("month").size().reindex(C.MONTHS, fill_value=0)
    fig, ax = plt.subplots(figsize=(9, 3.6))
    cols = [SERIES[0] if mm < C.R02_CHANGE_DATE[:7] else SERIES[1] for mm in C.MONTHS]
    ax.bar(range(len(m)), m.values, color=cols, width=0.65)
    ax.set_xticks(range(len(m)))
    ax.set_xticklabels([pd.Period(x, freq="M").strftime("%b %y") for x in C.MONTHS], fontsize=8.5)
    ax.axvline(C.MONTHS.index(C.R02_CHANGE_DATE[:7]) - 0.5, color=TEXT_SECONDARY, linestyle=(0, (4, 3)))
    ax.text(C.MONTHS.index(C.R02_CHANGE_DATE[:7]) - 0.4, m.max() * 0.95, "threshold changed\n(no approval)", fontsize=8.5, color=TEXT_SECONDARY, va="top")
    _style(ax, f"{rule} structuring alerts per month", C.RULES[rule])
    return _save(fig, path)


def plot_qa(qa_an: pd.DataFrame, path: Path) -> Path:
    d = qa_an[qa_an["error_type"] == "decision_error"].sort_values("analyst")
    fig, ax = plt.subplots(figsize=(8.5, 3.8))
    x = np.arange(len(d))
    colors = [SERIES[7] if a == C.WEAK_ANALYST else SERIES[0] for a in d["analyst"]]
    ax.errorbar(x, d["error_rate"] * 100, yerr=[(d["error_rate"] - d["ci_low"]) * 100, (d["ci_high"] - d["error_rate"]) * 100],
                fmt="none", ecolor=GRID, elinewidth=6, capsize=0)
    ax.scatter(x, d["error_rate"] * 100, s=70, color=colors, zorder=3)
    ax.axhline(C.QA_TOLERABLE_ERROR * 100, color=TEXT_SECONDARY, linestyle=(0, (4, 3)), linewidth=1.2)
    ax.text(len(d) - 0.6, C.QA_TOLERABLE_ERROR * 100 + 0.8, "tolerable 5%", fontsize=8, color=TEXT_SECONDARY, ha="right")
    ax.set_xticks(x)
    ax.set_xticklabels([f"{a}\n(n={n})" for a, n in zip(d["analyst"], d["sampled"])], fontsize=8.5)
    ax.set_ylabel("Wrongly closed, % of sample", color=TEXT_SECONDARY, fontsize=9)
    _style(ax, "QA re-review of closed alerts, by analyst", "Dot = error rate, bar = 95% Clopper-Pearson interval")
    return _save(fig, path)


def plot_coverage(cov: pd.DataFrame, path: Path) -> Path:
    rules = list(C.RULES) + ["any_rule"]
    M = cov[rules].values
    fig, ax = plt.subplots(figsize=(8.5, 3.6))
    ax.imshow(M, cmap="Blues", vmin=0, vmax=1.3, aspect="auto")
    for i in range(M.shape[0]):
        for j in range(M.shape[1]):
            v = M[i, j]
            ax.text(j, i, f"{v:.0%}" if v else "·", ha="center", va="center", fontsize=8.5,
                    color="white" if v > 0.6 else (SERIES[7] if (j == len(rules) - 1 and v == 0) else TEXT_PRIMARY),
                    fontweight="bold" if j == len(rules) - 1 else None)
    ax.set_xticks(range(len(rules)))
    ax.set_xticklabels(rules[:-1] + ["Any rule"], fontsize=9)
    ax.set_yticks(range(len(cov)))
    ax.set_yticklabels(cov["typology"], fontsize=9)
    for s in ax.spines.values():
        s.set_visible(False)
    _style(ax, "Which rule catches which typology", "Share of planted clients alerted while the behaviour lasted", grid_axis="")
    return _save(fig, path)


def plot_networks(clients: pd.DataFrame, nets: pd.DataFrame, path: Path) -> Path:
    G = nx.Graph()
    for r in nets.itertuples():
        ids = r.client_ids.split(", ")
        hub = f"payout {r.network_id}"
        G.add_node(hub, kind="account")
        for c in ids:
            G.add_node(c, kind="client")
            G.add_edge(c, hub)
        if r.shared_device:
            dev = f"device {r.network_id}"
            G.add_node(dev, kind="device")
            for c in ids:
                G.add_edge(c, dev)
    pos = nx.spring_layout(G, seed=4, k=0.5)
    fig, ax = plt.subplots(figsize=(8.5, 5))
    nx.draw_networkx_edges(G, pos, ax=ax, edge_color=GRID, width=1.2)
    kinds = nx.get_node_attributes(G, "kind")
    for kind, color, size in [("client", SERIES[0], 60), ("account", SERIES[7], 160), ("device", SERIES[3], 120)]:
        nodes = [n for n, k in kinds.items() if k == kind]
        nx.draw_networkx_nodes(G, pos, nodelist=nodes, node_color=color, node_size=size, ax=ax, label=
                               {"client": "Client", "account": "Shared payout account", "device": "Shared device"}[kind])
    ax.legend(frameon=False, fontsize=8.5, labelcolor=TEXT_SECONDARY, loc="lower left", scatterpoints=1)
    ax.axis("off")
    _style(ax, f"{len(nets)} client networks the transaction rules missed", "Linked by a shared payout account or device; the rules did not flag the pattern", grid_axis="")
    return _save(fig, path)


# ---------------------------------------------------------------------------- Excel MI pack
HEAD_FILL = PatternFill("solid", fgColor="1F3864")
HEAD_FONT = Font(bold=True, color="FFFFFF")
INPUT = Font(color="1F4E79")
PCT = "0.0%"
NUM = "#,##0"


def _head(ws, headers):
    for j, h in enumerate(headers, start=1):
        c = ws.cell(row=1, column=j, value=h)
        c.fill, c.font = HEAD_FILL, HEAD_FONT
        c.alignment = Alignment(wrap_text=True, horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 32
    ws.freeze_panes = "B2"


def write_excel(path: Path, *, kri, kpis, rules, cov, qa_an, findings, comp, screening, reviews) -> Path:
    wb = Workbook()
    ws = wb.active
    ws.title = "Read me"
    for i, (k, v) in enumerate([
        ("AML oversight MI pack", f"Mobile broker, Germany (fictional). Period {C.MONTHS[0]} to {C.MONTHS[-1]}."),
        ("Data", "Synthetic. Client names, accounts and watchlist entries are invented; analysts are codes."),
        ("Inputs", "Blue numbers come from the case system and the ledger. Black numbers are formulas."),
        ("RAG", "Green up to the amber limit, amber up to the red limit, red above it. Limits are the risk appetite."),
        ("Sheets", "KRI dashboard · Alert KPIs · Rules · Typology coverage · QA · Findings · Completeness · Screening · Reviews"),
    ], start=1):
        ws.cell(row=i, column=1, value=k).font = Font(bold=True, color="1F3864", size=14 if i == 1 else 11)
        ws.cell(row=i, column=2, value=v)
    ws.column_dimensions["A"].width = 24
    ws.column_dimensions["B"].width = 110

    # KRI dashboard: values per month, limits, status by formula
    ws = wb.create_sheet("KRI dashboard")
    months = C.MONTHS
    _head(ws, ["KRI", "Amber limit", "Red limit"] + [pd.Period(m, freq="M").strftime("%b %y") for m in months] + ["Latest status"])
    piv = kri.pivot(index="kri", columns="month", values="value").reindex(list(KRI_LABELS))
    red = PatternFill("solid", fgColor="F8D7DA")
    amb = PatternFill("solid", fgColor="FFF3CD")
    grn = PatternFill("solid", fgColor="D4EDDA")
    for i, k in enumerate(piv.index, start=2):
        ws.cell(row=i, column=1, value=KRI_LABELS[k])
        ws.cell(row=i, column=2, value=C.KRI_LIMITS[k][0])
        ws.cell(row=i, column=3, value=C.KRI_LIMITS[k][1])
        fmt = PCT if k.endswith("pct") or k.endswith("rate") else "0.0"
        for col in (2, 3):
            ws.cell(row=i, column=col).number_format = fmt
        for j, m in enumerate(months, start=4):
            v = piv.loc[k, m]
            if pd.notna(v):
                c = ws.cell(row=i, column=j, value=float(v))
                c.number_format, c.font = fmt, INPUT
        last_col = ws.cell(row=i, column=3 + len(months)).column_letter
        first_col = ws.cell(row=i, column=4).column_letter
        latest = f"LOOKUP(2,1/({first_col}{i}:{last_col}{i}<>\"\"),{first_col}{i}:{last_col}{i})"
        ws.cell(row=i, column=4 + len(months), value=f'=IFERROR(IF({latest}<=B{i},"GREEN",IF({latest}<=C{i},"AMBER","RED")),"n/a")')
        rng = f"{first_col}{i}:{last_col}{i}"
        ws.conditional_formatting.add(rng, FormulaRule(formula=[f'AND({first_col}{i}<>"",{first_col}{i}>$C{i})'], fill=red))
        ws.conditional_formatting.add(rng, FormulaRule(formula=[f'AND({first_col}{i}<>"",{first_col}{i}>$B{i})'], fill=amb))
        ws.conditional_formatting.add(rng, FormulaRule(formula=[f'AND({first_col}{i}<>"",{first_col}{i}<=$B{i})'], fill=grn))
    sc = ws.cell(row=2, column=4 + len(months)).column_letter
    ws.conditional_formatting.add(f"{sc}2:{sc}{len(piv) + 1}", CellIsRule(operator="equal", formula=['"RED"'], fill=red))
    ws.conditional_formatting.add(f"{sc}2:{sc}{len(piv) + 1}", CellIsRule(operator="equal", formula=['"AMBER"'], fill=amb))
    ws.conditional_formatting.add(f"{sc}2:{sc}{len(piv) + 1}", CellIsRule(operator="equal", formula=['"GREEN"'], fill=grn))
    ws.column_dimensions["A"].width = 34
    for j in range(2, 5 + len(months)):
        ws.column_dimensions[ws.cell(row=1, column=j).column_letter].width = 10

    # Alert KPIs
    ws = wb.create_sheet("Alert KPIs")
    cols = ["month", "alerts_created", "alerts_closed", "backlog_month_end", "backlog_over_sla", "median_handling_days",
            "escalation_rate", "missing_rationale_pct", "sars_filed", "median_days_alert_to_sar"]
    _head(ws, ["Month", "Created", "Closed", "Backlog at month end", "Backlog over SLA", "Median handling days",
               "Escalation rate", "Missing rationale", "SARs filed", "Median days alert to SAR", "Backlog change"])
    for i, r in enumerate(kpis[cols].itertuples(index=False), start=2):
        for j, v in enumerate(r, start=1):
            c = ws.cell(row=i, column=j, value=None if (isinstance(v, float) and np.isnan(v)) else v)
            if j > 1:
                c.font = INPUT
            if j in (7, 8):
                c.number_format = PCT
        ws.cell(row=i, column=11, value=f"=D{i}-D{i - 1}" if i > 2 else None)
    t = len(kpis) + 2
    ws.cell(row=t, column=1, value="Total").font = Font(bold=True)
    for col in "BCI":
        ws[f"{col}{t}"] = f"=SUM({col}2:{col}{t - 1})"
        ws[f"{col}{t}"].font = Font(bold=True)
    for col in "ABCDEFGHIJK":
        ws.column_dimensions[col].width = 14

    # Rules
    ws = wb.create_sheet("Rules")
    _head(ws, ["Rule", "Description", "Alerts", "Escalated", "SARs", "Escalation rate", "SAR conversion", "False positive share"])
    for i, r in enumerate(rules.itertuples(), start=2):
        for j, v in enumerate([r.rule, r.description, r.alerts, r.escalated, r.sars], start=1):
            c = ws.cell(row=i, column=j, value=int(v) if j > 2 else v)
            if j > 2:
                c.font = INPUT
        ws[f"F{i}"], ws[f"G{i}"], ws[f"H{i}"] = f"=D{i}/C{i}", f"=E{i}/C{i}", f"=1-E{i}/C{i}"
        for col in "FGH":
            ws[f"{col}{i}"].number_format = PCT
    ws.column_dimensions["B"].width = 70

    # Typology coverage
    ws = wb.create_sheet("Typology coverage")
    rcols = list(C.RULES) + ["any_rule"]
    _head(ws, ["Typology", "Clients"] + rcols)
    for i, r in enumerate(cov.itertuples(index=False), start=2):
        ws.cell(row=i, column=1, value=r.typology)
        ws.cell(row=i, column=2, value=r.clients)
        for j, rc in enumerate(rcols, start=3):
            c = ws.cell(row=i, column=j, value=float(getattr(r, rc)))
            c.number_format = "0%"
    last = ws.cell(row=1, column=2 + len(rcols)).column_letter
    ws.conditional_formatting.add(f"{last}2:{last}{len(cov) + 1}", CellIsRule(operator="equal", formula=["0"], fill=red))
    ws.column_dimensions["A"].width = 28

    # QA
    ws = wb.create_sheet("QA")
    d = qa_an[qa_an["error_type"] == "decision_error"]
    doc = qa_an[qa_an["error_type"] == "documentation_error"].set_index("analyst")
    _head(ws, ["Analyst", "Sampled", "Decision errors", "Decision error rate", "95% CI low", "95% CI high",
               "Documentation errors", "Documentation error rate", "Above tolerable 5%?"])
    for i, r in enumerate(d.itertuples(), start=2):
        ws.cell(row=i, column=1, value=r.analyst)
        for j, v in [(2, r.sampled), (3, r.errors), (5, r.ci_low), (6, r.ci_high), (7, int(doc.loc[r.analyst, "errors"]))]:
            c = ws.cell(row=i, column=j, value=v)
            c.font = INPUT
        ws[f"D{i}"], ws[f"H{i}"] = f"=C{i}/B{i}", f"=G{i}/B{i}"
        ws[f"I{i}"] = f'=IF(E{i}>{C.QA_TOLERABLE_ERROR},"YES (whole CI above)",IF(D{i}>{C.QA_TOLERABLE_ERROR},"possibly",""))'
        for col in "DEFH":
            ws[f"{col}{i}"].number_format = PCT
    t = len(d) + 2
    ws[f"A{t}"] = "All analysts"
    ws[f"B{t}"], ws[f"C{t}"], ws[f"G{t}"] = f"=SUM(B2:B{t - 1})", f"=SUM(C2:C{t - 1})", f"=SUM(G2:G{t - 1})"
    ws[f"D{t}"], ws[f"H{t}"] = f"=C{t}/B{t}", f"=G{t}/B{t}"
    ws[f"D{t}"].number_format = ws[f"H{t}"].number_format = PCT
    ws[f"A{t + 2}"] = f"Sample design: {C.QA_CONFIDENCE:.0%} confidence that the error rate is below {C.QA_TOLERABLE_ERROR:.0%} if no error is found (59 cases a quarter), stratified by analyst."
    for col in "ABCDEFGHI":
        ws.column_dimensions[col].width = 16

    # Findings
    ws = wb.create_sheet("Findings")
    _head(ws, ["ID", "Severity", "Area", "Observation", "Action", "Owner", "Due", "Status"])
    for i, r in enumerate(findings[["finding_id", "severity", "area", "observation", "action", "owner", "due", "status"]].itertuples(index=False), start=2):
        for j, v in enumerate(r, start=1):
            c = ws.cell(row=i, column=j, value=v)
            c.alignment = Alignment(wrap_text=True, vertical="top")
    ws.conditional_formatting.add(f"B2:B{len(findings) + 1}", CellIsRule(operator="equal", formula=['"Critical"'], fill=red))
    ws.conditional_formatting.add(f"B2:B{len(findings) + 1}", CellIsRule(operator="equal", formula=['"High"'], fill=amb))
    for col, w in zip("ABCDEFGH", [6, 10, 22, 60, 50, 22, 12, 9]):
        ws.column_dimensions[col].width = w
    n = len(findings) + 3
    ws[f"C{n}"] = "Open critical / high"
    ws[f"D{n}"] = f'=COUNTIFS(B2:B{n - 2},"Critical",H2:H{n - 2},"open")&" critical, "&COUNTIFS(B2:B{n - 2},"High",H2:H{n - 2},"open")&" high"'

    # Completeness
    ws = wb.create_sheet("Completeness")
    _head(ws, ["Month", "Source", "Ledger count", "Feed count", "Missing count", "Missing %", "Missing EUR"])
    for i, r in enumerate(comp.itertuples(), start=2):
        ws.cell(row=i, column=1, value=r.month)
        ws.cell(row=i, column=2, value=r.source)
        ws.cell(row=i, column=3, value=int(r.ledger_count)).font = INPUT
        ws.cell(row=i, column=4, value=int(r.feed_count)).font = INPUT
        ws[f"E{i}"], ws[f"F{i}"] = f"=C{i}-D{i}", f"=IF(C{i}=0,0,E{i}/C{i})"
        ws[f"F{i}"].number_format = "0.00%"
        ws.cell(row=i, column=7, value=float(r.missing_eur)).number_format = NUM
    ws.conditional_formatting.add(f"E2:E{len(comp) + 1}", CellIsRule(operator="greaterThan", formula=["0"], fill=red))
    for col in "ABCDEFG":
        ws.column_dimensions[col].width = 14

    # Screening and reviews
    ws = wb.create_sheet("Screening")
    _head(ws, ["Measure", "Value"])
    for i, (k, v) in enumerate(screening.items(), start=2):
        ws.cell(row=i, column=1, value=k.replace("_", " "))
        c = ws.cell(row=i, column=2, value=v)
        if k == "false_positive_rate":
            c.number_format = PCT
    ws.column_dimensions["A"].width = 30
    ws.column_dimensions["B"].width = 30
    ws = wb.create_sheet("Reviews")
    _head(ws, ["Risk rating", "Clients", "Overdue", "Overdue %"])
    for i, r in enumerate(reviews.itertuples(), start=2):
        ws.cell(row=i, column=1, value=r.risk_rating)
        ws.cell(row=i, column=2, value=int(r.clients)).font = INPUT
        ws.cell(row=i, column=3, value=int(r.overdue)).font = INPUT
        ws[f"D{i}"], ws[f"D{i}"].number_format = f"=C{i}/B{i}", PCT

    for s in wb.worksheets:
        s.sheet_view.showGridLines = s.title == "Read me"
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path


# ---------------------------------------------------------------------------- management report
def management_report(path: Path, *, findings, kri, kpis, rules, cov, screening, comp, qa_an, nets, btl, vc) -> Path:
    latest = kri[kri["month"] == C.MONTHS[-1]]
    red = latest[latest["status"] == "RED"]
    sev = findings["severity"].value_counts()
    d = qa_an[qa_an["error_type"] == "decision_error"]
    weak = d.set_index("analyst").loc[C.WEAK_ANALYST]
    others = d[d["analyst"] != C.WEAK_ANALYST]
    missing = comp["missing_count"].sum()
    lines = [
        f"# AML oversight report, {pd.Period(C.MONTHS[0], freq='M').strftime('%B %Y')} to {pd.Period(C.MONTHS[-1], freq='M').strftime('%B %Y')}", "",
        "For senior management and the Risk & Compliance Committee. Synthetic data; the broker, clients and analysts are fictional.", "",
        "## Summary", "",
        f"Oversight raised {len(findings)} findings: {sev.get('Critical', 0)} critical, {sev.get('High', 0)} high and {sev.get('Medium', 0)} medium. "
        f"In September {len(red)} of {latest['status'].ne('n/a').sum()} measured KRIs were red.", "",
        "| ID | Severity | Area | Observation | Owner | Due |", "|---|---|---|---|---|---|",
        *[f"| {r.finding_id} | {r.severity} | {r.area} | {r.observation} | {r.owner} | {r.due} |" for r in findings.itertuples()], "",
        "## Monitoring coverage", "",
        f"- {int(missing)} card deposits never reached transaction monitoring, so none of the rules saw them.",
        f"- R02 alert volume fell {abs(vc['change_pct']):.0%} after April. Re-running the rule with the approved setting (3 deposits) shows "
        f"{int(btl.loc[btl['min_deposits'] == 3, 'structuring_clients'].iloc[0])} structuring clients would have alerted; the current setting still catches "
        f"{int(btl.loc[btl['min_deposits'] == 5, 'structuring_clients'].iloc[0])}, but the approved threshold must be restored and the gap looked back on.",
        f"- {len(nets)} groups of six clients share a payout account or device. No rule looks at that, and the rules alerted on just {round(cov.loc[cov['typology'] == 'T4 mule ring', 'any_rule'].iloc[0] * 36)} of the 36 members, for an unrelated deposit.", "",
        "## Alert handling", "",
        f"- QA re-reviewed {int(d['sampled'].sum())} closed alerts over four quarters. Analyst {C.WEAK_ANALYST} wrongly closed {weak['error_rate']:.0%} "
        f"of sampled cases (95% interval {weak['ci_low']:.0%} to {weak['ci_high']:.0%}); the other analysts together {others['errors'].sum() / others['sampled'].sum():.1%}.",
        f"- Summer staffing pushed alerts closed after 30 days to {kpis['closed_over_sla_pct'].max():.0%} in August, and the median time from alert to SAR "
        f"to {kpis['median_days_alert_to_sar'].max():.0f} days in September.", "",
        "## Screening", "",
        f"- {screening['hits']:,} hits, {screening['false_positive_rate']:.0%} closed as false positives. One sanctions hit was closed wrongly (finding F05).",
        f"- {screening['screened_late']} new clients were screened late during a batch outage.", "",
        "## Kurzfassung für die Geschäftsleitung", "",
        f"Die Überwachung hat {len(findings)} Feststellungen ergeben, davon {sev.get('Critical', 0)} kritisch und {sev.get('High', 0)} hoch:",
        "",
        "- Ein Sanktionstreffer wurde fälschlich als Fehltreffer geschlossen. Konto sperren, Geldwäschebeauftragten sofort informieren.",
        f"- {int(missing)} Kartenzahlungen eines Zahlungsdienstleisters sind nicht im Monitoring angekommen. Nachladen und Regeln erneut laufen lassen.",
        "- Ein Regelschwellenwert wurde ohne Freigabe geändert. Genehmigten Wert wiederherstellen.",
        f"- {len(nets)} Kundengruppen teilen sich ein Auszahlungskonto oder ein Gerät (mögliche Finanzagenten). Keine Regel deckt das ab.",
        f"- Ein Analyst schließt zu viele echte Verdachtsfälle. Alle seine Schließungen werden nachgeprüft.", "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
