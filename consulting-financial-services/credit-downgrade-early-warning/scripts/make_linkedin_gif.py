"""Animated summary for a LinkedIn post (outputs/figures/linkedin_post.gif).

Numbers and headlines come from the pipeline run, so the animation matches the README.
Run from the project folder:  PYTHONPATH=src python scripts/make_linkedin_gif.py
"""

from __future__ import annotations

import warnings
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from downgrade_ews import config as C, pipeline

warnings.filterwarnings("ignore")
W = H = 800
FONT_DIR = Path("/usr/share/fonts/opentype/inter")
NAVY, INK, PAPER, MUTED = (16, 30, 58), (11, 11, 11), (252, 252, 251), (82, 81, 78)
BLUE, ORANGE, GREEN, YELLOW, GREY, RED = (42, 120, 214), (235, 104, 52), (27, 175, 122), (237, 161, 0), (155, 154, 149), (227, 73, 72)


def font(weight: str, size: int):
    p = FONT_DIR / f"Inter-{weight}.otf"
    return ImageFont.truetype(str(p if p.exists() else "DejaVuSans.ttf"), size)


def ease(x: float) -> float:
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


def wrap(d, text, f, width):
    words, lines, cur = text.split(), [], ""
    for w in words:
        test = (cur + " " + w).strip()
        if d.textlength(test, font=f) <= width:
            cur = test
        else:
            lines.append(cur)
            cur = w
    return lines + [cur]


def scene_title(n=24):
    out = []
    for i in range(n):
        im, d = frame(NAVY)
        a = ease(i / 8)
        for k, line in enumerate(["Can the news warn you", "before the rating", "agency does?"]):
            d.text((60, 220 + k * 66), line, font=font("ExtraBold", 54), fill=mix((255, 255, 255) if k < 2 else YELLOW, NAVY, a))
        b = ease((i - 9) / 8)
        d.text((60, 460), "360 issuers · 66,000 articles in English and German", font=font("Medium", 24), fill=mix((200, 205, 215), NAVY, b))
        d.text((60, 496), "A credit early-warning model, built in Python", font=font("Medium", 24), fill=mix((200, 205, 215), NAVY, b))
        footer(d, light=True)
        out.append(im)
    return out


def scene_headlines(heads, per=4, hold=16):
    out = []
    total = len(heads) * per + hold
    for i in range(total):
        im, d = frame()
        d.text((40, 48), "Reading the news", font=font("ExtraBold", 40), fill=INK)
        d.text((40, 102), "Helyn Retail SA, Aug to Sep 2025. Rating BB+, outlook stable.", font=font("Medium", 19), fill=MUTED)
        shown = min(len(heads), i // per + 1)
        for k, (date, lang, head, p) in enumerate(heads[:shown]):
            y = 150 + k * 66
            a = ease((i - k * per) / per)
            col = RED if p >= 0.7 else (ORANGE if p >= 0.55 else GREY)
            d.rounded_rectangle((40, y, W - 40, y + 56), 10, fill=(244, 243, 240))
            d.rounded_rectangle((40, y, 48, y + 56), 4, fill=col)
            line = wrap(d, head.replace("Helyn Retail SA", "Helyn"), font("SemiBold", 18), W - 250)[0]
            d.text((62, y + 10), line, font=font("SemiBold", 18), fill=mix(INK, (244, 243, 240), a))
            d.text((62, y + 34), f"{date} · {lang.upper()}", font=font("Medium", 14), fill=MUTED)
            bw = int(80 * p * a)
            d.rounded_rectangle((W - 160, y + 20, W - 160 + bw, y + 36), 6, fill=col)
            d.text((W - 54, y + 28), f"{p:.2f}", font=font("Bold", 16), fill=INK, anchor="rm")
        if i >= len(heads) * per:
            d.text((40, H - 120), "The score crosses the alert line in September.", font=font("SemiBold", 22), fill=RED)
        footer(d)
        out.append(im)
    return out


def scene_timeline(n=34):
    events = [("Sep 2025", "Model alert", RED), ("Dec 2025", "Agency: outlook negative", YELLOW), ("Jan 2026", "Downgrade BB+ → BB", INK)]
    out = []
    for i in range(n):
        im, d = frame()
        d.text((40, 48), "Four months early", font=font("ExtraBold", 40), fill=INK)
        d.text((40, 102), "Same issuer, what happened next", font=font("Medium", 20), fill=MUTED)
        x0, x1, y = 90, W - 90, 330
        a = ease(i / 10)
        d.line((x0, y, x0 + (x1 - x0) * a, y), fill=GREY, width=4)
        xs = [x0 + 30, x0 + (x1 - x0) * 0.55, x1 - 40]
        for k, ((when, what, col), x) in enumerate(zip(events, xs)):
            b = ease((i - 6 - k * 6) / 5)
            if b <= 0:
                continue
            r = 14 * b
            d.ellipse((x - r, y - r, x + r, y + r), fill=col)
            d.text((x, y - 40), when, font=font("Bold", 22), fill=mix(INK, PAPER, b), anchor="ms")
            for j, line in enumerate(wrap(d, what, font("SemiBold", 20), 190)):
                d.text((x, y + 48 + j * 26), line, font=font("SemiBold", 20), fill=mix(col if col != INK else INK, PAPER, b), anchor="ms")
        if i > 26:
            d.text((40, 560), "The covenant waiver request, the credit line", font=font("Medium", 22), fill=MUTED)
            d.text((40, 592), "draw and the CFO exit were all in the news", font=font("Medium", 22), fill=MUTED)
            d.text((40, 624), "before the agency moved.", font=font("Medium", 22), fill=MUTED)
        footer(d)
        out.append(im)
    return out


def scene_results(ev, n=24, hold=16):
    rows = [("Negative outlook rule", "Outlook only", GREY), ("Ratings + financials", "Ratings + financials", YELLOW),
            ("+ keyword list", "+ keyword rules", ORANGE), ("+ NLP news model", "+ NLP news scores", BLUE)]
    e = ev.set_index("model")
    out = []
    for i in range(n + hold):
        im, d = frame()
        d.text((40, 48), "Alerts that were right", font=font("ExtraBold", 40), fill=INK)
        d.text((40, 102), "Out-of-time test, Jul 2025 to Jun 2026. Base rate 3.9%.", font=font("Medium", 19), fill=MUTED)
        for k, (label, key, col) in enumerate(rows):
            y = 180 + k * 112
            a = ease((i - k * 3) / 8)
            v = e.loc[key, "alert_precision"]
            per = e.loc[key, "alerts_per_month"]
            d.text((40, y), label, font=font("SemiBold", 23), fill=INK)
            d.text((W - 40, y + 4), f"{per:.0f} alerts/month", font=font("Medium", 17), fill=MUTED, anchor="ra")
            wbar = (W - 220) * v / 0.35 * a
            d.rounded_rectangle((40, y + 36, 40 + max(wbar, 2), y + 76), 6, fill=col)
            if a > 0.9:
                d.text((52 + wbar, y + 56), f"{v:.0%}", font=font("Bold", 22), fill=INK, anchor="lm")
        if i > n - 4:
            d.text((40, 650), "More downgrades caught than the outlook rule,", font=font("SemiBold", 21), fill=BLUE)
            d.text((40, 680), "with less than half the review work.", font=font("SemiBold", 21), fill=BLUE)
        footer(d)
        out.append(im)
    return out


def scene_lesson(n=40):
    out = []
    for i in range(n):
        im, d = frame()
        d.text((40, 48), "The bug I almost shipped", font=font("ExtraBold", 40), fill=INK)
        a = ease(i / 8)
        d.text((40, 130), "Top words, first version:", font=font("SemiBold", 22), fill=mix(MUTED, PAPER, a))
        for k, w in enumerate(["transport", "utilities", "automotive"]):
            b = ease((i - 3 - k * 2) / 5)
            x = 40 + k * 190
            d.rounded_rectangle((x, 175, x + 170, 235), 12, fill=mix(RED, PAPER, b))
            d.text((x + 85, 205), w, font=font("Bold", 26), fill=mix((255, 255, 255), PAPER, b), anchor="mm")
        c = ease((i - 14) / 8)
        for k, line in enumerate(["It had learned the calendar, not the language:",
                                  "sector crises lined up with downgrades.",
                                  "Masked sectors, quarters and numbers.",
                                  "Then tested it like a bank's chatbot."]):
            d.text((40, 300 + k * 40), line, font=font("Medium" if k < 2 else "SemiBold", 24), fill=mix(INK if k < 2 else GREEN, PAPER, c))
        e = ease((i - 22) / 8)
        d.text((40, 500), "Top words now:", font=font("SemiBold", 22), fill=mix(MUTED, PAPER, e))
        for k, w in enumerate(["cash", "to negative", "auf negativ"]):
            x = 40 + k * 230
            d.rounded_rectangle((x, 545, x + 210, 605), 12, fill=mix(GREEN, PAPER, e))
            d.text((x + 105, 575), w, font=font("Bold", 24), fill=mix((255, 255, 255), PAPER, e), anchor="mm")
        footer(d)
        out.append(im)
    return out


def scene_end(n=38):
    out = []
    for i in range(n):
        im, d = frame(NAVY)
        a = ease(i / 8)
        d.text((60, 160), "Credit downgrade", font=font("ExtraBold", 50), fill=mix((255, 255, 255), NAVY, a))
        d.text((60, 222), "early warning", font=font("ExtraBold", 50), fill=mix((255, 255, 255), NAVY, a))
        items = ["NLP on English and German news", "Compared with what banks use today",
                 "Behavioural tests + model card", "Monthly watchlist with the evidence", "23 tests in GitHub Actions"]
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


def main() -> None:
    r = pipeline.run(pipeline.load_tables())
    iss = pipeline.story_issuer(r)
    s = r.scored[(r.scored["issuer_id"] == iss) & (r.scored["date"].between("2025-08", "2025-09-31"))]
    pick = s[s["p_article"] > 0.6].sort_values("date").tail(7)
    heads = list(zip(pick["date"], pick["language"], pick["headline"], pick["p_article"]))
    frames = scene_title() + scene_headlines(heads) + scene_timeline() + scene_results(r.evaluation) + scene_lesson() + scene_end()
    path = C.Paths().figures / "linkedin_post.gif"
    pal = [f.convert("P", palette=Image.ADAPTIVE, colors=64) for f in frames]
    pal[0].save(path, save_all=True, append_images=pal[1:], duration=90, loop=0, optimize=True, disposal=1)
    print(f"{path} {len(frames)} frames, {path.stat().st_size / 1e6:.2f} MB, story issuer {iss}")


if __name__ == "__main__":
    main()
