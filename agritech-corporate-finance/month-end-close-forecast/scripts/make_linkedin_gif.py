"""Animated summary of the project for a LinkedIn post (outputs/figures/linkedin_post.gif).

Numbers come from the pipeline run, so the animation cannot drift from the README.
Run from the project folder:  PYTHONPATH=src python scripts/make_linkedin_gif.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from close_forecast import config as C, pipeline, reporting

W = H = 800
FONT_DIR = Path("/usr/share/fonts/opentype/inter")
NAVY, INK, PAPER, MUTED, GRID = (16, 30, 58), (11, 11, 11), (252, 252, 251), (82, 81, 78), (228, 227, 223)
BLUE, ORANGE, GREEN, YELLOW, GREY = (42, 120, 214), (235, 104, 52), (27, 175, 122), (237, 161, 0), (155, 154, 149)
RED = (227, 73, 72)


def font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    path = FONT_DIR / f"Inter-{weight}.otf"
    return ImageFont.truetype(str(path if path.exists() else "DejaVuSans.ttf"), size)


def text(d, xy, s, f, fill=INK, anchor="la"):
    d.text(xy, s, font=f, fill=fill, anchor=anchor)


def ease(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


def frame(bg=PAPER):
    im = Image.new("RGB", (W, H), bg)
    return im, ImageDraw.Draw(im)


def footer(d, light=False):
    c = (180, 190, 210) if light else MUTED
    text(d, (40, H - 40), "Synthetic data · github.com/mohammedelsayed741996-blip", font("Medium", 17), c, "ls")


def scene_title(n=22):
    out = []
    for i in range(n):
        im, d = frame(NAVY)
        a = ease(i / 8)
        y = 250 - 20 * (1 - a)
        col = tuple(int(255 * a + NAVY[k] * (1 - a)) for k in range(3))
        text(d, (60, y), "I closed the books of", font("ExtraBold", 54), col)
        text(d, (60, y + 68), "a company that", font("ExtraBold", 54), col)
        text(d, (60, y + 136), "doesn't exist.", font("ExtraBold", 54), tuple(int(c * a + NAVY[k] * (1 - a)) for k, c in enumerate(YELLOW)))
        b = ease((i - 8) / 8)
        sub = tuple(int(200 * b + NAVY[k] * (1 - b)) for k in range(3))
        text(d, (60, y + 240), "September 2026 · 3 entities · 31,800 ledger lines", font("Medium", 24), sub)
        text(d, (60, y + 276), "Month-end close and a 3+9 forecast, built in Python", font("Medium", 24), sub)
        footer(d, light=True)
        out.append(im)
    return out


def scene_checks(checklist, per=3, hold=14):
    rows = checklist[["check_id", "check", "status"]].values.tolist()
    short = {"C01": "Documents balance", "C02": "Blocked cost centers", "C03": "Cost center in right company",
             "C04": "Expense has cost center", "C05": "Duplicate invoices", "C06": "Cut-off, working day 3",
             "C07": "Recurring postings", "C08": "Intercompany agrees", "C09": "GR/IR older than 60 days",
             "C10": "Suspense account zero", "C11": "Billing = ledger", "C12": "Capex within 110%"}
    chip = {"FAIL": (RED, "FAIL"), "WARN": (YELLOW, "WARN"), "PASS": (GREEN, "PASS")}
    out = []
    total = len(rows) * per + hold
    for i in range(total):
        im, d = frame()
        text(d, (40, 48), "12 close checks", font("ExtraBold", 40))
        shown = min(len(rows), i // per + 1)
        found = sum(1 for r in rows[:shown] if r[2] != "PASS")
        found = min(found, 11)
        text(d, (W - 40, 52), f"{found}/11", font("ExtraBold", 40), RED if found < 11 else GREEN, "ra")
        text(d, (W - 40, 100), "planted errors found", font("Medium", 18), MUTED, "ra")
        for k, (cid, _, status) in enumerate(rows[:shown]):
            y = 140 + k * 49
            a = ease((i - k * per) / per)
            x0 = 40 + int(30 * (1 - a))
            d.rounded_rectangle((x0, y, W - 40, y + 41), 8, fill=(244, 243, 240))
            text(d, (x0 + 16, y + 21), cid, font("Bold", 19), MUTED, "lm")
            text(d, (x0 + 76, y + 21), short[cid], font("SemiBold", 21), INK, "lm")
            c, label = chip[status]
            d.rounded_rectangle((W - 140, y + 7, W - 54, y + 34), 13, fill=c)
            text(d, (W - 97, y + 21), label, font("Bold", 16), (255, 255, 255), "mm")
        if i >= len(rows) * per:
            text(d, (40, H - 74), "…and a month nobody touched passes all 12.", font("SemiBold", 22), GREEN)
        footer(d)
        out.append(im)
    return out


def scene_bridge(bridge, n=30, hold=12):
    steps = bridge.to_dict("records")
    levels, run = [], 0.0
    for s in steps:
        run = s["value"] if s["kind"] == "total" else run + s["value"]
        levels.append(run)
    lo, hi = min(levels) - 0.6e6, max(levels) + 0.4e6
    top, bottom = 190, 640
    y = lambda v: bottom - (v - lo) / (hi - lo) * (bottom - top)  # noqa: E731
    out = []
    labels = {"Budget EBIT": "Budget", "Actual EBIT": "Actual", "Cost of sales": "COGS"}
    for i in range(n + hold):
        im, d = frame()
        text(d, (40, 48), "Why Q1 missed plan", font("ExtraBold", 40))
        text(d, (40, 104), "EBIT Jul–Sep, budget → actual, EUR", font("Medium", 20), MUTED)
        run = 0.0
        bw = (W - 80) / len(steps)
        for k, s in enumerate(steps):
            a = ease((i - k * 2.5) / 6)
            x0, x1 = 40 + k * bw + 8, 40 + (k + 1) * bw - 8
            if s["kind"] == "total":
                y0, y1 = y(s["value"]), bottom
                col, run = GREY, s["value"]
                lab = f"{s['value'] / 1e6:,.1f}m"
            else:
                a0, a1 = run, run + s["value"]
                y0, y1 = sorted([y(a0), y(a1)])
                col = BLUE if s["value"] >= 0 else ORANGE
                run = a1
                lab = f"{s['value'] / 1e6:+.2f}m"
            if a > 0:
                yy0 = y1 - (y1 - y0) * a
                d.rectangle((x0, yy0, x1, y1), fill=col)
                if a > 0.95:
                    text(d, ((x0 + x1) / 2, yy0 - 8), lab, font("Bold", 15), INK, "ms")
            text(d, ((x0 + x1) / 2, bottom + 22), labels.get(s["step"], s["step"]), font("Medium", 15), MUTED, "mm")
        if i > n - 6:
            text(d, (40, 700), "Cereal seed volume −16% after a dry autumn.", font("SemiBold", 22), ORANGE)
            text(d, (40, 732), "Price +4% only made up part of it.", font("Medium", 20), MUTED)
        footer(d)
        out.append(im)
    return out


def scene_backtest(bt, n=22, hold=16):
    avg = bt.groupby("method")["wape"].mean() * 100
    order = [("run_rate", "Run rate"), ("seasonal", "Last year x trend"), ("budget", "Budget"), ("driver", "Driver based")]
    vmax = max(avg) * 1.1
    out = []
    for i in range(n + hold):
        im, d = frame()
        text(d, (40, 48), "Which forecast method?", font("ExtraBold", 40))
        text(d, (40, 104), "Tested on last year. Error on the remaining months, %", font("Medium", 20), MUTED)
        for k, (m, name) in enumerate(order):
            yy = 200 + k * 110
            a = ease((i - k * 3) / 8)
            wbar = (W - 300) * avg[m] / vmax * a
            col = GREEN if m == "driver" else (ORANGE if m == "run_rate" else GREY)
            text(d, (40, yy), name, font("SemiBold", 24), INK)
            d.rounded_rectangle((40, yy + 38, 40 + max(wbar, 2), yy + 78), 6, fill=col)
            if a > 0.9:
                text(d, (52 + wbar, yy + 58), f"{avg[m]:.1f}%", font("Bold", 22), INK, "lm")
        if i > n - 4:
            text(d, (40, 690), "The winner builds the 3+9 forecast", font("SemiBold", 22), GREEN)
            text(d, (40, 722), "for functional costs and capex.", font("SemiBold", 22), GREEN)
        footer(d)
        out.append(im)
    return out


def scene_end(n=36):
    out = []
    for i in range(n):
        im, d = frame(NAVY)
        a = ease(i / 8)
        c = tuple(int(255 * a + NAVY[k] * (1 - a)) for k in range(3))
        text(d, (60, 170), "Month-end close", font("ExtraBold", 50), c)
        text(d, (60, 232), "+ rolling forecast", font("ExtraBold", 50), c)
        items = ["12 checks, proposed correcting entries", "Budget vs actual down to cost center",
                 "Backtested 3+9 forecast and capex EAC", "Excel pack with live formulas + Power BI", "34 tests in GitHub Actions"]
        for k, s in enumerate(items):
            b = ease((i - 4 - k * 2) / 5)
            cc = tuple(int(215 * b + NAVY[j] * (1 - b)) for j in range(3))
            d.ellipse((62, 344 + k * 46, 74, 356 + k * 46), fill=tuple(int(YELLOW[j] * b + NAVY[j] * (1 - b)) for j in range(3)))
            text(d, (92, 350 + k * 46), s, font("Medium", 25), cc, "lm")
        e = ease((i - 16) / 6)
        cc = tuple(int(YELLOW[j] * e + NAVY[j] * (1 - e)) for j in range(3))
        text(d, (60, 640), "Code, notebooks and Excel:", font("Medium", 22), tuple(int(200 * e + NAVY[j] * (1 - e)) for j in range(3)))
        text(d, (60, 676), "github.com/mohammedelsayed741996-blip/", font("Bold", 25), cc)
        text(d, (60, 710), "berlin-data-portfolio", font("Bold", 25), cc)
        out.append(im)
    return out


def main() -> None:
    r = pipeline.run(pipeline.load_tables())
    frames = (scene_title() + scene_checks(r.checklist) + scene_bridge(reporting.ebit_bridge(r.pvm, r.income_statement))
              + scene_backtest(r.backtest) + scene_end())
    path = C.Paths().figures / "linkedin_post.gif"
    pal = [f.convert("P", palette=Image.ADAPTIVE, colors=64) for f in frames]
    pal[0].save(path, save_all=True, append_images=pal[1:], duration=90, loop=0, optimize=True, disposal=1)
    print(f"{path} {len(frames)} frames, {path.stat().st_size / 1e6:.2f} MB")


if __name__ == "__main__":
    main()
