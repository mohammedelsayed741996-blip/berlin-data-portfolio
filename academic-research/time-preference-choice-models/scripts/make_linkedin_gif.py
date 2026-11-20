"""Animated summary for a LinkedIn post (outputs/figures/linkedin_post.gif).

Numbers are read from outputs/summary.json, so the animation matches the README.
Run from the project folder after the pipeline:  python scripts/make_linkedin_gif.py
"""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
W = H = 800
FONT_DIR = Path("/usr/share/fonts/opentype/inter")
NAVY, INK, PAPER, MUTED, LINE = (16, 30, 58), (11, 11, 11), (252, 252, 251), (82, 81, 78), (228, 227, 223)
BLUE, ORANGE, GREEN, YELLOW, GREY = (42, 120, 214), (235, 104, 52), (27, 175, 122), (237, 161, 0), (155, 154, 149)
WHITE, CARD = (255, 255, 255), (244, 243, 240)


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
    d.text((40, H - 40), "Simulated data · github.com/mohammedelsayed741996-blip", font=font("Medium", 17),
           fill=(180, 190, 210) if light else MUTED, anchor="ls")


def scene_question(n=34):
    out = []
    for i in range(n):
        im, d = frame(NAVY)
        a = ease(i / 8)
        d.text((60, 150), "Quick question.", font=font("ExtraBold", 50), fill=mix(WHITE, NAVY, a))
        for k, (lab, sub, x) in enumerate([("€50", "today", 60), ("€75", "in 3 months", 420)]):
            b = ease((i - 6 - k * 4) / 6)
            d.rounded_rectangle((x, 280, x + 320, 470), 20, fill=mix((34, 52, 92), NAVY, b))
            d.text((x + 160, 350), lab, font=font("ExtraBold", 72), fill=mix(YELLOW if k else WHITE, NAVY, b), anchor="mm")
            d.text((x + 160, 425), sub, font=font("Medium", 26), fill=mix((200, 205, 215), NAVY, b), anchor="mm")
        c = ease((i - 18) / 8)
        d.text((60, 560), "Most of my simulated people take the €50.", font=font("Bold", 30), fill=mix(WHITE, NAVY, c))
        d.text((60, 604), "Which model predicts that best?", font=font("Bold", 30), fill=mix(YELLOW, NAVY, c))
        footer(d, light=True)
        out.append(im)
    return out


def scene_models(s, n=58):
    c = s["completeness"]
    bars = [("Exponential discounting", c["exponential"], BLUE), ("Hyperbolic discounting", c["hyperbolic"], BLUE),
            ("ITCH heuristic", c["itch"], BLUE), ("Machine learning", c["ml_person"], ORANGE)]
    out = []
    for i in range(n):
        im, d = frame()
        d.text((40, 48), "Share of predictable", font=font("ExtraBold", 38), fill=INK)
        d.text((40, 94), "choices each model gets", font=font("ExtraBold", 38), fill=INK)
        d.text((40, 148), "399 simulated people · 23,940 choices · out of sample", font=font("Medium", 19), fill=MUTED)
        X0, X1 = 40, 640
        for k, (lab, v, col) in enumerate(bars):
            y = 210 + k * 105
            a = ease((i - k * 5) / 12)
            d.text((X0, y), lab, font=font("SemiBold", 23), fill=INK)
            d.rounded_rectangle((X0, y + 36, X1, y + 76), 8, fill=CARD)
            w = int((X1 - X0) * v * a)
            if w > 8:
                d.rounded_rectangle((X0, y + 36, X0 + w, y + 76), 8, fill=col)
            d.text((X1 + 16, y + 56), f"{v * a:.0%}", font=font("ExtraBold", 30), fill=col, anchor="lm")
        e = ease((i - 30) / 8)
        d.text((40, 650), "Machine learning wins.", font=font("Bold", 28), fill=mix(INK, PAPER, e))
        d.text((40, 692), "But why?", font=font("Bold", 28), fill=mix(ORANGE, PAPER, e))
        footer(d)
        out.append(im)
    return out


def scene_twist(s, n=52):
    c = s["completeness"]
    out = []
    for i in range(n):
        im, d = frame()
        d.text((40, 48), "The twist", font=font("ExtraBold", 40), fill=INK)
        lines = ["Most of the edge was not a smarter theory.", "It was learning from everyone at once."]
        for k, t in enumerate(lines):
            d.text((40, 112 + k * 36), t, font=font("Medium", 24), fill=mix(MUTED, PAPER, ease((i - k * 4) / 8)))
        X0, X1 = 40, 640
        a = ease((i - 10) / 14)
        rows = [("ITCH, each person alone", c["itch"], BLUE), ("ITCH, shrunk to the group", c["itch"] + (c["itch_eb"] - c["itch"]) * a, GREEN),
                ("Machine learning", c["ml_person"], ORANGE)]
        for k, (lab, v, col) in enumerate(rows):
            y = 240 + k * 110
            d.text((X0, y), lab, font=font("SemiBold", 23), fill=INK)
            d.rounded_rectangle((X0, y + 36, X1, y + 76), 8, fill=CARD)
            d.rounded_rectangle((X0, y + 36, X0 + int((X1 - X0) * v), y + 76), 8, fill=col)
            d.text((X1 + 16, y + 56), f"{v:.0%}", font=font("ExtraBold", 30), fill=col, anchor="lm")
        e = ease((i - 28) / 8)
        d.text((40, 640), "For people who use the heuristic:", font=font("Bold", 25), fill=mix(INK, PAPER, e))
        d.text((40, 680), "shrunk ITCH 88% · machine learning 83%", font=font("ExtraBold", 27), fill=mix(GREEN, PAPER, e))
        footer(d)
        out.append(im)
    return out


def scene_framing(s, n=46):
    f = s["framing"]["share_later"]
    later_delay, later_date = 0.621, 0.753
    out = []
    for i in range(n):
        im, d = frame()
        d.text((40, 48), "Can patience be nudged?", font=font("ExtraBold", 40), fill=INK)
        d.text((40, 104), "Same money, same wait. Only the wording changes.", font=font("Medium", 22), fill=MUTED)
        for k, (lab, v, col) in enumerate([('"in 90 days"', later_delay, BLUE), ('"on 19 February"', later_date, ORANGE)]):
            x = 90 + k * 330
            a = ease((i - k * 6) / 14)
            hgt = int(380 * v * a)
            d.rounded_rectangle((x, 600 - hgt, x + 240, 600), 14, fill=col)
            d.text((x + 120, 585 - hgt), f"{v * a:.0%}", font=font("ExtraBold", 40), fill=col, anchor="mb")
            d.text((x + 120, 640), lab, font=font("SemiBold", 25), fill=INK, anchor="mm")
        d.line([(60, 600), (740, 600)], fill=LINE, width=2)
        e = ease((i - 24) / 8)
        d.text((40, 180), "chose to wait", font=font("SemiBold", 22), fill=mix(MUTED, PAPER, e))
        d.text((40, 690), f"+{f['diff'] * 100:.0f} points (95% CI {f['ci_low'] * 100:.0f} to {f['ci_high'] * 100:.0f})",
               font=font("Bold", 26), fill=mix(INK, PAPER, e))
        footer(d)
        out.append(im)
    return out


def scene_end(n=36):
    out = []
    for i in range(n):
        im, d = frame(NAVY)
        a = ease(i / 8)
        d.text((60, 150), "Now or later:", font=font("ExtraBold", 50), fill=mix(WHITE, NAVY, a))
        d.text((60, 212), "theory vs machine learning", font=font("ExtraBold", 46), fill=mix(WHITE, NAVY, a))
        items = ["4 choice models, out-of-sample completeness", "Empirical Bayes vs gradient boosting", "Framing and magnitude effects",
                 "NLP pilot, literature review, paper draft", "Python, with an R replication in CI"]
        for k, t in enumerate(items):
            b = ease((i - 4 - k * 2) / 5)
            d.ellipse((62, 324 + k * 46, 74, 336 + k * 46), fill=mix(YELLOW, NAVY, b))
            d.text((92, 330 + k * 46), t, font=font("Medium", 25), fill=mix((215, 215, 215), NAVY, b), anchor="lm")
        e = ease((i - 16) / 6)
        d.text((60, 640), "Code and Colab notebooks:", font=font("Medium", 22), fill=mix((200, 200, 200), NAVY, e))
        d.text((60, 676), "github.com/mohammedelsayed741996-blip/", font=font("Bold", 25), fill=mix(YELLOW, NAVY, e))
        d.text((60, 710), "berlin-data-portfolio", font=font("Bold", 25), fill=mix(YELLOW, NAVY, e))
        out.append(im)
    return out


def main():
    s = json.loads((ROOT / "outputs" / "summary.json").read_text())
    frames = scene_question() + scene_models(s) + scene_twist(s) + scene_framing(s) + scene_end()
    path = ROOT / "outputs" / "figures" / "linkedin_post.gif"
    pal = [f.convert("P", palette=Image.ADAPTIVE, colors=64) for f in frames]
    pal[0].save(path, save_all=True, append_images=pal[1:], duration=90, loop=0, optimize=True, disposal=1)
    print(f"{path} {len(frames)} frames, {path.stat().st_size / 1e6:.2f} MB")


if __name__ == "__main__":
    main()
