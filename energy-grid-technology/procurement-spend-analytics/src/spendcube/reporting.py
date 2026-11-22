"""Figures, the Excel spend cube workbook and the German management deck."""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from .config import CATEGORIES, FIGURES, OUTPUTS  # noqa: E402

BLUE, ORANGE, GREEN, YELLOW, PURPLE, GREY = "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#8a5cd1", "#9a9893"
INK, MUTED, GRID, SURFACE = "#1d1d1b", "#5f5e5a", "#e4e3df", "#fcfcfb"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": GRID, "axes.labelcolor": MUTED, "xtick.color": MUTED,
                     "ytick.color": MUTED, "axes.spines.top": False, "axes.spines.right": False, "figure.facecolor": SURFACE,
                     "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE, "axes.titleweight": "bold", "axes.titlesize": 13,
                     "axes.titlelocation": "left"})


def _title(ax, title, sub):
    ax.set_title(title, color=INK, pad=26)
    ax.text(0, 1.02, sub, transform=ax.transAxes, color=MUTED, fontsize=9.5)


def eur_m(x):
    return f"€{x / 1e6:,.1f}m"


def figures(ctx):
    FIGURES.mkdir(parents=True, exist_ok=True)
    con = ctx["con"]

    # 1. spend by category, split by contract status
    from .analytics import q
    s = q(con, """SELECT c.category_name, f.contract_status, SUM(f.spend_eur) s FROM fact_po_line f JOIN dim_category c USING(category)
                  WHERE f.is_return=0 GROUP BY 1,2""").pivot(index="category_name", columns="contract_status", values="s").fillna(0)
    s = s.loc[s.sum(axis=1).sort_values().index]
    fig, ax = plt.subplots(figsize=(9, 5.2))
    left = np.zeros(len(s))
    for col, color, lab in [("active", BLUE, "Under an active framework agreement"), ("expired", YELLOW, "Supplier's agreement has expired"),
                            ("none", ORANGE, "No agreement with this supplier")]:
        v = s.get(col, pd.Series(0, index=s.index)).to_numpy() / 1e6
        ax.barh(s.index, v, left=left, color=color, label=lab, height=0.62, edgecolor=SURFACE, linewidth=1.5)
        left += v
    for i, tot in enumerate(left):
        ax.text(tot + 1.5, i, f"€{tot:,.0f}m", va="center", color=INK, fontsize=9)
    ax.set_xlabel("Spend, Nov 2024 to Oct 2026 (EUR million)")
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.legend(frameon=False, loc="lower right", fontsize=9)
    h = ctx["head"]
    _title(ax, "Where the money goes", f"€{h['spend_eur'] / 1e6:,.0f}m over two years; {h['maverick_share']:.0%} is bought outside an active agreement")
    fig.tight_layout()
    fig.savefig(FIGURES / "spend_by_category.png", dpi=150)
    plt.close(fig)

    # 2. pareto
    p = ctx["pareto"]
    fig, ax = plt.subplots(figsize=(8, 4.6))
    ax.plot(p["rank"], p.cumulative_share * 100, color=BLUE, linewidth=2)
    n80 = h["suppliers_for_80pct"]
    ax.axhline(80, color=GREY, linewidth=1, linestyle="--")
    ax.scatter([n80], [p.cumulative_share.iloc[n80 - 1] * 100], color=BLUE, s=60, zorder=3, edgecolor=SURFACE, linewidth=2)
    ax.annotate(f"{n80} suppliers carry 80% of spend", (n80, p.cumulative_share.iloc[n80 - 1] * 100), xytext=(n80 + 8, 62), color=INK,
                arrowprops=dict(arrowstyle="-", color=MUTED))
    ax.annotate(f"{h['tail_suppliers']} suppliers share the last 5%", (len(p) - 20, 97), xytext=(len(p) - 62, 86), color=INK,
                arrowprops=dict(arrowstyle="-", color=MUTED))
    ax.set_xlabel("Suppliers ranked by spend")
    ax.set_ylabel("Cumulative share of spend (%)")
    ax.set_ylim(0, 102)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    _title(ax, "A few suppliers, a long tail", f"{h['suppliers']} suppliers with orders, counted after merging duplicate records")
    fig.tight_layout()
    fig.savefig(FIGURES / "supplier_pareto.png", dpi=150)
    plt.close(fig)

    # 3. kraljic
    kr = ctx["kr"]
    colors = {"Strategic": PURPLE, "Leverage": BLUE, "Bottleneck": ORANGE, "Non-critical": GREY}
    fig, ax = plt.subplots(figsize=(8.4, 6))
    ax.axvline(0.40, color=GRID, linewidth=1.2)
    ax.axhline(8, color=GRID, linewidth=1.2)
    for _, r in kr.iterrows():
        ax.scatter(r.supply_risk, r.share_pct, s=80 + r.spend_eur / 4e5, color=colors[r.quadrant], alpha=0.85, edgecolor=SURFACE, linewidth=2)
        ax.annotate(r.category_name, (r.supply_risk, r.share_pct), xytext=(8, 6), textcoords="offset points", fontsize=8.5, color=INK)
    for txt, x, y in [("Leverage", 0.03, 44), ("Strategic", 0.75, 44), ("Non-critical", 0.03, 6.0), ("Bottleneck", 0.75, 1.0)]:
        ax.text(x, y, txt, color=colors[txt], fontsize=11, fontweight="bold")
    ax.set_xlim(0, 0.9)
    ax.set_ylim(-1, 47)
    ax.set_xlabel("Supply risk (few suppliers, concentration, country risk, price volatility)")
    ax.set_ylabel("Profit impact: share of spend (%)")
    _title(ax, "Kraljic matrix by category", "Bubble size = spend. Thresholds: 8% of spend, supply risk 0.40")
    fig.tight_layout()
    fig.savefig(FIGURES / "kraljic.png", dpi=150)
    plt.close(fig)

    # 4. commodity forecasts, small multiples
    ind, fc = ctx["ind"], ctx["fc"]
    names = {"copper": "Copper", "goes": "Electrical steel (GOES)", "steel_hrc": "Hot-rolled steel", "aluminium": "Aluminium", "oil": "Transformer oil"}
    fig, axes = plt.subplots(1, 5, figsize=(15, 3.8))
    for ax, (k, lab) in zip(axes, names.items()):
        hist = ind[ind.month >= ind.month.max() - pd.DateOffset(months=30)]
        f = fc[fc["index"] == k]
        ax.plot(hist.month, hist[k], color=BLUE, linewidth=1.8)
        ax.fill_between(f.month, f.lo, f.hi, color=BLUE, alpha=0.15, linewidth=0)
        ax.plot(f.month, f.forecast, color=BLUE, linewidth=1.8, linestyle="--")
        ax.set_title(lab, fontsize=10.5, loc="left")
        ax.tick_params(axis="x", labelrotation=45, labelsize=8)
        ax.tick_params(axis="y", labelsize=8)
        ax.grid(axis="y", color=GRID, linewidth=0.8)
    axes[0].set_ylabel("EUR per tonne")
    fig.suptitle("Commodity indices: last 30 months and six-month outlook with 80% band", x=0.01, ha="left", fontweight="bold", color=INK)
    fig.text(0.01, 0.9, "No model beat 'next month = this month' in the backtest, so the outlook is flat and the band carries the information",
             color=MUTED, fontsize=9.5)
    fig.tight_layout(rect=(0, 0, 1, 0.88))
    fig.savefig(FIGURES / "commodity_forecast.png", dpi=150)
    plt.close(fig)

    # 5. data quality findings
    dq = ctx["dq"].copy()
    dq = dq[dq.failing > 0].sort_values("failing")
    sev = {"high": ORANGE, "medium": YELLOW, "low": GREY}
    fig, ax = plt.subplots(figsize=(9, 5))
    short = lambda t: t if len(t) <= 50 else t[:t.rfind(" ", 0, 48)] + " …"
    ax.barh([f"{r.id}  {short(r.rule)}" for r in dq.itertuples()], dq.failing, color=[sev[s] for s in dq.severity], height=0.6)
    for i, r in enumerate(dq.itertuples()):
        ax.text(r.failing * 1.05 + 1, i, f"{r.failing:,}", va="center", fontsize=9, color=INK)
    ax.set_xscale("log")
    ax.set_xlabel("Failing rows or records (log scale)")
    from matplotlib.patches import Patch
    ax.legend(handles=[Patch(color=c, label=f"{k} severity") for k, c in sev.items()], frameon=False, loc="lower right", fontsize=9)
    f = ctx["found"]
    _title(ax, "What the data quality rules found", f"{int(f.found.sum()):,} of {int(f.planted.sum()):,} planted problems detected; each rule has an owner role")
    fig.tight_layout()
    fig.savefig(FIGURES / "dq_findings.png", dpi=150)
    plt.close(fig)


def excel(ctx):
    """Workbook for buyers: summary with live formulas, spend cube table to pivot, scorecards, DQ register and forecasts."""
    path = OUTPUTS / "procurement_spend_cube.xlsx"
    con = ctx["con"]
    from .analytics import q
    cube = q(con, """SELECT f.month, p.plant_name AS plant, c.category_name AS category, d.supplier_name AS supplier, d.country,
                            f.contract_status, ROUND(SUM(f.spend_eur),2) AS spend_eur, COUNT(*) AS lines
                     FROM fact_po_line f JOIN dim_supplier d USING(supplier_id) JOIN dim_category c USING(category) JOIN dim_plant p USING(plant)
                     WHERE f.is_return=0 GROUP BY 1,2,3,4,5,6""")
    with pd.ExcelWriter(path, engine="xlsxwriter") as xw:
        wb = xw.book
        money = wb.add_format({"num_format": "#,##0 €"})
        pct = wb.add_format({"num_format": "0.0%"})
        bold = wb.add_format({"bold": True, "font_size": 14})
        ws = wb.add_worksheet("Summary")
        ws.write("A1", "Havelwerk Grid Components (fictional): procurement spend cube", bold)
        ws.write("A2", "Synthetic data. Spend Nov 2024 to Oct 2026, EUR, returns excluded.")
        cube.to_excel(xw, sheet_name="Spend cube", index=False)
        sc = xw.sheets["Spend cube"]
        n = len(cube)
        sc.add_table(0, 0, n, len(cube.columns) - 1, {"name": "SpendCube", "columns": [{"header": c} for c in cube.columns], "style": "Table Style Light 9"})
        sc.set_column("A:A", 11)
        sc.set_column("B:F", 22)
        sc.set_column("G:G", 14, money)
        G, F_, C_ = f"'Spend cube'!$G$2:$G${n + 1}", f"'Spend cube'!$F$2:$F${n + 1}", f"'Spend cube'!$C$2:$C${n + 1}"
        total = cube.spend_eur.sum()
        by_status = cube.groupby("contract_status").spend_eur.sum()
        rows = [("Total spend", f"=SUM({G})", money, total)]
        for lab, st in [("Under an active agreement", "active"), ("Supplier's agreement expired", "expired"), ("No agreement", "none")]:
            rows.append((lab, f'=SUMIFS({G},{F_},"{st}")/$B$4', pct, by_status.get(st, 0) / total))
        for i, (lab, f, fmt, val) in enumerate(rows):
            ws.write(3 + i, 0, lab)
            ws.write_formula(3 + i, 1, f, fmt, val)
        ws.write(9, 0, "Spend by category", wb.add_format({"bold": True}))
        by_cat = cube.groupby("category").spend_eur.sum()
        for i, (code, c) in enumerate(CATEGORIES.items()):
            ws.write(10 + i, 0, c["name"])
            ws.write_formula(10 + i, 1, f"=SUMIFS({G},{C_},A{11 + i})", money, by_cat.get(c["name"], 0))
            ws.write_formula(10 + i, 2, f"=B{11 + i}/$B$4", pct, by_cat.get(c["name"], 0) / total)
        ws.set_column("A:A", 34)
        ws.set_column("B:B", 16)
        chart = wb.add_chart({"type": "bar"})
        chart.add_series({"name": "Spend", "categories": ["Summary", 10, 0, 18, 0], "values": ["Summary", 10, 1, 18, 1], "fill": {"color": BLUE}})
        chart.set_legend({"none": True})
        chart.set_title({"name": "Spend by category"})
        ws.insert_chart("E4", chart, {"x_scale": 1.3, "y_scale": 1.2})
        for name, df in [("Supplier scorecard", ctx["score"]), ("Kraljic", ctx["kr"]), ("DQ rules", ctx["dq"]), ("DQ planted vs found", ctx["found"]),
                         ("Supplier review queue", ctx["review"]), ("Forecast backtest", ctx["fsum"].reset_index()),
                         ("Commodity outlook", ctx["fc"]), ("Index pass-through", ctx["pt"]), ("Budget impact 6m", ctx["impact"])]:
            df.to_excel(xw, sheet_name=name[:31], index=False)
            xw.sheets[name[:31]].set_column(0, len(df.columns), 16)
    return path


def deck(ctx):
    """Management presentation in German (Einkauf, Geschäftsführung)."""
    from pptx import Presentation
    from pptx.dml.color import RGBColor
    from pptx.util import Emu, Inches, Pt

    h, res, f = ctx["head"], ctx["result"], ctx["found"]
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
    blank = prs.slide_layouts[6]
    navy, ink, muted = RGBColor(0x10, 0x1E, 0x3A), RGBColor(0x1D, 0x1D, 0x1B), RGBColor(0x5F, 0x5E, 0x5A)

    def text(slide, x, y, w, hgt, s, size=16, bold=False, color=ink):
        tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(hgt))
        tf = tb.text_frame
        tf.word_wrap = True
        for i, line in enumerate(s if isinstance(s, list) else [s]):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.text = line
            p.font.size, p.font.bold, p.font.color.rgb = Pt(size), bold, color
            p.space_after = Pt(8)
        return tb

    def slide(title, message, bullets=None, image=None, img_w=7.6):
        sl = prs.slides.add_slide(blank)
        text(sl, 0.6, 0.35, 12, 0.6, title, 26, True, navy)
        text(sl, 0.6, 1.0, 12, 0.6, message, 15, False, muted)
        if image:
            sl.shapes.add_picture(str(FIGURES / image), Inches(0.6), Inches(1.75), width=Inches(img_w))
        if bullets:
            text(sl, 0.6 + (img_w + 0.3 if image else 0), 1.9, 12.1 - (img_w + 0.3 if image else 0), 5, [f"• {b}" for b in bullets], 14)
        text(sl, 0.6, 7.0, 12, 0.3, "Fiktives Unternehmen, synthetische Daten · github.com/mohammedelsayed741996-blip/berlin-data-portfolio", 9, False, muted)
        return sl

    sl = prs.slides.add_slide(blank)
    bg = sl.shapes.add_shape(1, 0, 0, prs.slide_width, prs.slide_height)
    bg.fill.solid()
    bg.fill.fore_color.rgb = navy
    bg.line.fill.background()
    text(sl, 0.8, 2.3, 11.5, 1.2, "Einkaufsdaten: Qualität, Spend Cube und Rohstoffpreise", 36, True, RGBColor(255, 255, 255))
    text(sl, 0.8, 3.6, 11.5, 1.0, "Havelwerk Grid Components (fiktiv) · Werke Berlin, Erfurt, Danzig · Nov 2024 bis Okt 2026", 18, False, RGBColor(0xC8, 0xCD, 0xD7))
    text(sl, 0.8, 6.6, 11.5, 0.5, "Alle Daten synthetisch erzeugt. Keine echten Lieferanten, Personen oder Preise.", 12, False, RGBColor(0xC8, 0xCD, 0xD7))

    dqr = res["data_quality"]
    slide("Datenqualität: erst prüfen, dann berichten",
          f"12 Regeln über 8 Quellen aus zwei ERP-Systemen; alle {int(f.planted.sum())} absichtlich eingebauten Fehler wurden gefunden"
          if dqr["all_planted_found"] else f"12 Regeln über 8 Quellen; {int(f.found.sum())} von {int(f.planted.sum())} eingebauten Fehlern gefunden",
          [f"{dqr['cleaning']['duplicate_lines_removed']} doppelte Bestellpositionen aus überlappenden ERP_A-Exporten entfernt",
           f"{dqr['cleaning']['prices_corrected_per_tonne']} Kupferpositionen mit Preis pro Tonne auf einer kg-Position korrigiert",
           f"{len(ctx['merges'])} Lieferantendubletten zusammengeführt, {len(ctx['review'])} Grenzfälle zur manuellen Prüfung",
           "Jede Regel hat eine verantwortliche Rolle und eine konkrete Maßnahme (config/dq_rules.yaml)"],
          "dq_findings.png", 7.4)
    slide("Spend: 80 % bei wenigen Lieferanten",
          f"{h['spend_eur'] / 1e6:,.0f} Mio. € in zwei Jahren; {h['suppliers_for_80pct']} Lieferanten tragen 80 %, {h['tail_suppliers']} teilen sich die letzten 5 %",
          [f"{h['on_contract_share']:.0%} des Volumens laufen über einen aktiven Rahmenvertrag",
           f"{h['maverick_expired_contract_eur'] / 1e6:,.0f} Mio. € bei Lieferanten, deren Vertrag Ende 2025 ausgelaufen ist: schnellster Hebel",
           f"{h['maverick_no_contract_eur'] / 1e6:,.0f} Mio. € bei Lieferanten ohne Vertrag in Warengruppen, für die es Verträge gibt",
           f"Termintreue über alle Wareneingänge: {h['on_time_rate']:.0%}"],
          "spend_by_category.png", 7.4)
    top = ctx["score"].iloc[0]
    slide("Lieferanten: Kupfer, Elektroband, Isolation und Stahl sind strategisch",
          "Kraljic-Matrix nach Ausgabenanteil und Versorgungsrisiko; Lieferantenbewertung aus Termintreue, Qualität und Länderrisiko",
          [f"Größter Lieferant ({top.supplier_name}, {top.spend_eur / 1e6:,.0f} Mio. €) erreicht nur Note {top.grade}: Termintreue {top.on_time_rate:.0%}",
           "Elektroband: ein Lieferant mit fast dem gesamten Volumen, Zweitquelle prüfen",
           "Aluminium und Transformatoröl: kleines Volumen, aber hohes Risiko (Engpass)",
           "Elektronik: viele Anbieter, geringes Risiko, Bündelung für bessere Preise"],
          "kraljic.png", 6.8)
    fr = res["forecast"]
    slide("Rohstoffpreise: Bandbreiten statt Scheingenauigkeit",
          f"Kein Modell war im Backtest besser als 'nächster Monat = dieser Monat'; die 80-%-Bänder trafen in {fr['band_coverage_80pct']:.0%} der Fälle",
          None, "commodity_forecast.png", 12.1)
    imp = ctx["impact"].set_index("category")
    pt = ctx["pt"].set_index("category")
    de = {"CU": "Kupferleiter und Wicklungen", "ES": "Elektroband (kornorientiert)", "ST": "Kessel- und Baustahl", "AL": "Aluminiumteile",
          "OI": "Transformatoröl"}

    def eur(x):
        return (f"{x / 1e6:+.1f}".replace(".", ",") + " Mio. €") if abs(x) >= 1e6 else (f"{x / 1e3:+,.0f}".replace(",", ".") + " Tsd. €")

    bl = []
    for cat in ["CU", "ES", "ST", "AL", "OI"]:
        if cat in imp.index:
            r = imp.loc[cat]
            lag = int(pt.loc[cat].lag_months)
            bl.append(f"{de[cat]}: {pt.loc[cat].pass_through:.0%} des Preises folgen dem Index mit {lag} {'Monat' if lag == 1 else 'Monaten'} Verzug; "
                      f"Effekt in 6 Monaten {eur(r.impact_eur_6m_expected)} (80-%-Band {eur(r.impact_eur_6m_low)} bis {eur(r.impact_eur_6m_high)})")
    slide("Was die Indizes für unser Budget bedeuten", "Preisweitergabe aus den eigenen Bestelldaten geschätzt, Volumen wie in den letzten 12 Monaten; negativ = Einsparung", bl)
    slide("Empfehlungen und nächste Schritte", "Was ich in den ersten Wochen mit dem Team angehen würde",
          ["Ausgelaufene Rahmenverträge verlängern oder neu ausschreiben, beginnend mit Stahl und Kupfer",
           "Pflichtfeld Warengruppe in ERP_B und ein gemeinsamer Zahlungsbedingungskatalog für beide Systeme",
           "Prüfliste der Lieferantendubletten mit dem Stammdatenteam abarbeiten, danach Golden Record produktiv nutzen",
           "Gespräch mit dem größten Kupferlieferanten zu Termintreue; Zweitquelle für Elektroband qualifizieren",
           "Budgetplanung 2027 mit Indexbändern statt Punktprognosen; Datenqualitätsregeln monatlich als Power-BI-Seite",
           "Stammdatenänderungen über eine Power-App mit Genehmigung per Power Automate (Entwurf in docs/power_platform_flow.md)"])
    path = OUTPUTS / "management_summary_de.pptx"
    prs.save(path)
    return path
