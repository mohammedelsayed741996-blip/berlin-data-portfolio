"""Animated summary for a LinkedIn post (outputs/figures/linkedin_post.gif).

The chat scenes show real answers from the agent; the numbers come from outputs/eval.json.
Run from the project folder:  PYTHONPATH=src python scripts/make_linkedin_gif.py
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from agentlake.agent import Agent
from agentlake.config import ROOT
from agentlake.tools import User

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
    d.text((40, H - 40), "Synthetic data · github.com/mohammedelsayed741996-blip", font=font("Medium", 17),
           fill=(180, 190, 210) if light else MUTED, anchor="ls")


def bubble(d, x, y, w, text, fill, f, color=INK, width=40):
    lines = textwrap.wrap(text, width)
    h = 24 + 30 * len(lines)
    d.rounded_rectangle((x, y, x + w, y + h), 16, fill=fill)
    for i, ln in enumerate(lines):
        d.text((x + 18, y + 14 + 30 * i), ln, font=f, fill=color)
    return y + h



def scene_title(n=28):
    out = []
    for i in range(n):
        im, d = frame(NAVY)
        a = ease(i / 8)
        for k, (txt, col) in enumerate([("An AI agent on company data", WHITE), ("where the model proposes", WHITE), ("and the code decides.", YELLOW)]):
            d.text((60, 220 + 62 * k), txt, font=font("ExtraBold", 46), fill=mix(col, NAVY, a))
        b = ease((i - 10) / 8)
        d.text((60, 460), "A Finance assistant on a lakehouse, with access", font=font("Medium", 25), fill=mix((200, 205, 215), NAVY, b))
        d.text((60, 496), "control, approvals and a red team in CI.", font=font("Medium", 25), fill=mix((200, 205, 215), NAVY, b))
        footer(d, light=True)
        out.append(im)
    return out


def scene_chat(title, q, ans, role_label, n=46, declined=False):
    out = []
    for i in range(n):
        im, d = frame()
        d.text((40, 44), title, font=font("ExtraBold", 34), fill=INK)
        d.rounded_rectangle((40, 100, 40 + 22 + d.textlength(role_label, font=font("SemiBold", 18)), 132), 10, fill=CARD)
        d.text((51, 116), role_label, font=font("SemiBold", 18), fill=MUTED, anchor="lm")
        k = min(len(q), int(len(q) * (i / 14)))
        y = bubble(d, 230, 170, 530, q[:k] + ("|" if k < len(q) else ""), USER, font("Medium", 23), width=34)
        a = ease((i - 18) / 8)
        if a > 0:
            lines = textwrap.wrap(ans, 44)
            d.rounded_rectangle((40, y + 24, 660, y + 24 + 34 + 30 * len(lines)), 16,
                                fill=mix(AMBER if declined else WHITE, PAPER, a), outline=mix(LINE, PAPER, a), width=2)
            for j, ln in enumerate(lines):
                d.text((60, y + 42 + 30 * j), ln, font=font("Medium", 23), fill=mix(INK, PAPER, a))
        footer(d)
        out.append(im)
    return out


def scene_approval(n=46):
    out = []
    rows = [("Account manager drafts a reminder", "request created, nothing sent", BLUE),
            ("Finance tries to approve a credit hold", "refused: Head of Finance only", ORANGE),
            ("Head of Finance approves", "approved, with name and time", GREEN)]
    for i in range(n):
        im, d = frame()
        d.text((40, 44), "Actions wait for a person", font=font("ExtraBold", 36), fill=INK)
        d.text((40, 98), "The agent has no tool that sends or changes anything", font=font("Medium", 21), fill=MUTED)
        for k, (a_, b_, col) in enumerate(rows):
            a = ease((i - 4 - k * 8) / 8)
            y = 180 + k * 130
            d.rounded_rectangle((40, y, 760, y + 104), 14, fill=mix(CARD, PAPER, a))
            d.rectangle((40, y, 48, y + 104), fill=mix(col, PAPER, a))
            d.text((70, y + 22), a_, font=font("SemiBold", 25), fill=mix(INK, PAPER, a))
            d.text((70, y + 62), b_, font=font("Medium", 22), fill=mix(col, PAPER, a))
        e = ease((i - 30) / 8)
        d.text((40, 610), "Four-eyes rule: whoever proposes a credit", font=font("Medium", 23), fill=mix(MUTED, PAPER, e))
        d.text((40, 642), "hold cannot approve it.", font=font("Medium", 23), fill=mix(MUTED, PAPER, e))
        footer(d)
        out.append(im)
    return out


def scene_results(s, n=52):
    out = []
    core = round(s["task_success"] * 34)
    for i in range(n):
        im, d = frame()
        d.text((40, 44), "A red team runs on every push", font=font("ExtraBold", 36), fill=INK)
        d.text((40, 98), "A hostile planner tries 14 attacks as 3 different users", font=font("Medium", 21), fill=MUTED)
        attacks = ["free-form SQL", "send email directly", "another owner's account", "SQL injection in a filter",
                   "group by personal data", "argument smuggling", "credit hold without the role", "runaway loop"]
        for k, t in enumerate(attacks):
            a = ease((i - k * 2) / 5)
            y = 160 + k * 44
            d.text((40, y), t, font=font("Medium", 22), fill=mix(INK, PAPER, a))
            d.text((480, y), "contained", font=font("SemiBold", 22), fill=mix(GREEN, PAPER, a))
        e = ease((i - 22) / 8)
        d.text((40, 540), f"{s['red_team_runs']} runs: {s['red_team_leaks']} leaks, {s['red_team_unauthorized_actions']} unauthorised actions",
               font=font("ExtraBold", 28), fill=mix(GREEN, PAPER, e))
        f = ease((i - 30) / 8)
        d.text((40, 600), f"Core tasks: {core} of 34 pass", font=font("SemiBold", 24), fill=mix(INK, PAPER, f))
        d.text((40, 638), f"Paraphrases: {round(s['paraphrase_success'] * 6)} of 6. That gap is the model's job.", font=font("Medium", 23), fill=mix(MUTED, PAPER, f))
        footer(d)
        out.append(im)
    return out


def scene_end(n=40):
    out = []
    for i in range(n):
        im, d = frame(NAVY)
        a = ease(i / 8)
        d.text((60, 140), "Agentic lakehouse", font=font("ExtraBold", 50), fill=mix(WHITE, NAVY, a))
        items = ["Semantic layer instead of free SQL", "Row-level security in the tools, not the prompt",
                 "Human approval for every action", "Claude on Amazon Bedrock behind one interface",
                 "Terraform for AWS · 6 decision records", "Delivery plan with estimates and risks"]
        for k, t in enumerate(items):
            b = ease((i - 4 - k * 2) / 5)
            d.ellipse((62, 254 + k * 50, 74, 266 + k * 50), fill=mix(YELLOW, NAVY, b))
            d.text((92, 260 + k * 50), t, font=font("Medium", 24), fill=mix((215, 215, 215), NAVY, b), anchor="lm")
        e = ease((i - 18) / 6)
        d.text((60, 640), "Code, decisions and Colab notebooks:", font=font("Medium", 22), fill=mix((200, 200, 200), NAVY, e))
        d.text((60, 676), "github.com/mohammedelsayed741996-blip/", font=font("Bold", 25), fill=mix(YELLOW, NAVY, e))
        d.text((60, 710), "berlin-data-portfolio", font=font("Bold", 25), fill=mix(YELLOW, NAVY, e))
        out.append(im)
    return out


def main():
    agent = Agent()
    q = "What does Elbtal Maschinenbau owe us and how much is overdue?"
    own = agent.run(q, User("AM02", "account_manager")).answer
    other = agent.run(q, User("AM05", "account_manager")).answer
    s = json.loads((ROOT / "outputs" / "eval.json").read_text())
    frames = (scene_title()
              + scene_chat("Ask about your own customer", q, own, "Signed in as: account manager AM02")
              + scene_chat("Same question, another manager", q, other, "Signed in as: account manager AM05", declined=True)
              + scene_approval() + scene_results(s) + scene_end())
    path = ROOT / "outputs" / "figures" / "linkedin_post.gif"
    pal = [f.convert("P", palette=Image.ADAPTIVE, colors=64) for f in frames]
    pal[0].save(path, save_all=True, append_images=pal[1:], duration=90, loop=0, optimize=True, disposal=1)
    print(f"{path} {len(frames)} frames, {path.stat().st_size / 1e6:.2f} MB")


if __name__ == "__main__":
    main()
