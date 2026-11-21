"""Animated summary for a LinkedIn post (outputs/figures/linkedin_post.gif).

The chat scenes show real answers from the assistant; the numbers come from outputs/eval.json.
Run from the project folder:  PYTHONPATH=src python scripts/make_linkedin_gif.py
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from hrrag.answer import Assistant
from hrrag.config import ROOT, Settings
from hrrag.corpus import load
from hrrag.privacy import redact
from hrrag.retrieval import Retriever

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
    d.text((40, H - 40), "Fictional company · github.com/mohammedelsayed741996-blip", font=font("Medium", 17),
           fill=(180, 190, 210) if light else MUTED, anchor="ls")


def bubble(d, x, y, w, text, fill, f, color=INK, width=40):
    lines = textwrap.wrap(text, width)
    h = 24 + 30 * len(lines)
    d.rounded_rectangle((x, y, x + w, y + h), 16, fill=fill)
    for i, ln in enumerate(lines):
        d.text((x + 18, y + 14 + 30 * i), ln, font=f, fill=color)
    return y + h


def scene_title(n=26):
    out = []
    for i in range(n):
        im, d = frame(NAVY)
        a = ease(i / 8)
        d.text((60, 230), "I built an HR assistant", font=font("ExtraBold", 48), fill=mix(WHITE, NAVY, a))
        d.text((60, 292), "that knows when to say", font=font("ExtraBold", 48), fill=mix(WHITE, NAVY, a))
        d.text((60, 354), "\"I don't know\".", font=font("ExtraBold", 48), fill=mix(YELLOW, NAVY, a))
        b = ease((i - 10) / 8)
        d.text((60, 470), "Answers from the policies, with the source.", font=font("Medium", 25), fill=mix((200, 205, 215), NAVY, b))
        d.text((60, 506), "Nothing else.", font=font("Medium", 25), fill=mix((200, 205, 215), NAVY, b))
        footer(d, light=True)
        out.append(im)
    return out


def scene_chat(title, q, ans, role_label, n=46, declined=False):
    out = []
    shown_q = ""
    for i in range(n):
        im, d = frame()
        d.text((40, 44), title, font=font("ExtraBold", 34), fill=INK)
        d.rounded_rectangle((40, 100, 40 + 22 + d.textlength(role_label, font=font("SemiBold", 18)), 132), 10, fill=CARD)
        d.text((51, 116), role_label, font=font("SemiBold", 18), fill=MUTED, anchor="lm")
        k = min(len(q), int(len(q) * (i / 14)))
        y = bubble(d, 230, 170, 530, q[:k] + ("|" if k < len(q) else ""), USER, font("Medium", 23), width=34)
        a = ease((i - 18) / 8)
        if a > 0:
            fill = mix(AMBER if declined else WHITE, PAPER, a)
            d.rounded_rectangle((40, y + 24, 640, y + 24 + 34 + 30 * len(textwrap.wrap(ans["text"], 42)) + (64 if ans["src"] else 0)), 16,
                                fill=fill, outline=mix(LINE, PAPER, a), width=2)
            for j, ln in enumerate(textwrap.wrap(ans["text"], 42)):
                d.text((60, y + 42 + 30 * j), ln, font=font("Medium", 23), fill=mix(INK, PAPER, a))
            if ans["src"]:
                yy = y + 46 + 30 * len(textwrap.wrap(ans["text"], 42))
                d.text((60, yy), "Source: " + ans["src"], font=font("SemiBold", 18), fill=mix(BLUE, PAPER, a))
                d.text((60, yy + 26), ans["ver"], font=font("Medium", 16), fill=mix(MUTED, PAPER, a))
        footer(d)
        out.append(im)
    return out


def scene_redact(n=40):
    raw = "Hi, I'm Lena Fischer (E-204871). How long can I take Elternzeit?"
    red, _ = redact(raw)
    out = []
    for i in range(n):
        im, d = frame()
        d.text((40, 44), "Personal data stays out", font=font("ExtraBold", 36), fill=INK)
        d.text((40, 98), "Removed before the question is answered or logged", font=font("Medium", 21), fill=MUTED)
        bubble(d, 40, 170, 720, raw, USER, font("Medium", 24), width=48)
        a = ease((i - 12) / 10)
        d.text((40, 300), "What gets stored:", font=font("SemiBold", 22), fill=mix(MUTED, PAPER, a))
        bubble(d, 40, 340, 720, red, mix(CARD, PAPER, a), font("Medium", 24), color=mix(INK, PAPER, a), width=48)
        b = ease((i - 22) / 8)
        for k, t in enumerate(["No user ID, only the role", "Deleted after 90 days", "Restricted documents never retrieved for the wrong role"]):
            d.ellipse((44, 492 + k * 46, 58, 506 + k * 46), fill=mix(GREEN, PAPER, b))
            d.text((74, 499 + k * 46), t, font=font("Medium", 23), fill=mix(INK, PAPER, b), anchor="lm")
        footer(d)
        out.append(im)
    return out


def scene_results(t, n=50):
    rows = [("Right answer, with the right source", t["answer_correct"], BLUE), ("Right source in the top 3", t["hit_at_3"], BLUE),
            ("Off-topic and restricted questions declined", t["decline_rate_when_should"], GREEN)]
    out = []
    for i in range(n):
        im, d = frame()
        d.text((40, 44), "Tested on questions it", font=font("ExtraBold", 36), fill=INK)
        d.text((40, 90), "had never seen", font=font("ExtraBold", 36), fill=INK)
        d.text((40, 146), "45 held-out questions, written the way employees ask", font=font("Medium", 20), fill=MUTED)
        X0, X1 = 40, 620
        for k, (lab, v, col) in enumerate(rows):
            y = 210 + k * 110
            a = ease((i - k * 5) / 12)
            d.text((X0, y), lab, font=font("SemiBold", 23), fill=INK)
            d.rounded_rectangle((X0, y + 36, X1, y + 76), 8, fill=CARD)
            w = int((X1 - X0) * v * a)
            if w > 8:
                d.rounded_rectangle((X0, y + 36, X0 + w, y + 76), 8, fill=col)
            d.text((X1 + 16, y + 56), f"{v * a:.0%}", font=font("ExtraBold", 30), fill=col, anchor="lm")
        e = ease((i - 24) / 8)
        d.text((40, 560), f"{t['leaks']} leaks of manager or HR documents", font=font("ExtraBold", 30), fill=mix(GREEN, PAPER, e))
        d.text((40, 606), "CI blocks a release if any of these slip", font=font("Medium", 23), fill=mix(MUTED, PAPER, e))
        footer(d)
        out.append(im)
    return out


def scene_ship(n=44):
    steps = ["37 tests, incl. PostgreSQL", "Quality gate on held-out questions", "TypeScript type check", "Docker image built",
             "Container answers a real question"]
    out = []
    for i in range(n):
        im, d = frame()
        d.text((40, 44), "And it ships", font=font("ExtraBold", 40), fill=INK)
        d.text((40, 100), "Every push to GitHub runs:", font=font("Medium", 22), fill=MUTED)
        for k, s in enumerate(steps):
            a = ease((i - 4 - k * 4) / 5)
            y = 180 + k * 82
            d.rounded_rectangle((40, y, 760, y + 64), 12, fill=mix(CARD, PAPER, a))
            d.ellipse((60, y + 18, 88, y + 46), fill=mix(GREEN, PAPER, a))
            d.text((74, y + 32), "✓", font=font("Bold", 20), fill=mix(WHITE, PAPER, a), anchor="mm")
            d.text((108, y + 32), s, font=font("SemiBold", 24), fill=mix(INK, PAPER, a), anchor="lm")
        footer(d)
        out.append(im)
    return out


def scene_end(n=36):
    out = []
    for i in range(n):
        im, d = frame(NAVY)
        a = ease(i / 8)
        d.text((60, 150), "HR policy assistant", font=font("ExtraBold", 50), fill=mix(WHITE, NAVY, a))
        items = ["Answers with the source, or says it doesn't know", "Role-based access before retrieval", "Personal data removed before logging",
                 "Optional LLM, only allowed to cite what it was given", "Docker · PostgreSQL · Kubernetes · CI/CD"]
        for k, t in enumerate(items):
            b = ease((i - 4 - k * 2) / 5)
            d.ellipse((62, 264 + k * 50, 74, 276 + k * 50), fill=mix(YELLOW, NAVY, b))
            d.text((92, 270 + k * 50), t, font=font("Medium", 24), fill=mix((215, 215, 215), NAVY, b), anchor="lm")
        e = ease((i - 16) / 6)
        d.text((60, 640), "Code and Colab notebooks:", font=font("Medium", 22), fill=mix((200, 200, 200), NAVY, e))
        d.text((60, 676), "github.com/mohammedelsayed741996-blip/", font=font("Bold", 25), fill=mix(YELLOW, NAVY, e))
        d.text((60, 710), "berlin-data-portfolio", font=font("Bold", 25), fill=mix(YELLOW, NAVY, e))
        out.append(im)
    return out


def real(assistant, q, role):
    a = assistant.ask(q, role=role)
    text = a.text.split(" [")[0] if a.answered else "I could not find this in the HR policies you have access to. Please ask HR."
    if a.answered and not text.endswith("."):
        text += "."
    src = f"{a.citations[0]['policy_id']} · {a.citations[0]['section']}" if a.citations else ""
    ver = f"version {a.citations[0]['version']}, valid from {a.citations[0]['effective_date']}" if a.citations else ""
    return {"text": text, "src": src, "ver": ver}


def main():
    assistant = Assistant(Retriever(load(ROOT / "policies")), Settings())
    t = json.loads((ROOT / "outputs" / "eval.json").read_text())["test"]
    frames = (scene_title()
              + scene_chat("Ask it like you'd ask a colleague", "How long can I take Elternzeit?",
                           real(assistant, "How long can I take Elternzeit?", "employee"), "Signed in as: employee")
              + scene_chat("Same question, different person", "What is the merit budget for 2026?",
                           real(assistant, "What is the merit budget for 2026?", "employee"), "Signed in as: employee", declined=True)
              + scene_chat("Same question, different person", "What is the merit budget for 2026?",
                           real(assistant, "What is the merit budget for 2026?", "hr"), "Signed in as: HR")
              + scene_redact() + scene_results(t) + scene_ship() + scene_end())
    path = ROOT / "outputs" / "figures" / "linkedin_post.gif"
    pal = [f.convert("P", palette=Image.ADAPTIVE, colors=64) for f in frames]
    pal[0].save(path, save_all=True, append_images=pal[1:], duration=90, loop=0, optimize=True, disposal=1)
    print(f"{path} {len(frames)} frames, {path.stat().st_size / 1e6:.2f} MB")


if __name__ == "__main__":
    main()
