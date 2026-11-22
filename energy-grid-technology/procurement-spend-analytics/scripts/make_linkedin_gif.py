"""Animated summary for a LinkedIn post (outputs/figures/linkedin_post.gif). Numbers come from outputs/.

Run from the project folder:  PYTHONPATH=src python scripts/make_linkedin_gif.py
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from PIL import Image, ImageDraw, ImageFont

from spendcube.config import OUTPUTS

W = H = 800
FONT_DIR = Path("/usr/share/fonts/opentype/inter")
NAVY, INK, PAPER, MUTED, LINE = (16, 30, 58), (11, 11, 11), (252, 252, 251), (82, 81, 78), (228, 227, 223)
BLUE, ORANGE, GREEN, YELLOW, AMBER = (42, 120, 214), (235, 104, 52), (27, 175, 122), (237, 161, 0), (255, 246, 224)
WHITE, CARD, USER = (255, 255, 255), (244, 243, 240), (226, 236, 250)


def font(w, s):
    p = FONT_DIR / f"Inter-{w}.otf"
    return ImageFont.truetype(str(p if p.exists() else "DejaVuSans.ttf"), s)


def ease(x):
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


def mix(c, bg, a):
    return tuple(int(c[k] * a + bg[k] * (1 - a)) for k in range(3))


def frame(bg=PAPER):
    im = Image.new("RGB", (W, H), bg)
    return im, ImageDraw.Draw(im)


def footer(d, light=False):
    d.text((40, H - 40), "Fictional company, synthetic data · github.com/mohammedelsayed741996-blip", font=font("Medium", 17),
           fill=(180, 190, 210) if light else MUTED, anchor="ls")


def bubble(d, x, y, w, text, fill, f, color=INK, width=40):
    lines = textwrap.wrap(text, width)
    h = 24 + 30 * len(lines)
    d.rounded_rectangle((x, y, x + w, y + h), 16, fill=fill)
    for i, ln in enumerate(lines):
        d.text((x + 18, y + 14 + 30 * i), ln, font=f, fill=color)
    return y + h



PURPLE = (138, 92, 209)


def scene_title(n=28):
    out = []
    for i in range(n):
        im, d = frame(NAVY)
        a = ease(i / 8)
        for k, (txt, col) in enumerate([("Two ERP systems.", WHITE), ("Six ways to write", WHITE), ("\"30 days net\".", WHITE), ("One spend cube.", YELLOW)]):
            d.text((60, 180 + 62 * k), txt, font=font("ExtraBold", 46), fill=mix(col, NAVY, a))
        b = ease((i - 10) / 8)
        d.text((60, 470), "Procurement data quality, supplier analytics", font=font("Medium", 25), fill=mix((200, 205, 215), NAVY, b))
        d.text((60, 506), "and commodity price forecasting.", font=font("Medium", 25), fill=mix((200, 205, 215), NAVY, b))
        footer(d, light=True)
        out.append(im)
    return out


def scene_merge(n=52):
    names = ["ERP_A 1000056   Saar Draht GmbH & Co. KG", "ERP_B PLS-5008   Saar Draht G.m.b.H. & Co. KG"]
    out = []
    for i in range(n):
        im, d = frame()
        d.text((40, 44), "Is this one supplier or two?", font=font("ExtraBold", 36), fill=INK)
        d.text((40, 98), "Matched on VAT ID first, then on the normalised name", font=font("Medium", 21), fill=MUTED)
        m = ease((i - 14) / 12)
        for k, nme in enumerate(names):
            y0 = 170 + k * 90
            y = int(y0 + (250 - y0) * m) if k else int(y0 + (250 - y0) * m)
            col = mix(CARD, PAPER, 1)
            d.rounded_rectangle((40, y, 720, y + 56), 12, fill=col, outline=LINE, width=2)
            d.text((60, y + 28), nme, font=font("SemiBold", 22), fill=mix(INK, CARD, 1 - 0.7 * m if k else 1), anchor="lm")
        e = ease((i - 28) / 8)
        if e > 0:
            d.rounded_rectangle((40, 250, 720, 306), 12, fill=mix(GREEN, PAPER, e))
            d.text((60, 278), "Golden record S0009   Saar Draht GmbH & Co. KG", font=font("Bold", 22), fill=mix(WHITE, GREEN, e), anchor="lm")
            d.text((40, 360), "167 supplier records became 115 companies", font=font("ExtraBold", 27), fill=mix(INK, PAPER, e))
            d.text((40, 404), "All 55 duplicate pairs found, no false merges.", font=font("Medium", 23), fill=mix(MUTED, PAPER, e))
            d.text((40, 440), "\"Ruhr Stahlbau S.A.\" and \"... Sp. z o.o.\" have", font=font("Medium", 23), fill=mix(MUTED, PAPER, e))
            d.text((40, 476), "different legal forms, so a person decides.", font=font("Medium", 23), fill=mix(MUTED, PAPER, e))
        footer(d)
        out.append(im)
    return out


def scene_dq(found, n=50):
    out = []
    labels = {"Duplicate order lines in the ERP_A export": "Duplicate order lines", "Order lines with a supplier missing from the master": "Supplier not in master",
              "ERP_B lines without a category": "Missing category", "Copper lines priced per tonne on a per-kg line": "Price per tonne on a kg line",
              "Returns booked as negative quantities": "Returns as negative quantity", "Suppliers without a country": "Supplier without country",
              "Goods receipts dated before the order": "Receipt before order", "Duplicate supplier pairs (within and across ERPs)": "Duplicate supplier pairs"}
    for i in range(n):
        im, d = frame()
        d.text((40, 44), "12 data quality rules", font=font("ExtraBold", 36), fill=INK)
        d.text((40, 98), "Problems planted in the data vs found by the rules", font=font("Medium", 21), fill=MUTED)
        for k, r in enumerate(found.itertuples()):
            a = ease((i - k * 3) / 6)
            y = 160 + k * 58
            d.text((40, y), labels[r.planted_problem], font=font("Medium", 22), fill=mix(INK, PAPER, a))
            d.text((560, y), f"{int(r.found * a)} / {r.planted}", font=font("Bold", 22), fill=mix(GREEN, PAPER, a))
            if a > 0.98:
                d.text((700, y), "✓", font=font("Bold", 24), fill=GREEN)
        e = ease((i - 30) / 8)
        d.text((40, 650), "Every rule has an owner role and an action.", font=font("SemiBold", 23), fill=mix(INK, PAPER, e))
        footer(d)
        out.append(im)
    return out


def scene_spend(h, n=48):
    out = []
    parts = [("Active framework agreement", h["on_contract_share"], BLUE), ("Agreement expired end of 2025", h["maverick_expired_contract_eur"] / h["spend_eur"], YELLOW),
             ("No agreement with this supplier", h["maverick_no_contract_eur"] / h["spend_eur"], ORANGE)]
    for i in range(n):
        im, d = frame()
        d.text((40, 44), f"€{h['spend_eur'] / 1e6:,.0f}m of spend, two years", font=font("ExtraBold", 36), fill=INK)
        d.text((40, 98), f"{h['suppliers_for_80pct']} suppliers carry 80% of it; {h['tail_suppliers']} share the last 5%", font=font("Medium", 21), fill=MUTED)
        a = ease(i / 18)
        x = 40
        for lab, share, col in parts:
            w = int(720 * share * a)
            if w > 2:
                d.rectangle((x, 180, x + w, 250), fill=col)
            x += w
        for k, (lab, share, col) in enumerate(parts):
            b = ease((i - 14 - k * 4) / 6)
            y = 300 + k * 70
            d.rectangle((40, y + 4, 64, y + 28), fill=mix(col, PAPER, b))
            d.text((80, y + 16), lab, font=font("Medium", 23), fill=mix(INK, PAPER, b), anchor="lm")
            d.text((760, y + 16), f"{share:.0%}", font=font("Bold", 26), fill=mix(col, PAPER, b), anchor="rm")
        e = ease((i - 32) / 8)
        d.text((40, 560), f"Quickest win: renew the expired agreements", font=font("SemiBold", 25), fill=mix(INK, PAPER, e))
        d.text((40, 600), f"(€{h['maverick_expired_contract_eur'] / 1e6:,.0f}m with suppliers we already know).", font=font("Medium", 23), fill=mix(MUTED, PAPER, e))
        footer(d)
        out.append(im)
    return out


def scene_forecast(r, n=50):
    out = []
    rows = [("Naive: next month = this month", 7.75, BLUE), ("AR on returns", 7.84, MUTED), ("Holt, damped trend", 8.03, MUTED),
            ("Drift", 8.17, MUTED), ("Seasonal naive", 11.16, MUTED)]
    for i in range(n):
        im, d = frame()
        d.text((40, 44), "Can we forecast copper?", font=font("ExtraBold", 36), fill=INK)
        d.text((40, 98), "Mean error, 1 to 6 months ahead, 5 commodities", font=font("Medium", 21), fill=MUTED)
        for k, (lab, v, col) in enumerate(rows):
            a = ease((i - k * 3) / 8)
            y = 160 + k * 64
            d.text((40, y), lab, font=font("Medium", 22), fill=mix(INK, PAPER, a))
            w = int(270 * v / 12 * a)
            d.rounded_rectangle((420, y + 2, 420 + max(w, 4), y + 30), 6, fill=mix(col, PAPER, a))
            d.text((430 + w, y + 16), f"{v:.2f}%", font=font("Bold", 20), fill=mix(INK, PAPER, a), anchor="lm")
        e = ease((i - 24) / 8)
        d.text((40, 500), "Not better than naive. So the plan uses bands:", font=font("SemiBold", 25), fill=mix(INK, PAPER, e))
        d.text((40, 544), f"80% bands held {r['forecast']['band_coverage_80pct']:.0%} of outcomes in the backtest.", font=font("Medium", 23), fill=mix(MUTED, PAPER, e))
        f = ease((i - 32) / 8)
        d.text((40, 610), "73% of our copper price follows the index", font=font("Medium", 23), fill=mix(MUTED, PAPER, f))
        d.text((40, 644), "with a one-month delay, read from our own orders.", font=font("Medium", 23), fill=mix(MUTED, PAPER, f))
        footer(d)
        out.append(im)
    return out


def scene_end(n=40):
    out = []
    for i in range(n):
        im, d = frame(NAVY)
        a = ease(i / 8)
        d.text((60, 140), "Procurement spend cube", font=font("ExtraBold", 48), fill=mix(WHITE, NAVY, a))
        items = ["Data source profiling and 12 quality rules", "Golden supplier records with a review queue", "Star schema, SQL views and Power BI measures",
                 "Supplier scorecard and Kraljic matrix", "Commodity forecasts with honest bands", "Excel cube and a management deck in German"]
        for k, t in enumerate(items):
            b = ease((i - 4 - k * 2) / 5)
            d.ellipse((62, 254 + k * 50, 74, 266 + k * 50), fill=mix(YELLOW, NAVY, b))
            d.text((92, 260 + k * 50), t, font=font("Medium", 24), fill=mix((215, 215, 215), NAVY, b), anchor="lm")
        e = ease((i - 18) / 6)
        d.text((60, 640), "Code and Colab notebooks:", font=font("Medium", 22), fill=mix((200, 200, 200), NAVY, e))
        d.text((60, 676), "github.com/mohammedelsayed741996-blip/", font=font("Bold", 25), fill=mix(YELLOW, NAVY, e))
        d.text((60, 710), "berlin-data-portfolio", font=font("Bold", 25), fill=mix(YELLOW, NAVY, e))
        out.append(im)
    return out


def main():
    r = json.loads((OUTPUTS / "results.json").read_text())
    found = pd.read_csv(OUTPUTS / "dq_planted_vs_found.csv")
    frames = scene_title() + scene_dq(found) + scene_merge() + scene_spend(r["spend"]) + scene_forecast(r) + scene_end()
    path = OUTPUTS / "figures" / "linkedin_post.gif"
    pal = [f.convert("P", palette=Image.ADAPTIVE, colors=64) for f in frames]
    pal[0].save(path, save_all=True, append_images=pal[1:], duration=90, loop=0, optimize=True, disposal=1)
    print(f"{path} {len(frames)} frames, {path.stat().st_size / 1e6:.2f} MB")


if __name__ == "__main__":
    main()
