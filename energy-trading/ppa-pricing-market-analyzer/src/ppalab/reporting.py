"""Figures, the Excel PPA offer calculator and the automated weekly market report (German)."""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from .config import AS_OF, BALANCING_EUR_MWH, FIGURES, OUTPUTS  # noqa: E402
from .crm import STAGES  # noqa: E402
from .pricing import LGD, RATING_PD  # noqa: E402

BLUE, ORANGE, GREEN, YELLOW, PURPLE, GREY = "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#8a5cd1", "#9a9893"
INK, MUTED, GRID, SURFACE = "#1d1d1b", "#5f5e5a", "#e4e3df", "#fcfcfb"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": GRID, "axes.labelcolor": MUTED, "xtick.color": MUTED,
                     "ytick.color": MUTED, "axes.spines.top": False, "axes.spines.right": False, "figure.facecolor": SURFACE,
                     "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE, "axes.titleweight": "bold", "axes.titlesize": 12,
                     "axes.titlelocation": "left"})


def _save(fig, name):
    fig.savefig(FIGURES / name, dpi=150)
    plt.close(fig)


def figures(ctx):
    FIGURES.mkdir(parents=True, exist_ok=True)
    y, m = ctx["yearly"], ctx["monthly"]
    full = y[y.hours > 8000]

    # 1. market trends as three small panels
    fig, ax = plt.subplots(1, 3, figsize=(15, 4.3))
    ax[0].plot(m.month, m.base, color=BLUE, linewidth=1.8)
    ax[0].set_title("Monthly baseload price (EUR/MWh)")
    ax[0].grid(axis="y", color=GRID)
    ax[1].bar(y.year.astype(str), y.negative_hours, color=ORANGE, width=0.6)
    for i, v in enumerate(y.negative_hours):
        ax[1].text(i, v + 8, f"{v}", ha="center", fontsize=8.5, color=INK)
    ax[1].set_title("Hours with negative prices")
    if (y.hours < 8000).any():
        ax[1].text(len(y) - 1, y.negative_hours.iloc[-1] / 2, "Jan-Oct", ha="center", color=SURFACE, fontsize=8, rotation=90)
    ax[2].plot(y.year, y.solar_capture_rate * 100, color=YELLOW, linewidth=2, marker="o", markersize=5, label="Solar")
    ax[2].plot(y.year, y.wind_capture_rate * 100, color=BLUE, linewidth=2, marker="o", markersize=5, label="Wind")
    ax[2].text(y.year.iloc[-1] + 0.1, y.solar_capture_rate.iloc[-1] * 100, " Solar", color=INK, va="center", fontsize=9)
    ax[2].text(y.year.iloc[-1] + 0.1, y.wind_capture_rate.iloc[-1] * 100, " Wind", color=INK, va="center", fontsize=9)
    ax[2].set_title("Capture rate: earned price / baseload (%)")
    ax[2].grid(axis="y", color=GRID)
    ax[2].set_xlim(y.year.min() - 0.3, y.year.max() + 0.9)
    fig.suptitle("German-style power market, synthetic: crisis, then cheaper solar hours", x=0.01, ha="left", fontweight="bold", color=INK)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    _save(fig, "market_trends.png")

    # 2. hour x month heatmap of relative prices, last 12 months (diverging around 1.0)
    from .trends import hour_month_profile
    t = hour_month_profile(ctx["h"])
    fig, ax = plt.subplots(figsize=(10, 4.6))
    from matplotlib.colors import TwoSlopeNorm
    im = ax.imshow(t.to_numpy(), aspect="auto", cmap="RdBu_r", norm=TwoSlopeNorm(vmin=min(t.min().min(), 0.2), vcenter=1.0, vmax=max(t.max().max(), 1.8)))
    ax.set_yticks(range(12), ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])
    ax.set_xticks(range(0, 24, 2), [f"{h}:00" for h in range(0, 24, 2)])
    cb = fig.colorbar(im, ax=ax, shrink=0.85)
    cb.set_label("Price relative to the 12-month average")
    ax.set_title("Price by month and hour, last 12 months", pad=22)
    ax.text(0, 1.02, "Blue = cheaper than average. Spring and summer middays are where solar plants sell", transform=ax.transAxes, color=MUTED, fontsize=9)
    fig.tight_layout()
    _save(fig, "price_heatmap.png")

    # 3. offer waterfall, solar pay-as-produced
    o = ctx["offers"]["solar"]
    steps = [("Forward base\n2027-29", o["forward_base"]), ("Solar shape", o["shape"]), ("No output in\nnegative hours", o["curtailment_uplift"]),
             ("Balancing", o["balancing"]), ("Hedging", o["hedging"]), ("Profile risk", o["profile_risk"]), ("Volume risk", o["volume_risk"]),
             ("Credit (BBB)", o["credit"]), ("Margin", o["margin"])]
    fig, ax = plt.subplots(figsize=(11, 4.8))
    level = 0.0
    for i, (lab, v) in enumerate(steps):
        if i == 0:
            ax.bar(i, v, color=BLUE, width=0.62)
            level = v
            ax.text(i, v + 1, f"{v:.1f}", ha="center", fontsize=9, color=INK)
            continue
        bottom = level if v >= 0 else level + v
        ax.bar(i, abs(v), bottom=bottom, color=GREEN if v >= 0 else ORANGE, width=0.62)
        ax.text(i, max(level, level + v) + 1, f"{v:+.1f}", ha="center", fontsize=9, color=INK)
        level += v
    ax.bar(len(steps), o["offer_price"], color=PURPLE, width=0.62)
    ax.text(len(steps), o["offer_price"] + 1, f"{o['offer_price']:.1f}", ha="center", fontsize=9, color=INK, fontweight="bold")
    ax.set_xticks(range(len(steps) + 1), [s[0] for s in steps] + ["Offer price"], fontsize=8.5)
    ax.set_ylabel("EUR per MWh")
    ax.grid(axis="y", color=GRID)
    ax.set_axisbelow(True)
    ax.set_title("Pay-as-produced solar PPA, 10 MW, 2027-2029: from forward price to offer", pad=22)
    ax.text(0, 1.02, f"Expected capture price {o['expected_capture']:.1f} EUR/MWh; {o['curtailed_share']:.0%} of potential output falls in negative hours",
            transform=ax.transAxes, color=MUTED, fontsize=9)
    fig.tight_layout()
    _save(fig, "offer_waterfall.png")

    # 4. structures: range P90-P10 with expected
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.2), sharex=True)
    names = {"merchant": "Merchant (no PPA)", "pay_as_produced": "Pay-as-produced PPA", "baseload": "Baseload PPA", "swap": "Financial swap"}
    for ax, tech in zip(axes, ["solar", "wind"]):
        r = ctx["struct"][tech]
        for i, k in enumerate(names):
            lo, hi, mu = r[k].quantile(0.1), r[k].quantile(0.9), r[k].mean()
            ax.plot([lo, hi], [i, i], color=BLUE, linewidth=6, solid_capstyle="round", alpha=0.35)
            ax.scatter([mu], [i], color=BLUE, s=60, zorder=3, edgecolor=SURFACE, linewidth=2)
            ax.text(hi + 1, i, f"{mu:.1f}", va="center", fontsize=9, color=INK)
        ax.set_yticks(range(4), list(names.values()) if tech == "solar" else [""] * 4)
        ax.invert_yaxis()
        ax.set_title(f"{tech.capitalize()} plant", fontsize=11)
        ax.grid(axis="x", color=GRID)
        ax.set_xlabel("Producer's realised price, EUR per MWh produced")
    fig.suptitle("What the producer earns under each structure: expected (dot) and P90-P10 range (bar)", x=0.01, ha="left", fontweight="bold", color=INK)
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    _save(fig, "structures.png")

    # 5. BESS
    b = ctx["bess"]
    fig, ax = plt.subplots(figsize=(9, 4.2))
    x = np.arange(len(b))
    ax.bar(x - 0.2, b.revenue_eur_per_mw_year / 1e3, width=0.38, color=GREY, label="Perfect foresight")
    ax.bar(x + 0.2, b.realistic_eur_per_mw_year / 1e3, width=0.38, color=GREEN, label="75% captured by a real optimiser")
    ax.set_xticks(x, b.year.astype(str))
    ax.set_ylabel("EUR thousand per MW per year")
    ax.legend(frameon=False)
    ax.grid(axis="y", color=GRID)
    ax.set_axisbelow(True)
    ax.set_title("Day-ahead arbitrage value of a 1 MW / 2 MWh battery", pad=22)
    ax.text(0, 1.02, "Dynamic programme per day, 88% round trip, EUR 4/MWh degradation. 2026 annualised from Jan-Oct",
            transform=ax.transAxes, color=MUTED, fontsize=9)
    fig.tight_layout()
    _save(fig, "bess_value.png")

    # 6. pipeline
    pl = ctx["crm"]["pipeline"] / 1e6
    fig, ax = plt.subplots(figsize=(9, 4.2))
    left = np.zeros(len(pl))
    for col, c in zip(pl.columns, [PURPLE, GREY, YELLOW, BLUE]):
        ax.barh(pl.index, pl[col], left=left, color=c, label=col, height=0.6, edgecolor=SURFACE, linewidth=1.5)
        left += pl[col].to_numpy()
    ax.invert_yaxis()
    ax.set_xlabel("Probability-weighted margin over the contract tenor (EUR million)")
    ax.legend(frameon=False, ncols=4, loc="upper center", bbox_to_anchor=(0.5, -0.16), fontsize=8.5)
    ax.grid(axis="x", color=GRID)
    ax.set_axisbelow(True)
    ax.set_title("Open origination pipeline by stage and product", pad=22)
    ax.text(0, 1.02, "Synthetic Salesforce opportunity export; stage probabilities from the sales process, not typed values",
            transform=ax.transAxes, color=MUTED, fontsize=9)
    fig.tight_layout()
    _save(fig, "pipeline.png")


def excel(ctx):
    """PPA offer calculator with live formulas, plus the supporting tables."""
    path = OUTPUTS / "ppa_offer_calculator.xlsx"
    o_s, o_w = ctx["offers"]["solar"], ctx["offers"]["wind"]
    with pd.ExcelWriter(path, engine="xlsxwriter") as xw:
        wb = xw.book
        bold = wb.add_format({"bold": True, "font_size": 14})
        hdr = wb.add_format({"bold": True, "bg_color": "#e9eef7"})
        inp = wb.add_format({"bg_color": "#fff4d6", "border": 1, "num_format": "0.00"})
        eur = wb.add_format({"num_format": "0.00 \"€/MWh\""})
        eurb = wb.add_format({"num_format": "0.00 \"€/MWh\"", "bold": True, "bg_color": "#e3f5ec"})
        money = wb.add_format({"num_format": "#,##0 \"€\""})
        pct = wb.add_format({"num_format": "0.0%"})

        # lookup tables first so formulas can reference them
        curve = ctx["curve"]
        curve.to_excel(xw, sheet_name="Forward curve", index=False)
        lk = pd.DataFrame({"technology": ["solar", "wind"], "capture_rate_paid": [o_s["capture_rate"], o_w["capture_rate"]],
                           "curtailed_share": [o_s["curtailed_share"], o_w["curtailed_share"]],
                           "balancing": [BALANCING_EUR_MWH["solar"], BALANCING_EUR_MWH["wind"]],
                           "profile_risk": [-o_s["profile_risk"], -o_w["profile_risk"]], "volume_risk": [-o_s["volume_risk"], -o_w["volume_risk"]],
                           "full_load_hours": [ctx["stats"]["solar"].paid_mwh.mean() / 10 / 3, ctx["stats"]["wind"].paid_mwh.mean() / 10 / 3]})
        lk.to_excel(xw, sheet_name="Monte Carlo inputs", index=False)
        pd.DataFrame({"rating": list(RATING_PD), "pd_1y": list(RATING_PD.values())}).to_excel(xw, sheet_name="Credit", index=False)

        ws = wb.add_worksheet("Offer")
        ws.activate()
        ws.set_first_sheet()
        ws.write("A1", "PPA offer calculator (pay-as-produced)", bold)
        ws.write("A2", f"Synthetic market data, pricing date {AS_OF}. Yellow cells are inputs; everything else is a formula.")
        rows = [
            ("Technology (solar / wind)", "solar", None), ("Capacity (MW)", 10, inp), ("First delivery year", 2027, inp), ("Tenor (years)", 3, inp),
            ("Counterparty rating", "BBB", None), ("Margin (€/MWh)", 1.0, inp), ("Hedging cost (€/MWh)", 0.35, inp), ("Risk lambda multiplier", 1.0, inp),
        ]
        for i, (lab, val, fmt) in enumerate(rows):
            ws.write(3 + i, 0, lab, hdr)
            ws.write(3 + i, 1, val, fmt or wb.add_format({"bg_color": "#fff4d6", "border": 1}))
        ws.data_validation("B4", {"validate": "list", "source": ["solar", "wind"]})
        ws.data_validation("B8", {"validate": "list", "source": list(RATING_PD)})
        F = "'Monte Carlo inputs'!"
        calc = [
            ("Forward base over the tenor", "=AVERAGEIFS('Forward curve'!$C:$C,'Forward curve'!$B:$B,\">=\"&B6,'Forward curve'!$B:$B,\"<\"&(B6+B7))", eur),
            ("Capture rate (paid hours, Monte Carlo)", f"=INDEX({F}$B:$B,MATCH(B4,{F}$A:$A,0))", pct),
            ("Expected capture price", "=B13*B14", eur),
            ("Balancing", f"=-INDEX({F}$D:$D,MATCH(B4,{F}$A:$A,0))", eur),
            ("Hedging", "=-B10", eur),
            ("Profile risk", f"=-INDEX({F}$E:$E,MATCH(B4,{F}$A:$A,0))*B11", eur),
            ("Volume risk", f"=-INDEX({F}$F:$F,MATCH(B4,{F}$A:$A,0))*B11", eur),
            ("Credit (PD x LGD x exposure x tenor)", f"=-INDEX(Credit!$B:$B,MATCH(B8,Credit!$A:$A,0))*{LGD}*1.65*0.1*B15*SQRT(B7/2)*B7", eur),
            ("Margin", "=-B9", eur),
            ("Offer price", "=SUM(B15:B21)", eurb),
            ("Expected annual volume (MWh)", f"=B5*INDEX({F}$G:$G,MATCH(B4,{F}$A:$A,0))", wb.add_format({"num_format": "#,##0"})),
            ("Contract value over the tenor", "=B22*B23*B7", money),
        ]
        for i, (lab, f, fmt) in enumerate(calc):
            ws.write(12 + i, 0, lab, hdr)
            ws.write_formula(12 + i, 1, f, fmt)
        ws.write(26, 0, "Credit uses 10% of the capture price as the yearly price uncertainty; the full Monte Carlo is in the Python model.")
        ws.set_column("A:A", 40)
        ws.set_column("B:B", 18)

        cmp_ = []
        for tech in ("solar", "wind"):
            from .pricing import summarise_structures
            s = summarise_structures(ctx["struct"][tech]).reset_index(names="structure")
            s.insert(0, "technology", tech)
            cmp_.append(s)
        pd.concat(cmp_).to_excel(xw, sheet_name="Structure comparison", index=False)
        ctx["yearly"].round(3).to_excel(xw, sheet_name="Market by year", index=False)
        ctx["bess"].to_excel(xw, sheet_name="BESS", index=False)
        ctx["crm"]["forecast"].to_excel(xw, sheet_name="Pipeline forecast", index=False)
        for name in ["Forward curve", "Monte Carlo inputs", "Credit", "Structure comparison", "Market by year", "BESS", "Pipeline forecast"]:
            xw.sheets[name].set_column(0, 15, 16)
    return path


DE_CHECKS = {"Close date missing": "Abschlussdatum fehlt", "Probability does not match stage": "Wahrscheinlichkeit passt nicht zur Phase",
             "Volume is zero": "Volumen ist null", "Open deal with close date in the past": "Offene Opportunity mit Abschlussdatum in der Vergangenheit",
             "Open deal without activity for 60+ days": "Offene Opportunity ohne Aktivität seit über 60 Tagen"}


def weekly_report(ctx) -> str:
    """Wöchentlicher Marktbericht: the last full week against the week before, written in German."""
    h = ctx["h"]
    end = h.timestamp.max().normalize()
    wk = h[h.timestamp > end - pd.Timedelta(days=7)]
    prev = h[(h.timestamp > end - pd.Timedelta(days=14)) & (h.timestamp <= end - pd.Timedelta(days=7))]

    def stats(g):
        return {"base": g.price_eur_mwh.mean(), "peak": g[g.is_peak].price_eur_mwh.mean(), "neg": int((g.price_eur_mwh < 0).sum()),
                "solar_cr": (g.price_eur_mwh * g.solar_gw).sum() / g.solar_gw.sum() / g.price_eur_mwh.mean(),
                "spread": g.groupby("date").price_eur_mwh.agg(lambda s: s.max() - s.min()).mean()}
    a, b = stats(wk), stats(prev)
    cal = ctx["d"]["cal27"]
    c_now, c_prev = cal.cal27_base_eur_mwh.iloc[-1], cal.cal27_base_eur_mwh.iloc[-6]
    o = ctx["offers"]
    fc = ctx["crm"]["forecast"]
    issues = ctx["crm"]["checks"]

    def de(x, d=1):
        return f"{x:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")

    lines = [
        f"# Wöchentlicher Marktbericht Strom DE (synthetisch), Woche bis {end:%d.%m.%Y}", "",
        "Automatisch erzeugt mit `python -m ppalab.run`. Alle Daten sind simuliert.", "",
        "## Spotmarkt", "",
        "| Kennzahl | Diese Woche | Vorwoche |", "|---|---|---|",
        f"| Base (€/MWh) | {de(a['base'])} | {de(b['base'])} |",
        f"| Peak (€/MWh) | {de(a['peak'])} | {de(b['peak'])} |",
        f"| Stunden mit negativen Preisen | {a['neg']} | {b['neg']} |",
        f"| Solar Capture Rate | {de(a['solar_cr'] * 100, 0)} % | {de(b['solar_cr'] * 100, 0)} % |",
        f"| Mittlerer Tagesspread (€/MWh) | {de(a['spread'])} | {de(b['spread'])} |", "",
        "## Terminmarkt", "",
        f"Cal-27 Base: {de(c_now, 2)} €/MWh ({de(c_now - c_prev, 2)} €/MWh zur Vorwoche). "
        f"Annualisierte Volatilität (60 Tage): {de(ctx['result']['market']['cal27_vol_annualised'] * 100, 0)} %.", "",
        "## Indikative PPA-Preise (Pay-as-produced, 10 MW, 2027-2029, Gegenpartei BBB)", "",
        f"- Solar: {de(o['solar']['offer_price'], 2)} €/MWh (Capture Rate {de(o['solar']['capture_rate'] * 100, 0)} %, "
        f"{de(o['solar']['curtailed_share'] * 100, 0)} % der möglichen Erzeugung in negativen Stunden)",
        f"- Wind: {de(o['wind']['offer_price'], 2)} €/MWh (Capture Rate {de(o['wind']['capture_rate'] * 100, 0)} %)", "",
        "## Pipeline", "",
        f"Gewichtete Marge mit Abschluss im laufenden Quartal ({fc.quarter.iloc[0]}): {de(fc.weighted_margin_eur.iloc[0] / 1e6, 2)} Mio. € "
        f"bei einem Ziel von {de(fc.target_eur.iloc[0] / 1e6, 2)} Mio. € ({de(fc.coverage.iloc[0] * 100, 0)} % Abdeckung).", "",
        "Datenqualität im CRM:", "",
    ] + [f"- {DE_CHECKS.get(r.check, r.check)}: {r.opportunities}" for r in issues.itertuples()] + [""]
    text = "\n".join(lines)
    (OUTPUTS / "weekly_market_report_de.md").write_text(text)
    return text
