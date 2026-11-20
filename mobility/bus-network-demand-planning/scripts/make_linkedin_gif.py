"""Animated summary for a LinkedIn post (outputs/figures/linkedin_post.gif).

Numbers come from the pipeline run, so the animation matches the README.
Run from the project folder:  PYTHONPATH=src python scripts/make_linkedin_gif.py
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from bus_network import config as C, pipeline

W = H = 800
FONT_DIR = Path("/usr/share/fonts/opentype/inter")
NAVY, INK, PAPER, MUTED, LINE = (16, 30, 58), (11, 11, 11), (252, 252, 251), (82, 81, 78), (228, 227, 223)
BLUE, ORANGE, GREEN, YELLOW, GREY, RED = (42, 120, 214), (235, 104, 52), (27, 175, 122), (237, 161, 0), (155, 154, 149), (227, 73, 72)
WHITE = (255, 255, 255)


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


def scene_title(n=26):
    out = []
    for i in range(n):
        im, d = frame(NAVY)
        a = ease(i / 8)
        for k, line in enumerate(["I planned a bus network", "that doesn't exist."]):
            d.text((60, 250 + k * 66), line, font=font("ExtraBold", 50), fill=mix(WHITE if k == 0 else YELLOW, NAVY, a))
        b = ease((i - 9) / 8)
        for k, line in enumerate(["22 lines · 32 cities · about 80,000 trips", "I hid 6 problems in its data. Would the checks find them?"]):
            d.text((60, 430 + k * 36), line, font=font("Medium", 24), fill=mix((200, 205, 215), NAVY, b))
        footer(d, light=True)
        out.append(im)
    return out


def _proj(G):
    lons = [C.CITIES[c][1] * np.cos(np.radians(51)) for c in C.CITIES]
    lats = [C.CITIES[c][0] for c in C.CITIES]
    x0, x1, y0, y1 = min(lons), max(lons), min(lats), max(lats)
    s = min(600 / (x1 - x0), 540 / (y1 - y0))

    def xy(city):
        lat, lon = C.CITIES[city][:2]
        return 60 + (lon * np.cos(np.radians(51)) - x0) * s, 150 + (y1 - lat) * s
    return xy


def scene_map(G, gaps, n=46):
    xy = _proj(G)
    edges = sorted(G.edges(data=True), key=lambda e: -e[2]["pax_proxy"])
    lmax = edges[0][2]["pax_proxy"]
    out = []
    for i in range(n):
        im, d = frame()
        d.text((40, 48), "The network", font=font("ExtraBold", 40), fill=INK)
        d.text((40, 100), "Line width = passengers on board", font=font("Medium", 20), fill=MUTED)
        shown = int(len(edges) * ease(i / 24))
        for a, b, e in edges[:shown]:
            w = int(2 + 10 * e["pax_proxy"] / lmax)
            d.line([xy(a), xy(b)], fill=mix(BLUE, PAPER, 0.45 + 0.55 * e["pax_proxy"] / lmax), width=w)
        g = ease((i - 26) / 8)
        if g > 0:
            for r in gaps.head(3).itertuples():
                (xa, ya), (xb, yb) = xy(r.origin), xy(r.destination)
                for t in np.arange(0, 1, 0.08):
                    t2 = min(t + 0.045, 1)
                    d.line([(xa + (xb - xa) * t, ya + (yb - ya) * t), (xa + (xb - xa) * t2, ya + (yb - ya) * t2)],
                           fill=mix(ORANGE, PAPER, g), width=4)
            d.text((W - 40, 100), "- - demand, no direct line", font=font("Bold", 20), fill=mix(ORANGE, PAPER, g), anchor="ra")
        for c, (lat, lon, pop, cc) in C.CITIES.items():
            x, y = xy(c)
            r = 4 + pop ** 0.5 / 12
            d.ellipse((x - r, y - r, x + r, y + r), fill=PAPER, outline=INK, width=2)
        for c in ["Berlin", "Hamburg", "Munich", "Frankfurt", "Cologne", "Warsaw", "Vienna", "Amsterdam", "Leipzig"]:
            x, y = xy(c)
            d.text((x + 9, y - 9), c, font=font("SemiBold", 15), fill=MUTED)
        footer(d)
        out.append(im)
    return out


def scene_seats(mismatch, n=40):
    trips, over, worst = int(mismatch["trips"].iloc[0]), int(mismatch["overbooked_trips"].iloc[0]), int(mismatch["max_seats_over"].iloc[0])
    out = []
    for i in range(n):
        im, d = frame()
        d.text((40, 48), "Problem 1 of 6", font=font("Bold", 22), fill=RED)
        d.text((40, 82), "The bus was smaller", font=font("ExtraBold", 40), fill=INK)
        d.text((40, 132), "than the ticket.", font=font("ExtraBold", 40), fill=INK)
        a = ease(i / 12)
        # seats sold vs seats on the bus, as seat grids
        for k, (label, seats, col) in enumerate([("Ticketing sells", 79, BLUE), ("Partner runs", 49, RED)]):
            y0 = 230 + k * 200
            d.text((40, y0), label, font=font("SemiBold", 24), fill=INK)
            d.text((W - 40, y0), f"{seats} seats", font=font("ExtraBold", 28), fill=col, anchor="ra")
            show = int(seats * ease((i - k * 8) / 12))
            for s in range(show):
                r, c = divmod(s, 20)
                x, y = 40 + c * 36, y0 + 44 + r * 30
                d.rounded_rectangle((x, y, x + 28, y + 22), 5, fill=mix(col, PAPER, 0.85))
        b = ease((i - 22) / 8)
        d.text((40, 680), f"{over} of {trips} trips overbooked, by up to {worst} seats", font=font("Bold", 25), fill=mix(INK, PAPER, b))
        footer(d)
        out.append(im)
    return out


def scene_forecast(bt, weekly, n=40):
    w = weekly.groupby("week")[["unconstrained_pax", "pax", "pred"]].sum().iloc[1:-1]
    ymax = w.values.max() * 1.08
    X0, X1, Y0, Y1 = 60, 740, 600, 250

    def pts(col, upto):
        k = len(w)
        return [(X0 + (X1 - X0) * j / (k - 1), Y0 - (Y0 - Y1) * w[col].iloc[j] / ymax) for j in range(upto)]
    out = []
    for i in range(n):
        im, d = frame()
        d.text((40, 48), "Sold-out buses hide demand", font=font("ExtraBold", 38), fill=INK)
        d.text((40, 100), "Bookings stop at the seat count. The forecast has to look past them.", font=font("Medium", 20), fill=MUTED)
        d.line([(X0, Y0), (X1, Y0)], fill=LINE, width=2)
        upto = max(2, int(len(w) * ease(i / 22)))
        for col, c, wd in [("unconstrained_pax", INK, 5), ("pax", GREY, 5), ("pred", BLUE, 4)]:
            d.line(pts(col, upto), fill=c, width=wd, joint="curve")
        for k, (lab, c) in enumerate([("True demand", INK), ("Bookings", GREY), ("Forecast", BLUE)]):
            d.rectangle((60 + k * 220, 170, 84 + k * 220, 178), fill=c)
            d.text((94 + k * 220, 174), lab, font=font("SemiBold", 19), fill=c, anchor="lm")
        b = ease((i - 24) / 8)
        d.text((60, 650), f"Forecast error {bt['naive_wape_vs_true_demand']:.1%} → {bt['model_wape_vs_true_demand']:.1%}",
               font=font("ExtraBold", 32), fill=mix(BLUE, PAPER, b))
        d.text((60, 696), "Winter 2025/26, held out. Naive = same departure last year", font=font("Medium", 18), fill=mix(MUTED, PAPER, b))
        footer(d)
        out.append(im)
    return out


def scene_plan(s, n=44):
    cards = [("Contribution", f"{s['plan_contribution_change_pct']:+.1%}", GREEN),
             ("Bus-hours", f"{s['plan_bus_hours_change_pct']:+.1%}", GREEN),
             ("Sold-out departures", f"{s['sold_out_share_now']:.0%} → {s['sold_out_share_plan']:.0%}", GREEN),
             ("Passengers", "same", BLUE)]
    out = []
    for i in range(n):
        im, d = frame()
        d.text((40, 48), "The winter timetable", font=font("ExtraBold", 40), fill=INK)
        d.text((40, 100), "16 options per line, chosen by a mixed-integer program", font=font("Medium", 20), fill=MUTED)
        for k, (lab, val, col) in enumerate(cards):
            a = ease((i - k * 5) / 8)
            y = 170 + k * 128
            x0 = 40 + int(40 * (1 - a))
            d.rounded_rectangle((x0, y, W - 40, y + 108), 14, fill=mix((244, 243, 240), PAPER, a))
            d.text((x0 + 28, y + 54), lab, font=font("SemiBold", 28), fill=mix(INK, PAPER, a), anchor="lm")
            d.text((W - 68, y + 54), val, font=font("ExtraBold", 44), fill=mix(col, PAPER, a), anchor="rm")
        footer(d)
        out.append(im)
    return out


def scene_end(n=34):
    out = []
    for i in range(n):
        im, d = frame(NAVY)
        a = ease(i / 8)
        d.text((60, 160), "Bus network:", font=font("ExtraBold", 50), fill=mix(WHITE, NAVY, a))
        d.text((60, 222), "data to timetable", font=font("ExtraBold", 50), fill=mix(WHITE, NAVY, a))
        items = ["8 checks across 4 planning systems", "Load factor on passenger-km", "Network graph and gravity model",
                 "Forecast that corrects for sold-out buses", "Maps, Excel report, runbook"]
        for k, txt in enumerate(items):
            b = ease((i - 4 - k * 2) / 5)
            d.ellipse((62, 334 + k * 46, 74, 346 + k * 46), fill=mix(YELLOW, NAVY, b))
            d.text((92, 340 + k * 46), txt, font=font("Medium", 25), fill=mix((215, 215, 215), NAVY, b), anchor="lm")
        e = ease((i - 16) / 6)
        d.text((60, 640), "Code and Colab notebooks:", font=font("Medium", 22), fill=mix((200, 200, 200), NAVY, e))
        d.text((60, 676), "github.com/mohammedelsayed741996-blip/", font=font("Bold", 25), fill=mix(YELLOW, NAVY, e))
        d.text((60, 710), "berlin-data-portfolio", font=font("Bold", 25), fill=mix(YELLOW, NAVY, e))
        out.append(im)
    return out


def main():
    r = pipeline.run()
    frames = (scene_title() + scene_map(r["graph"], r["gaps"]) + scene_seats(r["sql"]["02_capacity_mismatch"])
              + scene_forecast(r["backtest"], r["backtest_weekly"]) + scene_plan(r["summary"]) + scene_end())
    path = C.Paths().figures / "linkedin_post.gif"
    pal = [f.convert("P", palette=Image.ADAPTIVE, colors=64) for f in frames]
    pal[0].save(path, save_all=True, append_images=pal[1:], duration=90, loop=0, optimize=True, disposal=1)
    print(f"{path} {len(frames)} frames, {path.stat().st_size / 1e6:.2f} MB")


if __name__ == "__main__":
    main()
