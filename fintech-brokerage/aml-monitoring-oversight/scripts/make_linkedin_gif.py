"""Animated summary for a LinkedIn post (outputs/figures/linkedin_post.gif).

Numbers come from the pipeline run, so the animation matches the README.
Run from the project folder:  PYTHONPATH=src python scripts/make_linkedin_gif.py
"""

from __future__ import annotations

import math
from pathlib import Path

import pandas as pd
from PIL import Image, ImageDraw, ImageFont

from aml_oversight import config as C, pipeline

W = H = 800
FONT_DIR = Path("/usr/share/fonts/opentype/inter")
NAVY, INK, PAPER, MUTED, LINE = (16, 30, 58), (11, 11, 11), (252, 252, 251), (82, 81, 78), (228, 227, 223)
BLUE, ORANGE, GREEN, YELLOW, GREY, RED = (42, 120, 214), (235, 104, 52), (27, 175, 122), (237, 161, 0), (155, 154, 149), (227, 73, 72)
SEV = {"Critical": RED, "High": ORANGE, "Medium": YELLOW}


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
    d.text((40, H - 40), "Synthetic data · github.com/mohammedelsayed741996-blip", font=font("Medium", 17),
           fill=(180, 190, 210) if light else MUTED, anchor="ls")


def scene_title(n=24):
    out = []
    for i in range(n):
        im, d = frame(NAVY)
        a = ease(i / 8)
        for k, line in enumerate(["I audited an AML team", "that doesn't exist."]):
            d.text((60, 250 + k * 66), line, font=font("ExtraBold", 52), fill=mix((255, 255, 255) if k == 0 else YELLOW, NAVY, a))
        b = ease((i - 9) / 8)
        for k, line in enumerate(["A fictional broker · 15,000 clients · 1,919 alerts", "I hid 9 control failures. Could oversight find them?"]):
            d.text((60, 430 + k * 36), line, font=font("Medium", 24), fill=mix((200, 205, 215), NAVY, b))
        footer(d, light=True)
        out.append(im)
    return out


def scene_findings(findings, per=4, hold=16):
    short = {"F05": "Sanctions hit closed by mistake", "F01": "1,016 deposits the rules never saw",
             "F03": "Mule rings: no rule covers them", "F02": "Threshold changed, no approval",
             "F04": "One analyst closes real cases", "F06": "Summer backlog over SLA",
             "F07": "Alerts closed without rationale", "F08": "Screening ran days late",
             "F09": "High-risk reviews overdue"}
    rows = findings[["finding_id", "severity"]].values.tolist()
    out = []
    for i in range(len(rows) * per + hold):
        im, d = frame()
        d.text((40, 48), "What oversight found", font=font("ExtraBold", 40), fill=INK)
        shown = min(len(rows), i // per + 1)
        d.text((W - 40, 52), f"{shown}/9", font=font("ExtraBold", 40), fill=GREEN if shown == 9 else RED, anchor="ra")
        for k, (fid, sev) in enumerate(rows[:shown]):
            y = 128 + k * 62
            a = ease((i - k * per) / per)
            x0 = 40 + int(30 * (1 - a))
            d.rounded_rectangle((x0, y, W - 40, y + 52), 9, fill=(244, 243, 240))
            d.text((x0 + 16, y + 26), fid, font=font("Bold", 18), fill=MUTED, anchor="lm")
            d.text((x0 + 70, y + 26), short[fid], font=font("SemiBold", 21), fill=INK, anchor="lm")
            d.rounded_rectangle((W - 160, y + 13, W - 54, y + 39), 13, fill=SEV[sev])
            d.text((W - 107, y + 26), sev.upper(), font=font("Bold", 14), fill=(255, 255, 255), anchor="mm")
        footer(d)
        out.append(im)
    return out


def scene_feed(tx, feed_ids, n=34):
    t = tx[(tx["channel"] == "CARD") & (tx["psp"] == C.FEED_GAP[2]) & (tx["type"] == "DEPOSIT") & tx["date"].between("2026-05-15", "2026-07-31")]
    led = t.groupby("date").size()
    fed = t[t["tx_id"].isin(feed_ids["tx_id"])].groupby("date").size().reindex(led.index, fill_value=0)
    x0, x1, y0, y1 = 60, W - 60, 560, 200
    vmax = led.max() * 1.15
    px = lambda i: x0 + (x1 - x0) * i / (len(led) - 1)  # noqa: E731
    py = lambda v: y0 - (y0 - y1) * v / vmax  # noqa: E731
    out = []
    gi0 = list(led.index).index(next(d for d in led.index if d >= C.FEED_GAP[0]))
    gi1 = list(led.index).index(max(d for d in led.index if d <= C.FEED_GAP[1]))
    for i in range(n):
        im, d = frame()
        d.text((40, 48), "1,016 deposits the rules never saw", font=font("ExtraBold", 36), fill=INK)
        d.text((40, 100), "Card deposits per day: core ledger vs monitoring feed", font=font("Medium", 19), fill=MUTED)
        upto = int(len(led) * ease(i / 22))
        if upto >= gi0:
            d.rectangle((px(gi0), y1, px(gi1), y0), fill=(252, 236, 236))
        for series, col, w in [(led.values, GREY, 4), (fed.values, BLUE, 4)]:
            pts = [(px(k), py(v)) for k, v in enumerate(series[:max(upto, 2)])]
            d.line(pts, fill=col, width=w, joint="curve")
        d.line((x0, y0, x1, y0), fill=LINE, width=2)
        d.text((x0, y0 + 30), "15 May", font=font("Medium", 16), fill=MUTED)
        d.text((x1, y0 + 30), "31 Jul", font=font("Medium", 16), fill=MUTED, anchor="ra")
        d.line((x0, 172, x0 + 28, 172), fill=GREY, width=4)
        d.text((x0 + 36, 172), "core ledger", font=font("SemiBold", 18), fill=GREY, anchor="lm")
        d.line((x0 + 180, 172, x0 + 208, 172), fill=BLUE, width=4)
        d.text((x0 + 216, 172), "monitoring feed", font=font("SemiBold", 18), fill=BLUE, anchor="lm")
        if i > 22:
            d.text((40, 650), "Nobody noticed: a missing transaction", font=font("SemiBold", 22), fill=RED)
            d.text((40, 682), "never raises an alert.", font=font("SemiBold", 22), fill=RED)
        footer(d)
        out.append(im)
    return out


def scene_rings(n=34):
    out = []
    centers = [(200, 300), (400, 260), (600, 300), (200, 500), (400, 540), (600, 500)]
    for i in range(n):
        im, d = frame()
        d.text((40, 48), "6 mule rings the rules missed", font=font("ExtraBold", 38), fill=INK)
        d.text((40, 100), "Six clients each, all paying out to one shared account", font=font("Medium", 19), fill=MUTED)
        for k, (cx, cy) in enumerate(centers):
            a = ease((i - k * 3) / 6)
            if a <= 0:
                continue
            for j in range(6):
                ang = 2 * math.pi * j / 6 + k
                x, y = cx + 70 * a * math.cos(ang), cy + 70 * a * math.sin(ang)
                d.line((cx, cy, x, y), fill=LINE, width=3)
                d.ellipse((x - 10, y - 10, x + 10, y + 10), fill=BLUE)
            d.ellipse((cx - 16, cy - 16, cx + 16, cy + 16), fill=RED)
        if i > 22:
            d.text((40, 660), "Found with a link analysis on shared accounts", font=font("SemiBold", 22), fill=GREEN)
            d.text((40, 692), "and devices. Four lines of SQL.", font=font("SemiBold", 22), fill=GREEN)
        footer(d)
        out.append(im)
    return out


def scene_qa(qa, n=30):
    d_ = qa[qa["error_type"] == "decision_error"].sort_values("analyst")
    out = []
    x0, x1, y0, y1 = 80, W - 50, 560, 190
    vmax = 0.42
    for i in range(n):
        im, d = frame()
        d.text((40, 48), "Which analyst needs a lookback?", font=font("ExtraBold", 36), fill=INK)
        d.text((40, 100), "QA re-review of closed alerts, 95% confidence intervals", font=font("Medium", 19), fill=MUTED)
        y5 = y0 - (y0 - y1) * C.QA_TOLERABLE_ERROR / vmax
        d.line((x0, y5, x1, y5), fill=MUTED, width=2)
        d.text((x1, y5 - 8), "tolerable 5%", font=font("Medium", 15), fill=MUTED, anchor="rs")
        for k, r in enumerate(d_.itertuples()):
            a = ease((i - k * 2) / 6)
            x = x0 + (x1 - x0) * (k + 0.5) / len(d_)
            lo, hi, e = (y0 - (y0 - y1) * v * a / vmax for v in (r.ci_low, r.ci_high, r.error_rate))
            col = RED if r.analyst == C.WEAK_ANALYST else BLUE
            d.rounded_rectangle((x - 6, hi, x + 6, lo), 6, fill=(228, 227, 223))
            d.ellipse((x - 11, e - 11, x + 11, e + 11), fill=col)
            d.text((x, y0 + 30), r.analyst, font=font("SemiBold", 18), fill=col if r.analyst == C.WEAK_ANALYST else INK, anchor="mm")
        if i > 18:
            d.text((40, 650), "Only A06's whole interval sits above 5%.", font=font("SemiBold", 22), fill=RED)
            d.text((40, 682), "That is the evidence for a full lookback.", font=font("SemiBold", 22), fill=MUTED)
        footer(d)
        out.append(im)
    return out


def scene_end(n=38):
    out = []
    for i in range(n):
        im, d = frame(NAVY)
        a = ease(i / 8)
        d.text((60, 160), "AML monitoring", font=font("ExtraBold", 50), fill=mix((255, 255, 255), NAVY, a))
        d.text((60, 222), "oversight + MI", font=font("ExtraBold", 50), fill=mix((255, 255, 255), NAVY, a))
        items = ["Ledger-to-feed reconciliation", "Rule volume and below-the-line tests", "QA sampling with confidence intervals",
                 "KRI heat map, Excel MI pack", "Board report with German summary"]
        for k, s in enumerate(items):
            b = ease((i - 4 - k * 2) / 5)
            d.ellipse((62, 334 + k * 46, 74, 346 + k * 46), fill=mix(YELLOW, NAVY, b))
            d.text((92, 340 + k * 46), s, font=font("Medium", 25), fill=mix((215, 215, 215), NAVY, b), anchor="lm")
        e = ease((i - 16) / 6)
        d.text((60, 640), "Code and Colab notebooks:", font=font("Medium", 22), fill=mix((200, 200, 200), NAVY, e))
        d.text((60, 676), "github.com/mohammedelsayed741996-blip/", font=font("Bold", 25), fill=mix(YELLOW, NAVY, e))
        d.text((60, 710), "berlin-data-portfolio", font=font("Bold", 25), fill=mix(YELLOW, NAVY, e))
        out.append(im)
    return out


def main():
    r = pipeline.run(pipeline.load_tables())
    t = r.tables
    frames = (scene_title() + scene_findings(r.findings) + scene_feed(t["transactions"], t["tm_feed_ids"]) + scene_rings()
              + scene_qa(r.qa_by_analyst) + scene_end())
    path = C.Paths().figures / "linkedin_post.gif"
    pal = [f.convert("P", palette=Image.ADAPTIVE, colors=64) for f in frames]
    pal[0].save(path, save_all=True, append_images=pal[1:], duration=90, loop=0, optimize=True, disposal=1)
    print(f"{path} {len(frames)} frames, {path.stat().st_size / 1e6:.2f} MB")


if __name__ == "__main__":
    main()
