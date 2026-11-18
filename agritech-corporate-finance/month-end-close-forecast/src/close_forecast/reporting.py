"""Charts, the Excel controlling pack, the close memo and the Power BI export."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from openpyxl import Workbook  # noqa: E402
from openpyxl.formatting.rule import CellIsRule, FormulaRule  # noqa: E402
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side  # noqa: E402
from openpyxl.utils import get_column_letter  # noqa: E402

from . import config as C  # noqa: E402
from .fiscal import fiscal_months, fiscal_year  # noqa: E402

SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
TEXT_PRIMARY, TEXT_SECONDARY, GRID, SURFACE, NEUTRAL = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb", "#9b9a95"
FAV, UNFAV = SERIES[0], SERIES[1]


def _style(ax, title: str, subtitle: str = "") -> None:
    ax.set_facecolor(SURFACE)
    ax.figure.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=TEXT_SECONDARY, labelsize=9)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.set_title(title, loc="left", fontsize=12, color=TEXT_PRIMARY, pad=22 if subtitle else 8, fontweight="bold")
    if subtitle:
        ax.text(0, 1.02, subtitle, transform=ax.transAxes, fontsize=9, color=TEXT_SECONDARY)


def _meur(x, _=None) -> str:
    return f"{x / 1e6:,.1f}m"


def plot_ebit_bridge(bridge: pd.DataFrame, path: Path) -> Path:
    """Waterfall from budget EBIT YTD to actual EBIT YTD."""
    fig, ax = plt.subplots(figsize=(9.5, 4.6))
    levels, running = [], 0.0
    for r in bridge.itertuples():
        running = r.value if r.kind == "total" else running + r.value
        levels.append(running)
    span = max(levels) - min(levels) + 1
    floor = min(levels) - 0.35 * span
    ceiling = max(levels) + 0.25 * span
    running = 0.0
    for i, r in enumerate(bridge.itertuples()):
        if r.kind == "total":
            ax.bar(i, r.value - floor, bottom=floor, color=NEUTRAL, width=0.62)
            running = r.value
            top, label = r.value, _meur(r.value)
        else:
            bottom = running if r.value >= 0 else running + r.value
            ax.bar(i, abs(r.value), bottom=bottom, color=FAV if r.value >= 0 else UNFAV, width=0.62,
                   edgecolor=SURFACE, linewidth=2)
            top, label = bottom + abs(r.value), f"{r.value / 1e6:+,.2f}m"
            running += r.value
        ax.text(i, top + span * 0.04, label, ha="center", fontsize=8.5, color=TEXT_PRIMARY)
    ax.set_ylim(floor, ceiling)
    ax.set_xticks(range(len(bridge)))
    ax.set_xticklabels(bridge["step"], fontsize=8.5, color=TEXT_SECONDARY)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(_meur))
    _style(ax, "EBIT, budget to actual, FY 2026/27 July to September",
           "EUR; blue helps EBIT, orange hurts it. Q1 is a loss in every year: seed sales peak in spring")
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def ebit_bridge(pvm: pd.DataFrame, is_ytd: pd.DataFrame) -> pd.DataFrame:
    lines = is_ytd.set_index("line")
    rows = [("Budget EBIT", lines.loc["EBIT", "budget_ytd"], "total"),
            ("Volume", pvm["volume_effect_eur"].sum(), "delta"),
            ("Price", pvm["price_effect_eur"].sum(), "delta")]
    for name, short in [("Cost of sales", "Cost of sales"), ("Selling", "Selling"),
                        ("Research and development", "R&D"), ("General and administration", "G&A")]:
        rows.append((short, lines.loc[name, "actual_ytd"] - lines.loc[name, "budget_ytd"], "delta"))
    other = lines.loc["EBIT", "actual_ytd"] - sum(r[1] for r in rows)
    if abs(other) > 1:
        rows.append(("Unassigned", other, "delta"))
    rows.append(("Actual EBIT", lines.loc["EBIT", "actual_ytd"], "total"))
    return pd.DataFrame(rows, columns=["step", "value", "kind"])


def plot_cost_forecast(tables, cost_fc: pd.DataFrame, path: Path) -> Path:
    """Monthly operating costs: last year, this year's budget, actuals and forecast."""
    from .variance import actual_costs
    fy = cost_fc["fiscal_year"].iloc[0]
    months = fiscal_months(fy)
    labels = [pd.Period(m, freq="M").strftime("%b") for m in months]
    c = cost_fc[cost_fc["gl_account"] != "6950"]
    act = c[c["kind"] == "actual"].groupby("month")["amount_eur"].sum()
    fc = c[c["kind"] == "forecast"].groupby("month")["amount_eur"].sum()
    bud = c[c["kind"] == "budget"].groupby("month")["amount_eur"].sum().reindex(months)
    a = actual_costs(tables)
    pyfy = f"{int(fy[:4]) - 1}/{fy[2:4]}"
    py = a[(a["fiscal_year"] == pyfy) & (a["gl_account"] != "6950")].groupby("period")["actual_eur"].sum().sort_index()
    fig, ax = plt.subplots(figsize=(9.5, 4.4))
    x = np.arange(12)
    ax.plot(x, py.values, color=NEUTRAL, linewidth=2, label=f"Actual FY {pyfy}")
    ax.plot(x, bud.values, color=SERIES[2], linewidth=2, linestyle=(0, (4, 3)), label=f"Budget FY {fy}")
    n = len(act)
    ax.plot(x[:n], act.reindex(months[:n]).values, color=SERIES[0], linewidth=2.4, marker="o", markersize=5,
            label=f"Actual FY {fy}")
    fx = np.r_[x[n - 1], x[n:]]
    fy_vals = np.r_[act.reindex(months[:n]).values[-1], fc.reindex(months[n:]).values]
    ax.plot(fx, fy_vals, color=SERIES[0], linewidth=2.4, linestyle=(0, (1.5, 2)), label="Forecast (3+9)")
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(_meur))
    ax.legend(frameon=False, fontsize=8.5, loc="upper center", bbox_to_anchor=(0.5, -0.1), ncol=4,
              labelcolor=TEXT_SECONDARY)
    _style(ax, "Operating costs by month, EUR", "Harvest processing lifts Sep to Nov; the 13th salary lifts November")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def plot_backtest(bt: pd.DataFrame, path: Path) -> Path:
    avg = bt.groupby(["cost_type", "method"])["wape"].mean().unstack()
    order = ["budget", "run_rate", "seasonal", "driver"]
    avg = avg[order]
    fig, ax = plt.subplots(figsize=(8.5, 3.9))
    w = 0.38
    x = np.arange(len(order))
    for i, (ct, color) in enumerate(zip(avg.index, [SERIES[0], SERIES[2]])):
        vals = avg.loc[ct].values * 100
        ax.bar(x + (i - 0.5) * w, vals, width=w - 0.04, color=color, label=ct)
        for xi, v in zip(x + (i - 0.5) * w, vals):
            ax.text(xi, v + 0.15, f"{v:.1f}%", ha="center", fontsize=8, color=TEXT_PRIMARY)
    ax.set_xticks(x)
    ax.set_xticklabels(["Budget", "Run rate", "Prior year seasonal", "Driver based"])
    ax.set_ylabel("Weighted abs. error on remaining months, %", color=TEXT_SECONDARY, fontsize=9)
    ax.legend(frameon=False, fontsize=8.5, labelcolor=TEXT_SECONDARY)
    _style(ax, "Forecast backtest on FY 2025/26 (cut-offs after periods 3, 6 and 9)", "Lower is better")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def plot_capex(cap: pd.DataFrame, path: Path) -> Path:
    cap = cap.iloc[::-1]
    fig, ax = plt.subplots(figsize=(9, 3.8))
    y = np.arange(len(cap))
    actual = cap["actual_to_date_eur"].values
    committed = cap["open_commitments_eur"].values
    rest = np.maximum(cap["eac_eur"].values - actual - committed, 0)
    ax.barh(y, actual, color=SERIES[0], height=0.55, label="Spent", edgecolor=SURFACE, linewidth=2)
    ax.barh(y, committed, left=actual, color=SERIES[3], height=0.55, label="Ordered, not invoiced", edgecolor=SURFACE, linewidth=2)
    ax.barh(y, rest, left=actual + committed, color=GRID, height=0.55, label="Still to order (plan)", edgecolor=SURFACE, linewidth=2)
    for yi, b in zip(y, cap["approved_budget_eur"].values):
        ax.plot([b, b], [yi - 0.38, yi + 0.38], color=TEXT_PRIMARY, linewidth=2)
    for yi, b, eac, pct in zip(y, cap["approved_budget_eur"].values, cap["eac_eur"].values, cap["eac_vs_budget_pct"].values):
        ax.text(max(b, eac) + cap["approved_budget_eur"].max() * 0.02, yi,
                f"EAC {pct:+.0%} vs budget", va="center", fontsize=8, color=UNFAV if pct > 0.10 else TEXT_SECONDARY)
    ax.set_yticks(y)
    ax.set_yticklabels([f"{w}  {d}" for w, d in zip(cap["wbs"], cap["description"])], fontsize=8.5)
    ax.xaxis.set_major_formatter(plt.FuncFormatter(_meur))
    ax.grid(axis="x", color=GRID)
    ax.set_xlim(0, cap["eac_eur"].max() * 1.3)
    ax.legend(frameon=False, fontsize=8, loc="lower right", labelcolor=TEXT_SECONDARY)
    _style(ax, "Capital projects: estimate at completion vs approved budget", "Black tick = approved budget, EUR")
    ax.grid(axis="y", visible=False)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def plot_pvm(pvm: pd.DataFrame, path: Path) -> Path:
    fig, ax = plt.subplots(figsize=(8.5, 3.8))
    x = np.arange(len(pvm))
    w = 0.38
    ax.bar(x - w / 2, pvm["volume_effect_eur"], width=w - 0.04, color=SERIES[0], label="Volume effect")
    ax.bar(x + w / 2, pvm["price_effect_eur"], width=w - 0.04, color=SERIES[3], label="Price effect")
    ax.axhline(0, color=TEXT_SECONDARY, linewidth=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels([c.capitalize() for c in pvm["crop"]])
    ax.yaxis.set_major_formatter(plt.FuncFormatter(_meur))
    ax.legend(frameon=False, fontsize=8.5, labelcolor=TEXT_SECONDARY)
    _style(ax, "Revenue vs budget, July to September, by crop", "EUR; volume at budget price, price at actual volume")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


# ---------------------------------------------------------------------------- Excel pack
HEADER_FILL = PatternFill("solid", fgColor="1F3864")
HEADER_FONT = Font(bold=True, color="FFFFFF")
INPUT_FONT = Font(color="1F4E79")
THIN = Side(style="thin", color="D9D9D9")
NUM = '#,##0;[Red]-#,##0'
PCT = '0.0%;[Red]-0.0%'


def _header(ws, row: int, headers: list[str]) -> None:
    for j, h in enumerate(headers, start=1):
        c = ws.cell(row=row, column=j, value=h)
        c.fill, c.font = HEADER_FILL, HEADER_FONT
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.row_dimensions[row].height = 30


def _widths(ws, widths: dict[str, int]) -> None:
    for col, w in widths.items():
        ws.column_dimensions[col].width = w


def write_excel(path: Path, *, checklist: pd.DataFrame, adjustments: pd.DataFrame, bva_fa: pd.DataFrame,
                comments: pd.DataFrame, pvm: pd.DataFrame, landing: pd.DataFrame, cost_fc: pd.DataFrame,
                capex: pd.DataFrame, ic: pd.DataFrame, choice: pd.DataFrame) -> Path:
    """Controlling pack with live formulas: variances, totals and the full-year outlook are formulas,
    so the file keeps working when a number is overwritten by hand."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Read me"
    info = [
        ("Controlling pack", f"{C.GROUP_NAME}, close {C.CLOSE_PERIOD} (period 3 of FY {fiscal_year(C.CLOSE_PERIOD)})"),
        ("Data", "Synthetic. Generated by the code in this repository; no real company or personal data."),
        ("Sign convention", "Costs positive, revenue positive. Variance = actual - budget; for costs a positive variance is unfavourable."),
        ("Blue numbers", "Inputs from the ledger extract. Black numbers are formulas."),
        ("Thresholds", f"Flag when |variance| > {C.VARIANCE_THRESHOLD_PCT:.0%} and > EUR {C.VARIANCE_THRESHOLD_EUR:,}"),
        ("Sheets", "Close checklist · Adjustments · BvA by function · Variance comments · Revenue PVM · "
                   "Forecast 3+9 · Outlook · Capex · Intercompany"),
    ]
    ws["A1"].font = Font(bold=True, size=14, color="1F3864")
    for i, (k, v) in enumerate(info, start=1):
        ws.cell(row=i, column=1, value=k).font = Font(bold=True, size=14 if i == 1 else 11, color="1F3864")
        ws.cell(row=i, column=2, value=v)
    _widths(ws, {"A": 18, "B": 110})

    # Close checklist ------------------------------------------------------------
    ws = wb.create_sheet("Close checklist")
    cols = ["check_id", "check", "area", "owner", "severity", "status", "exceptions", "amount_eur"]
    _header(ws, 1, ["ID", "Check", "Area", "Owner", "Severity", "Status", "Exceptions", "Amount EUR", "Done (x)"])
    for i, r in enumerate(checklist[cols].itertuples(index=False), start=2):
        for j, v in enumerate(r, start=1):
            c = ws.cell(row=i, column=j, value=v)
            if j == 8:
                c.number_format = NUM
        ws.cell(row=i, column=9, value="x" if r.status == "PASS" else None)
    n = len(checklist) + 1
    ws.cell(row=n + 2, column=1, value="Open items").font = Font(bold=True)
    ws.cell(row=n + 2, column=7, value=f'=COUNTIFS(F2:F{n},"<>PASS",I2:I{n},"<>x")')
    ws.cell(row=n + 3, column=1, value="Close ready?").font = Font(bold=True)
    ws.cell(row=n + 3, column=7, value=f'=IF(G{n + 2}=0,"YES","NO")')
    red = PatternFill("solid", fgColor="F8D7DA")
    amber = PatternFill("solid", fgColor="FFF3CD")
    green = PatternFill("solid", fgColor="D4EDDA")
    ws.conditional_formatting.add(f"F2:F{n}", CellIsRule(operator="equal", formula=['"FAIL"'], fill=red))
    ws.conditional_formatting.add(f"F2:F{n}", CellIsRule(operator="equal", formula=['"WARN"'], fill=amber))
    ws.conditional_formatting.add(f"F2:F{n}", CellIsRule(operator="equal", formula=['"PASS"'], fill=green))
    ws.conditional_formatting.add(f"A2:I{n}", FormulaRule(formula=[f'$I2="x"'], fill=green))
    _widths(ws, {"A": 6, "B": 52, "C": 18, "D": 20, "E": 10, "F": 9, "G": 11, "H": 14, "I": 9})
    ws.freeze_panes = "A2"

    # Adjustments ----------------------------------------------------------------
    ws = wb.create_sheet("Adjustments")
    acols = ["check_id", "company_code", "cost_center", "functional_area", "gl_account", "amount_eur", "description"]
    _header(ws, 1, ["Check", "Company", "Cost center", "Function", "Account", "Amount EUR", "Proposed entry", "Approved (x)"])
    for i, r in enumerate(adjustments[acols].itertuples(index=False), start=2):
        for j, v in enumerate(r, start=1):
            c = ws.cell(row=i, column=j, value=v)
            if j == 6:
                c.number_format, c.font = NUM, INPUT_FONT
    m = len(adjustments) + 1
    ws.cell(row=m + 2, column=5, value="Net P&L effect").font = Font(bold=True)
    ws.cell(row=m + 2, column=6, value=f"=SUM(F2:F{m})").number_format = NUM
    _widths(ws, {"A": 7, "B": 9, "C": 11, "D": 9, "E": 9, "F": 14, "G": 58, "H": 12})

    # BvA by function -------------------------------------------------------------
    ws = wb.create_sheet("BvA by function")
    _header(ws, 1, ["Function", "Actual month", "Budget month", "Var month", "Actual YTD", "Budget YTD", "Var YTD",
                    "Var YTD %", "Prior year YTD", "vs PY %", "Budget FY", "Flag"])
    b = bva_fa[bva_fa["functional_area"] != ""].reset_index(drop=True)
    for i, r in enumerate(b.itertuples(), start=2):
        ws.cell(row=i, column=1, value=C.FUNCTIONAL_AREAS.get(r.functional_area, r.functional_area))
        for col, v in zip("BCEFIK", [r.actual_month, r.budget_month, r.actual_ytd, r.budget_ytd, r.prior_year_ytd, r.budget_full_year]):
            c = ws[f"{col}{i}"]
            c.value, c.number_format, c.font = round(v, 2), NUM, INPUT_FONT
        ws[f"D{i}"] = f"=B{i}-C{i}"
        ws[f"G{i}"] = f"=E{i}-F{i}"
        ws[f"H{i}"] = f"=IF(F{i}=0,\"\",G{i}/F{i})"
        ws[f"J{i}"] = f"=IF(I{i}=0,\"\",E{i}/I{i}-1)"
        ws[f"L{i}"] = (f'=IF(AND(ABS(G{i})>{C.VARIANCE_THRESHOLD_EUR},ABS(H{i})>{C.VARIANCE_THRESHOLD_PCT}),"CHECK","")')
        for col in "DG":
            ws[f"{col}{i}"].number_format = NUM
        for col in "HJ":
            ws[f"{col}{i}"].number_format = PCT
    t = len(b) + 2
    ws.cell(row=t, column=1, value="Total operating costs").font = Font(bold=True)
    for col in "BCDEFGIK":
        c = ws[f"{col}{t}"]
        c.value, c.number_format, c.font = f"=SUM({col}2:{col}{t - 1})", NUM, Font(bold=True)
    ws[f"H{t}"], ws[f"H{t}"].number_format = f"=G{t}/F{t}", PCT
    ws[f"J{t}"], ws[f"J{t}"].number_format = f"=E{t}/I{t}-1", PCT
    ws.conditional_formatting.add(f"G2:G{t}", CellIsRule(operator="greaterThan", formula=["0"], font=Font(color="C00000")))
    _widths(ws, {k: 14 for k in "BCDEFGHIJKL"} | {"A": 28})
    ws.freeze_panes = "B2"

    # Variance comments -------------------------------------------------------------
    ws = wb.create_sheet("Variance comments")
    _header(ws, 1, ["Cost center", "Name", "Account", "Var YTD EUR", "Var YTD %", "Explanation", "Action"])
    for i, r in enumerate(comments.itertuples(), start=2):
        vals = [r.cost_center, r.cost_center_name, r.account, r.var_ytd_eur, r.var_ytd_pct, r.explanation, r.action]
        for j, v in enumerate(vals, start=1):
            c = ws.cell(row=i, column=j, value=v)
            c.alignment = Alignment(wrap_text=True, vertical="top")
        ws.cell(row=i, column=4).number_format = NUM
        ws.cell(row=i, column=5).number_format = PCT
    _widths(ws, {"A": 11, "B": 20, "C": 18, "D": 13, "E": 10, "F": 60, "G": 40})

    # Revenue PVM ---------------------------------------------------------------------
    ws = wb.create_sheet("Revenue PVM")
    _header(ws, 1, ["Crop", "Units actual", "Units budget", "Price actual", "Price budget", "Revenue actual",
                    "Revenue budget", "Volume effect", "Price effect", "Total variance", "Check"])
    for i, r in enumerate(pvm.itertuples(), start=2):
        ws[f"A{i}"] = r.crop
        for col, v in zip("BCFG", [r.units_actual, r.units_budget, r.revenue_eur_actual, r.revenue_eur_budget]):
            c = ws[f"{col}{i}"]
            c.value, c.font, c.number_format = round(v, 2), INPUT_FONT, NUM
        ws[f"D{i}"], ws[f"D{i}"].number_format = f'=IF(B{i}=0,0,F{i}/B{i})', "#,##0.00"
        ws[f"E{i}"], ws[f"E{i}"].number_format = f'=IF(C{i}=0,0,G{i}/C{i})', "#,##0.00"
        ws[f"H{i}"] = f"=(B{i}-C{i})*E{i}"
        ws[f"I{i}"] = f"=(D{i}-E{i})*B{i}"
        ws[f"J{i}"] = f"=F{i}-G{i}"
        ws[f"K{i}"] = f"=ROUND(H{i}+I{i}-J{i},0)"
        for col in "HIJ":
            ws[f"{col}{i}"].number_format = NUM
    t = len(pvm) + 2
    ws[f"A{t}"] = "Total"
    ws[f"A{t}"].font = Font(bold=True)
    for col in "FGHIJ":
        ws[f"{col}{t}"], ws[f"{col}{t}"].number_format = f"=SUM({col}2:{col}{t - 1})", NUM
    ws[f"A{t + 2}"] = "Check column should be 0: volume + price effects add up to the total variance."
    _widths(ws, {k: 14 for k in "BCDEFGHIJK"} | {"A": 12})

    # Forecast 3+9 by function and month ----------------------------------------------
    ws = wb.create_sheet("Forecast 3+9")
    fy = cost_fc["fiscal_year"].iloc[0]
    months = fiscal_months(fy)
    c = cost_fc[cost_fc["gl_account"] != "6950"]
    act_fc = c[c["kind"] != "budget"].groupby(["functional_area", "month"])["amount_eur"].sum().unstack().reindex(columns=months)
    budg = c[c["kind"] == "budget"].groupby(["functional_area", "month"])["amount_eur"].sum().unstack().reindex(columns=months)
    n_act = c[c["kind"] == "actual"]["month"].nunique()
    _header(ws, 1, ["Function", "Row"] + [pd.Period(m, freq="M").strftime("%b %y") + (" A" if k < n_act else " F")
                                          for k, m in enumerate(months)] + ["Full year"])
    row = 2
    first_col, last_col = get_column_letter(3), get_column_letter(14)
    for fa in ["COS", "SEL", "RND", "GNA"]:
        for label, frame in [("Actual / forecast", act_fc), ("Budget", budg)]:
            ws.cell(row=row, column=1, value=C.FUNCTIONAL_AREAS[fa])
            ws.cell(row=row, column=2, value=label)
            for k, m in enumerate(months):
                cell = ws.cell(row=row, column=3 + k, value=round(float(frame.loc[fa, m]), 2))
                cell.number_format = NUM
                cell.font = INPUT_FONT if (label == "Budget" or k < n_act) else Font(color="7F6000", italic=True)
            ws.cell(row=row, column=15, value=f"=SUM({first_col}{row}:{last_col}{row})").number_format = NUM
            row += 1
        ws.cell(row=row, column=2, value="Outlook vs budget")
        for k in range(13):
            col = get_column_letter(3 + k)
            ws[f"{col}{row}"] = f"={col}{row - 2}-{col}{row - 1}"
            ws[f"{col}{row}"].number_format = NUM
            ws[f"{col}{row}"].font = Font(bold=True)
        row += 2
    ws.cell(row=row, column=1, value="Methods chosen by backtest").font = Font(bold=True)
    for r in choice.itertuples():
        row += 1
        ws.cell(row=row, column=1, value=C.FUNCTIONAL_AREAS[r.functional_area])
        ws.cell(row=row, column=2, value=r.cost_type)
        ws.cell(row=row, column=3, value=r.chosen_method)
        ws.cell(row=row, column=4, value=round(r.chosen_wape, 4)).number_format = PCT
        ws.cell(row=row, column=5, value="error; budget method:")
        ws.cell(row=row, column=6, value=round(r.budget_wape, 4)).number_format = PCT
    _widths(ws, {"A": 26, "B": 18} | {get_column_letter(k): 12 for k in range(3, 16)})
    ws.freeze_panes = "C2"

    # Outlook ---------------------------------------------------------------------------
    ws = wb.create_sheet("Outlook")
    _header(ws, 1, ["Line", "Actual YTD", "Forecast rest of year", "Outlook FY", "Budget FY", "Var vs budget",
                    "Var %", "Prior year FY"])
    body = landing[landing["line"] != "EBIT"].reset_index(drop=True)
    for i, r in enumerate(body.itertuples(), start=2):
        ws[f"A{i}"] = r.line
        for col, v in zip("BCEH", [r.actual_ytd, r.forecast_rest, r.budget_fy, r.prior_year_fy]):
            ws[f"{col}{i}"], ws[f"{col}{i}"].number_format, ws[f"{col}{i}"].font = round(v, 0), NUM, INPUT_FONT
        ws[f"D{i}"], ws[f"D{i}"].number_format = f"=B{i}+C{i}", NUM
        ws[f"F{i}"], ws[f"F{i}"].number_format = f"=D{i}-E{i}", NUM
        ws[f"G{i}"], ws[f"G{i}"].number_format = f"=IF(E{i}=0,\"\",F{i}/ABS(E{i}))", PCT
    e = len(body) + 2
    ws[f"A{e}"] = "EBIT"
    ws[f"A{e}"].font = Font(bold=True)
    for col in "BCDEFH":
        ws[f"{col}{e}"] = f"=SUM({col}2:{col}{e - 1})"
        ws[f"{col}{e}"].number_format, ws[f"{col}{e}"].font = NUM, Font(bold=True)
    ws[f"G{e}"], ws[f"G{e}"].number_format = f"=F{e}/ABS(E{e})", PCT
    ws[f"A{e + 1}"] = "EBIT margin"
    for col in "DEH":
        ws[f"{col}{e + 1}"], ws[f"{col}{e + 1}"].number_format = f"={col}{e}/{col}2", PCT
    ws[f"A{e + 3}"] = "Costs are shown negative. Intercompany charges are eliminated. Actuals include the proposed close adjustments."
    _widths(ws, {"A": 30} | {k: 16 for k in "BCDEFGH"})

    # Capex -------------------------------------------------------------------------------
    ws = wb.create_sheet("Capex")
    _header(ws, 1, ["WBS", "Project", "Approved budget", "Spent to date", "Open orders", "EAC", "EAC vs budget",
                    "Plan FY", "Spent FY YTD", "Outlook FY", "Supplement needed"])
    for i, r in enumerate(capex.itertuples(), start=2):
        ws[f"A{i}"], ws[f"B{i}"] = r.wbs, r.description
        for col, v in zip("CDEFHIJ", [r.approved_budget_eur, r.actual_to_date_eur, r.open_commitments_eur, r.eac_eur,
                                      r.plan_fy_eur, r.actual_fy_ytd_eur, r.outlook_fy_eur]):
            ws[f"{col}{i}"], ws[f"{col}{i}"].number_format, ws[f"{col}{i}"].font = round(v, 0), NUM, INPUT_FONT
        ws[f"G{i}"], ws[f"G{i}"].number_format = f"=F{i}/C{i}-1", PCT
        ws[f"K{i}"] = f'=IF((D{i}+E{i})/C{i}>{C.CAPEX_OVERRUN_LIMIT},"YES","")'
    _widths(ws, {"A": 10, "B": 30} | {k: 15 for k in "CDEFGHIJK"})

    # Intercompany -------------------------------------------------------------------------
    ws = wb.create_sheet("Intercompany")
    _header(ws, 1, ["Pair", "DE10 receivable", "Partner payable", "Difference", "Month income DE10", "Month charge partner", "Month difference"])
    for i, r in enumerate(ic.itertuples(index=False), start=2):
        ws[f"A{i}"] = r[0]
        for col, v in zip("BCEF", [r[1], r[2], r[4], r[5]]):
            ws[f"{col}{i}"], ws[f"{col}{i}"].number_format, ws[f"{col}{i}"].font = v, NUM, INPUT_FONT
        ws[f"D{i}"], ws[f"D{i}"].number_format = f"=B{i}-C{i}", NUM
        ws[f"G{i}"], ws[f"G{i}"].number_format = f"=E{i}-F{i}", NUM
    ws.conditional_formatting.add("D2:D10", CellIsRule(operator="notEqual", formula=["0"], fill=red))
    _widths(ws, {"A": 12} | {k: 18 for k in "BCDEFG"})

    for sheet in wb.worksheets:
        sheet.sheet_view.showGridLines = sheet.title == "Read me"
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path


# ---------------------------------------------------------------------------- Power BI export
def export_powerbi(tables, cost_fc: pd.DataFrame, rev_fc: pd.DataFrame, adjustments: pd.DataFrame, folder: Path) -> list[Path]:
    """Star schema as CSV for Power BI: one fact for amounts (actual, adjustment, budget, forecast), dimensions around it."""
    folder.mkdir(parents=True, exist_ok=True)
    from .variance import actual_costs
    act = actual_costs(tables).rename(columns={"actual_eur": "amount_eur"}).assign(scenario="Actual")
    bud = tables["budget"].rename(columns={"budget_eur": "amount_eur"}).assign(scenario="Budget")
    adj = adjustments[["month", "company_code", "cost_center", "functional_area", "gl_account", "amount_eur"]].assign(scenario="Close adjustment")
    fc = cost_fc[cost_fc["kind"] == "forecast"][["month", "company_code", "cost_center", "functional_area", "gl_account", "amount_eur"]].assign(scenario="Forecast")
    cols = ["month", "company_code", "cost_center", "functional_area", "gl_account", "scenario", "amount_eur"]
    fact_cost = pd.concat([act[cols], bud[cols], adj[cols], fc[cols]], ignore_index=True)
    fact_cost["amount_eur"] = fact_cost["amount_eur"].round(2)

    s = tables["sales"].assign(scenario="Actual")
    rb = tables["revenue_budget"].assign(scenario="Budget")
    rf = rev_fc[rev_fc["kind"] == "forecast"].assign(scenario="Forecast")
    rcols = ["month", "company_code", "crop", "scenario", "units", "revenue_eur"]
    fact_rev = pd.concat([s[rcols], rb[rcols], rf[rcols]], ignore_index=True).round({"units": 0, "revenue_eur": 2})

    months = pd.period_range("2024-07", "2027-06", freq="M")
    dim_date = pd.DataFrame({"month": months.strftime("%Y-%m"), "month_start": months.start_time.date,
                             "fiscal_year": [fiscal_year(m) for m in months.strftime("%Y-%m")],
                             "fiscal_period": [(p.month - 7) % 12 + 1 for p in months],
                             "month_name": months.strftime("%b")})
    dim_fa = pd.DataFrame([{"functional_area": k, "functional_area_name": v, "sort": i}
                           for i, (k, v) in enumerate(C.FUNCTIONAL_AREAS.items())])
    out = {
        "fact_cost.csv": fact_cost, "fact_revenue.csv": fact_rev, "dim_date.csv": dim_date,
        "dim_cost_center.csv": tables["cost_centers"], "dim_account.csv": tables["gl_accounts"],
        "dim_entity.csv": tables["entities"], "dim_functional_area.csv": dim_fa,
    }
    paths = []
    for name, df in out.items():
        p = folder / name
        df.to_csv(p, index=False)
        paths.append(p)
    return paths


# ---------------------------------------------------------------------------- close memo
def _md(df: pd.DataFrame) -> str:
    return df.to_markdown(index=False)


def close_memo(path: Path, *, checklist, adjustments, comments, pvm, is_ytd, landing, choice, capex) -> Path:
    fails = checklist[checklist["status"] != "PASS"]
    eb = landing.set_index("line")
    lines = [
        f"# Close memo: {C.CLOSE_PERIOD} (period 3, FY {fiscal_year(C.CLOSE_PERIOD)})",
        "",
        f"{C.GROUP_NAME}. All data is synthetic. Amounts in EUR.",
        "",
        "## Close status",
        "",
        f"{len(checklist)} checks ran; {len(fails)} need action before sign-off. The proposed corrections change P&L by "
        f"EUR {adjustments['amount_eur'].sum():,.0f}.",
        "",
        _md(checklist[["check_id", "check", "status", "exceptions", "amount_eur"]]),
        "",
        "## Proposed adjustments",
        "",
        _md(adjustments[["check_id", "company_code", "cost_center", "gl_account", "amount_eur", "description"]]),
        "",
        "## Year to date vs budget (before adjustments)",
        "",
        _md(is_ytd),
        "",
        "Revenue by crop, volume and price effects:",
        "",
        _md(pvm[["crop", "units_vs_budget_pct", "price_vs_budget_pct", "volume_effect_eur", "price_effect_eur", "total_variance_eur"]].round(3)),
        "",
        "## Variance comments",
        "",
        _md(comments[["cost_center", "cost_center_name", "account", "var_ytd_eur", "explanation", "action"]]),
        "",
        "## Full-year outlook (3+9, after adjustments)",
        "",
        _md(landing),
        "",
        f"EBIT outlook EUR {eb.loc['EBIT', 'outlook_fy']:,.0f} against a budget of EUR {eb.loc['EBIT', 'budget_fy']:,.0f}.",
        "",
        "Forecast methods, chosen by a backtest on FY 2025/26:",
        "",
        _md(choice.round(4)),
        "",
        "## Capital projects",
        "",
        _md(capex[["wbs", "description", "approved_budget_eur", "actual_to_date_eur", "open_commitments_eur", "eac_eur", "eac_vs_budget_pct"]]),
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
