"""Animated summary for a LinkedIn post (outputs/figures/linkedin_post.gif). Numbers come from outputs/.

Run from the project folder:  PYTHONPATH=src python scripts/make_linkedin_gif.py
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from PIL import Image, ImageDraw, ImageFont

from ppalab.config import OUTPUTS

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
    d.text((40, H - 40), "Synthetic market data · github.com/mohammedelsayed741996-blip", font=font("Medium", 17),
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
        for k, (txt, col) in enumerate([("Your solar park makes", WHITE), ("1 MWh at noon.", WHITE), ("What is it worth?", YELLOW)]):
            d.text((60, 220 + 64 * k), txt, font=font("ExtraBold", 46), fill=mix(col, NAVY, a))
        b = ease((i - 10) / 8)
        d.text((60, 470), "Pricing a PPA from the forward curve,", font=font("Medium", 25), fill=mix((200, 205, 215), NAVY, b))
        d.text((60, 506), "step by step.", font=font("Medium", 25), fill=mix((200, 205, 215), NAVY, b))
        footer(d, light=True)
        out.append(im)
    return out


def scene_capture(y, n=50):
    out = []
    for i in range(n):
        im, d = frame()
        d.text((40, 44), "Solar earns less every year", font=font("ExtraBold", 36), fill=INK)
        d.text((40, 98), "Capture rate: what solar earns per MWh / baseload price", font=font("Medium", 21), fill=MUTED)
        rows = y[y.hours > 8000]
        for k, r in enumerate(rows.itertuples()):
            a = ease((i - k * 3) / 6)
            yy = 160 + k * 56
            d.text((40, yy), str(r.year), font=font("SemiBold", 22), fill=mix(INK, PAPER, a))
            w = int(420 * r.solar_capture_rate * a)
            d.rounded_rectangle((120, yy + 2, 120 + max(w, 4), yy + 30), 6, fill=mix(YELLOW, PAPER, a))
            d.text((130 + w, yy + 16), f"{r.solar_capture_rate:.0%}", font=font("Bold", 20), fill=mix(INK, PAPER, a), anchor="lm")
            d.text((700, yy + 16), f"{r.negative_hours}", font=font("SemiBold", 20), fill=mix(ORANGE, PAPER, a), anchor="rm")
        d.text((700, 135), "negative hours", font=font("Medium", 16), fill=MUTED, anchor="rm")
        footer(d)
        out.append(im)
    return out


def scene_walk(o, n=56):
    steps = [("Forward base 2027-29", o["forward_base"]), ("Solar produces in cheap hours", o["shape"]), ("No output in negative hours", o["curtailment_uplift"]),
             ("Balancing", o["balancing"]), ("Hedging, profile, volume, credit", o["hedging"] + o["profile_risk"] + o["volume_risk"] + o["credit"]),
             ("Margin", o["margin"])]
    out = []
    for i in range(n):
        im, d = frame()
        d.text((40, 44), "From forward price to offer", font=font("ExtraBold", 36), fill=INK)
        d.text((40, 98), "10 MW solar, pay-as-produced, 2027-2029, EUR/MWh", font=font("Medium", 21), fill=MUTED)
        for k, (lab, v) in enumerate(steps):
            a = ease((i - k * 4) / 6)
            yy = 160 + k * 66
            col = BLUE if k == 0 else (GREEN if v >= 0 else ORANGE)
            d.text((40, yy), lab, font=font("Medium", 23), fill=mix(INK, PAPER, a))
            d.text((760, yy), f"{v:.2f}" if k == 0 else f"{v:+.2f}", font=font("Bold", 24), fill=mix(col, PAPER, a), anchor="ra")
        e = ease((i - 30) / 8)
        d.line((40, 570, 760, 570), fill=mix(LINE, PAPER, e), width=2)
        d.text((40, 592), "Offer price", font=font("ExtraBold", 30), fill=mix(INK, PAPER, e))
        d.text((760, 592), f"{o['offer_price']:.2f}", font=font("ExtraBold", 30), fill=mix(PURPLE, PAPER, e), anchor="ra")
        footer(d)
        out.append(im)
    return out


def scene_struct(s, n=52):
    names = [("merchant", "Merchant, no PPA"), ("pay_as_produced", "Pay-as-produced PPA"), ("baseload", "Baseload PPA")]
    out = []
    for i in range(n):
        im, d = frame()
        d.text((40, 44), "Who carries the risk?", font=font("ExtraBold", 36), fill=INK)
        d.text((40, 98), "What the solar producer earns, 100 scenarios", font=font("Medium", 21), fill=MUTED)
        lo_x, hi_x = 40, 760
        scale = lambda v: lo_x + (v - 40) / (85 - 40) * (hi_x - lo_x)
        for k, (key, lab) in enumerate(names):
            a = ease((i - k * 6) / 8)
            yy = 190 + k * 130
            d.text((40, yy), lab, font=font("SemiBold", 24), fill=mix(INK, PAPER, a))
            p90, p10, mu = s["P90 (bad case)"][key], s["P10 (good case)"][key], s["expected"][key]
            x1, x2 = scale(p90), scale(p90 + (p10 - p90) * a)
            d.rounded_rectangle((x1, yy + 48, max(x2, x1 + 12), yy + 66), 9, fill=mix((190, 212, 242), PAPER, a))
            d.ellipse((scale(mu) - 9, yy + 48, scale(mu) + 9, yy + 66), fill=mix(BLUE, PAPER, a))
            txt = f"{mu:.1f} expected" + ("" if p10 == p90 else f", {p90:.0f} to {p10:.0f}")
            d.text((40, yy + 76), txt, font=font("Medium", 20), fill=mix(MUTED, PAPER, a))
        footer(d)
        out.append(im)
    return out


def scene_bess(r, n=40):
    out = []
    b = r["bess"][-2]
    st = r["solar_plus_storage"][-2]
    for i in range(n):
        im, d = frame()
        d.text((40, 44), "And the battery?", font=font("ExtraBold", 36), fill=INK)
        a, e = ease(i / 8), ease((i - 14) / 8)
        d.text((40, 140), "1 MW / 2 MWh, day-ahead arbitrage, 2025", font=font("Medium", 23), fill=mix(MUTED, PAPER, a))
        d.text((40, 180), f"EUR {b['realistic_eur_per_mw_year']:,.0f} per MW", font=font("ExtraBold", 44), fill=mix(GREEN, PAPER, a))
        d.text((40, 244), f"(EUR {b['revenue_eur_per_mw_year']:,.0f} with perfect foresight)", font=font("Medium", 21), fill=mix(MUTED, PAPER, a))
        d.text((40, 360), "Next to a 10 MW solar park, 5 MW / 10 MWh", font=font("Medium", 23), fill=mix(MUTED, PAPER, e))
        d.text((40, 400), f"+{st['uplift_eur_mwh']:.0f} EUR/MWh", font=font("ExtraBold", 44), fill=mix(PURPLE, PAPER, e))
        d.text((40, 464), "on the solar price, by moving noon into the evening", font=font("Medium", 21), fill=mix(MUTED, PAPER, e))
        footer(d)
        out.append(im)
    return out


def scene_end(n=40):
    out = []
    for i in range(n):
        im, d = frame(NAVY)
        a = ease(i / 8)
        d.text((60, 140), "PPA pricing analyzer", font=font("ExtraBold", 48), fill=mix(WHITE, NAVY, a))
        items = ["Market trends, volatility, negative hours", "Hourly price forward curve", "Monte Carlo PPA offers with a price walk",
                 "Pay-as-produced vs baseload vs swap", "Battery arbitrage and hybrid value", "Pipeline report and a German weekly report"]
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
    y = pd.read_csv(OUTPUTS / "market_yearly.csv")
    frames = scene_title() + scene_capture(y) + scene_walk(r["ppa"]["solar"]) + scene_struct(r["structures"]["solar"]) + scene_bess(r) + scene_end()
    path = OUTPUTS / "figures" / "linkedin_post.gif"
    pal = [f.convert("P", palette=Image.ADAPTIVE, colors=64) for f in frames]
    pal[0].save(path, save_all=True, append_images=pal[1:], duration=90, loop=0, optimize=True, disposal=1)
    print(f"{path} {len(frames)} frames, {path.stat().st_size / 1e6:.2f} MB")


if __name__ == "__main__":
    main()
