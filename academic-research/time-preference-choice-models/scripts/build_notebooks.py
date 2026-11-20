"""Build and execute the project notebooks without Jupyter.

Each code cell runs in one shared namespace, like a kernel, and its printed
output, last expression and images are saved as real notebook outputs, so the
files open with results in Jupyter, on GitHub and in Google Colab.

Run from the project folder:  python scripts/build_notebooks.py
"""

from __future__ import annotations

import ast
import base64
import contextlib
import io
import json
import os
from pathlib import Path

os.environ.setdefault("MPLBACKEND", "Agg")
PROJECT = Path(__file__).resolve().parents[1]
NB_DIR = PROJECT / "notebooks"
BASE = "https://colab.research.google.com/github/mohammedelsayed741996-blip/berlin-data-portfolio/blob/main/academic-research/time-preference-choice-models/notebooks"

SETUP = '''import os, sys, subprocess, warnings
from pathlib import Path

REPO = "https://github.com/mohammedelsayed741996-blip/berlin-data-portfolio.git"
PROJECT = "academic-research/time-preference-choice-models"

if "google.colab" in sys.modules:
    if not Path("/content/berlin-data-portfolio").exists():
        subprocess.run(["git", "clone", "--depth", "1", REPO, "/content/berlin-data-portfolio"], check=True)
    os.chdir(f"/content/berlin-data-portfolio/{PROJECT}")
else:
    here = Path.cwd()
    while not (here / "src" / "timepref").exists() and here != here.parent:
        here = here.parent
    os.chdir(here)

sys.path.insert(0, str(Path.cwd() / "src"))
warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd
pd.set_option("display.max_columns", 30)
pd.set_option("display.width", 160)
pd.set_option("display.max_colwidth", 80)
from IPython.display import Image, display
print("Project folder:", Path.cwd().name)'''

LOAD = '''from timepref import config as C, data, quality as Q, models as M, evaluate as E, effects as F, nlp as N, reporting as R

if not (Path("data") / "trials.csv.gz").exists():
    data.save(data.generate(), Path("data"))
tables = data.load(Path("data"))
clean, quality_log, rules = Q.apply(tables)
print(f"{clean['pid'].nunique()} participants, {len(clean):,} choices after exclusions")'''


def md(text: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": text.strip("\n")}


def code(text: str) -> dict:
    return {"cell_type": "code", "metadata": {}, "source": text.strip("\n"), "execution_count": None, "outputs": []}


def badge(name: str) -> str:
    return f"[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)]({BASE}/{name})"


NB1 = [
    md(f"""
# 01 · The experiment and data quality

{badge("01_experiment_and_data_quality.ipynb")}

Why do people take a smaller reward now over a larger one later, and can that be shaped? This
notebook sets up a simulated online experiment that asks exactly that, and cleans its data with
rules fixed before any model is fitted.

Each participant makes 60 choices between a smaller-sooner and a larger-later amount, plus 4 catch
trials where the later option is smaller, so choosing it means the person was not reading. Half the
participants see delays ("in 30 days"), half see calendar dates ("on 21 December").

All data are simulated. Participant codes are random, and no personal data exist anywhere in the
project. Because the generating process is known, every later step can be checked against the truth.
"""),
    code(SETUP),
    code(LOAD),
    md("""
## What a participant sees

Each row is one choice. `choice_ll` is 1 when the person took the larger-later option.
"""),
    code('''tables["trials"].query("submission == 1").head(8)[
    ["pid", "trial", "frame", "ss_amount", "ss_delay", "ll_amount", "ll_delay", "catch", "choice_ll", "rt_ms"]]'''),
    md("""
## Who is in the simulated population

Four decision types, so the models can be scored against a known truth: hyperbolic, quasi-hyperbolic
and exponential discounters, and people who use the ITCH heuristic (Ericson et al. 2015) and never
discount at all. Sixteen careless responders and twelve repeat submissions were added on purpose.
A real study has no such table.
"""),
    code('''tables["truth"]["type"].value_counts()'''),
    md("""
## Pre-registered exclusion rules

The rules are fixed before any model sees the data. Both content rules are needed: the speed rule
catches every careless responder, and the catch-trial rule catches 14 of 16 plus one genuine
participant who failed two catch trials.
"""),
    code('''quality_log'''),
    code('''Q.flow(tables, rules)'''),
    code('''excluded = set(rules[1].flagged) | set(rules[2].flagged)
careless = set(tables["truth"].query("careless != 'no'")["pid"])
print("careless responders caught:", len(careless & excluded), "of", len(careless))
print("genuine participants excluded:", len(excluded - careless))'''),
    md("""
## A first look at the choices

Patience rises with the size of the premium for waiting and falls with the wait itself. The date
frame already shows a higher share of later choices before any model is fitted.
"""),
    code('''c = clean.assign(premium=pd.cut(clean["ll_amount"] / clean["ss_amount"] - 1, [0, 0.25, 0.5, 1, 1.5],
                                  labels=["up to 25%", "25-50%", "50-100%", "100-150%"]),
              wait=pd.cut(clean["ll_delay"] - clean["ss_delay"], [0, 14, 60, 180], labels=["1-2 weeks", "3-8 weeks", "3-6 months"]))
(c.pivot_table(index="premium", columns=["frame", "wait"], values="choice_ll", aggfunc="mean", observed=True) * 100).round(0)'''),
]

NB2 = [
    md(f"""
# 02 · Discounting models, a heuristic and machine learning

{badge("02_models_vs_machine_learning.ipynb")}

Four models are fitted to every participant: exponential, hyperbolic and quasi-hyperbolic
discounting, and the ITCH heuristic. Gradient boosting is trained on everyone at once. Each
participant's trials are split into four folds, so every choice is predicted by a model that never
saw it.

The yardstick is completeness (Fudenberg et al. 2022), the share of the predictable variation a model
captures. 0% means no better than the person's base rate; 100% means as good as the true choice
probability, which is known here only because the data are simulated.
"""),
    code(SETUP),
    code(LOAD),
    md("""
## Fits on all data and parameter recovery

Small weak penalties keep estimates finite for people who always pick one side. For participants who
really are hyperbolic discounters, the estimated log k tracks the true value closely.
"""),
    code('''fits = M.fit_all(clean)
h = fits.query("model == 'hyperbolic'").merge(tables["truth"].query("type == 'hyperbolic'"), on="pid")
print("correlation of true and estimated log k:", round(np.corrcoef(h["log_k"], h["theta0"])[0, 1], 3))
print("mean error:", round((h["theta0"] - h["log_k"]).mean(), 3), "(the fitted model has no magnitude effect)")
R.plot_recovery(fits, tables["truth"], Path("outputs/figures/parameter_recovery.png"))
display(Image("outputs/figures/parameter_recovery.png"))'''),
    md("""
## Can the decision type be recovered from 60 choices?

The model with the lowest BIC is compared with the true type. Heuristic users and hyperbolic
discounters are mostly recognised. Quasi-hyperbolic participants are often mistaken for the other
two discounting types: with 60 choices the models are hard to tell apart.
"""),
    code('''best = M.best_model(fits).merge(tables["truth"][["pid", "type"]], on="pid")
print("right type:", f"{(best['best'] == best['type']).mean():.0%}", "(chance 25%)")
pd.crosstab(best["type"], best["best"], rownames=["true type"], colnames=["lowest BIC"])'''),
    md("""
## Out-of-sample comparison

Cross-validation fits every model 4 times for every participant, plus empirical-Bayes refits and
an inner split for the hybrid model. It takes a few minutes, so the pipeline caches the predictions;
set `REFRESH = True` to recompute them.
"""),
    code('''REFRESH = False
cache = Path("outputs/cv_predictions.csv.gz")
if REFRESH or not cache.exists():
    E.cross_validate(clean).to_csv(cache, index=False)
cv = pd.read_csv(cache)
board = E.scoreboard(cv)
board.round(4)'''),
    code('''R.plot_completeness(board, Path("outputs/figures/completeness.png"))
display(Image("outputs/figures/completeness.png"))'''),
    md("""
## Where the machine-learning advantage comes from

Without person information, gradient boosting is the second-worst model. With each person's base
rate and fitted parameters it is the best. So the gain is mostly about pooling information across
people, not about a better rule for trading money against time. Shrinking each person's ITCH
estimates towards the population, a simple empirical-Bayes step, recovers most of the gap.
"""),
    code('''for a, b in [("itch", "hyperbolic"), ("itch_eb", "ml_person"), ("hybrid", "ml_person")]:
    d, lo, hi = E.bootstrap_ci(cv, a, b)
    print(f"{a:>10} minus {b:<10} log loss {d:+.4f}  (95% CI {lo:+.4f} to {hi:+.4f})")'''),
    md("""
## By true decision type

Discounting models capture little of what heuristic users do. For those participants, shrunk ITCH is
the best model of all, ahead of gradient boosting.
"""),
    code('''(E.by_type(cv, tables["truth"]) * 100).round(0)'''),
]

NB3 = [
    md(f"""
# 03 · Can time preferences be shaped? Framing, magnitude and a text pilot

{badge("03_framing_effect_and_text_pilot.ipynb")}

Calendar dates instead of delays (Read et al. 2005) are a cheap intervention. This notebook
estimates its effect with a permutation test and a bootstrap, checks the magnitude effect within
participants, and then pilots a second data source: everyday text about money.
"""),
    code(SETUP),
    code(LOAD + '''
fits = M.fit_all(clean, models=("hyperbolic", "quasi_hyperbolic"))
people = F.person_table(clean, fits)'''),
    md("""
## The framing effect

The outcome is each participant's fitted hyperbolic log k, plus two others: the model-free share of
later choices and the present-bias parameter beta.
"""),
    code('''framing = F.framing_effect(people)
framing.round(3)'''),
    code('''R.plot_framing(people, framing, Path("outputs/figures/framing_effect.png"))
display(Image("outputs/figures/framing_effect.png"))'''),
    md("""
The estimated drop in log k (about 0.8) is larger than the factor built into the simulation for
discounters (0.5). Heuristic users react to the frame too, and a hyperbolic fit expresses their
change as a change in k. The share of later choices does not depend on any model, which is why it
should be reported alongside k.

Does the result depend on the exclusions? Barely:
"""),
    code('''excluded = sorted(set(rules[1].flagged) | set(rules[2].flagged))
F.with_careless(tables["trials"].query("submission == 1"), None, excluded).round(3)'''),
    md("""
## The magnitude effect

Each person's k is fitted twice, once on later amounts below 70 euros and once above. Larger amounts
should be discounted less (Kirby and Maraković 1996).
"""),
    code('''mag = F.magnitude_effect(clean)
{k: (round(v, 3) if isinstance(v, float) else v) for k, v in mag.items() if k != "table"}'''),
    md("""
## Text pilot: future orientation in everyday posts

Fifteen thousand fictional posts about money, spread over a year, with a dip around Black Friday and
in December and a rise after New Year built in. Two simulated annotators label 900 of them. Then a
classifier is trained and tested two ways: on a random split, and holding out whole phrasings, as
happens when language moves on after the labels were made.
"""),
    code('''posts = N.simulate_posts()
posts["posts"].sample(6, random_state=3)[["week", "text", "true_label"]]'''),
    code('''text = N.evaluate_text(posts["annotations"])
{k: (round(v, 3) if isinstance(v, float) else v) for k, v in text.items() if k not in ("confusion", "model")}'''),
    md("""
The random split says 0.96; holding out phrasings says about 0.5. The second number is the one to
believe for new data. Even so, the weekly index built from the classifier follows the truth well,
because errors average out over a few hundred posts a week.
"""),
    code('''N.accuracy_by_phrasing(posts["posts"], text)'''),
    code('''weekly = N.weekly_index(posts["posts"], text)
for c in ("classifier", "lexicon"):
    print(f"{c:>10}: r = {np.corrcoef(weekly[c + '_index'], weekly['true_index'])[0, 1]:.3f}")
R.plot_weekly(weekly, Path("outputs/figures/future_orientation_index.png"))
display(Image("outputs/figures/future_orientation_index.png"))'''),
    md("""
## From here to the paper

The draft in `paper/paper.pdf` writes these results up, and `docs/literature_review.md` maps the
research they build on. With real social-media data the same steps apply, plus an ethics review and
GDPR safeguards: only public posts, pseudonymised authors and aggregated reporting.
"""),
]


class _CapturedImage:
    def __init__(self, filename: str) -> None:
        self.data = Path(filename).read_bytes()


def _execute(cells: list[dict], workdir: Path) -> None:
    """Run code cells in a shared namespace and store their outputs."""
    shown: list = []
    # Stand-ins for IPython.display; the import line is skipped when executing here.
    ns: dict = {"__name__": "__main__", "Image": lambda filename: _CapturedImage(filename),
                "display": lambda obj: shown.append(obj)}
    old_cwd = os.getcwd()
    os.chdir(workdir)
    count = 0
    try:
        for cell in cells:
            if cell["cell_type"] != "code":
                continue
            count += 1
            shown.clear()
            src = cell["source"].replace("from IPython.display import Image, display", "pass")
            tree = ast.parse(src)
            last_expr = None
            if tree.body and isinstance(tree.body[-1], ast.Expr):
                last_expr = ast.Expression(tree.body.pop().value)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                exec(compile(tree, f"<cell {count}>", "exec"), ns)
                result = eval(compile(last_expr, f"<cell {count}>", "eval"), ns) if last_expr else None
            outputs = []
            printed = buf.getvalue()
            for obj in list(shown):
                outputs.append(_display_output(obj))
            if printed:
                # Keep print output ahead of images, like a real kernel would for this code.
                outputs.insert(0, {"name": "stdout", "output_type": "stream", "text": printed})
            if result is not None:
                out = _display_output(result)
                out["output_type"] = "execute_result"
                out["execution_count"] = count
                outputs.append(out)
            cell["outputs"] = outputs
            cell["execution_count"] = count
    finally:
        os.chdir(old_cwd)


def _display_output(obj) -> dict:
    if isinstance(obj, _CapturedImage):
        return {"output_type": "display_data", "metadata": {},
                "data": {"image/png": base64.b64encode(obj.data).decode(), "text/plain": "<IPython.core.display.Image object>"}}
    data = {"text/plain": repr(obj)}
    if hasattr(obj, "_repr_html_"):
        html = obj._repr_html_()
        if html:
            data["text/html"] = html
    return {"output_type": "display_data", "metadata": {}, "data": data}


def _write(cells: list[dict], path: Path) -> None:
    for c in cells:
        lines = c["source"].splitlines(keepends=True)
        c["source"] = lines
        for o in c.get("outputs", []):
            if "text" in o:
                o["text"] = o["text"].splitlines(keepends=True)
            for k in ("text/plain", "text/html"):
                if k in o.get("data", {}):
                    o["data"][k] = o["data"][k].splitlines(keepends=True)
    nb = {
        "cells": cells,
        "metadata": {
            "colab": {"provenance": []},
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "version": "3.11"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    for i, c in enumerate(cells):
        c["id"] = f"cell-{i:02d}"
    path.write_text(json.dumps(nb, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    NB_DIR.mkdir(exist_ok=True)
    books = {
        "01_experiment_and_data_quality.ipynb": NB1,
        "02_models_vs_machine_learning.ipynb": NB2,
        "03_framing_effect_and_text_pilot.ipynb": NB3,
    }
    for name, cells in books.items():
        _execute(cells, NB_DIR)
        _write(cells, NB_DIR / name)
        print(f"built and executed {name}: {sum(c['cell_type'] == 'code' for c in cells)} code cells")


if __name__ == "__main__":
    main()
