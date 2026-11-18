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
BASE = "https://colab.research.google.com/github/mohammedelsayed741996-blip/berlin-data-portfolio/blob/main/consulting-financial-services/credit-downgrade-early-warning/notebooks"

SETUP = '''import os, sys, subprocess, warnings
from pathlib import Path

REPO = "https://github.com/mohammedelsayed741996-blip/berlin-data-portfolio.git"
PROJECT = "consulting-financial-services/credit-downgrade-early-warning"

if "google.colab" in sys.modules:
    if not Path("/content/berlin-data-portfolio").exists():
        subprocess.run(["git", "clone", "--depth", "1", REPO, "/content/berlin-data-portfolio"], check=True)
    os.chdir(f"/content/berlin-data-portfolio/{PROJECT}")
else:
    here = Path.cwd()
    while not (here / "src" / "downgrade_ews").exists() and here != here.parent:
        here = here.parent
    os.chdir(here)

sys.path.insert(0, str(Path.cwd() / "src"))
warnings.filterwarnings("ignore")
import pandas as pd
pd.set_option("display.max_columns", 30)
pd.set_option("display.width", 160)
pd.set_option("display.max_colwidth", 110)
from IPython.display import Image, display
print("Project folder:", Path.cwd().name)'''

LOAD = '''from downgrade_ews import config as C, pipeline, features, models, explain, validation, reporting

tables = pipeline.load_tables()      # reads data/, or generates it if missing
run = pipeline.run(tables)           # text model, panel, four issuer models (about a minute)
print(f"{len(tables['news']):,} articles on {C.N_ISSUERS} issuers, {C.START} to {C.END}")'''


def md(text: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": text.strip("\n")}


def code(text: str) -> dict:
    return {"cell_type": "code", "metadata": {}, "source": text.strip("\n"), "execution_count": None, "outputs": []}


def badge(name: str) -> str:
    return f"[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)]({BASE}/{name})"


NB1 = [
    md(f"""
# 01 · Issuers, ratings and the news feed

{badge("01_data_and_news.ipynb")}

The question a bank or investor asks: which of the companies we lend to are likely to be downgraded soon, and can the news tell us before the rating agency does?

All data here is synthetic. 360 made-up European issuers in ten sectors, with ratings from AA to CCC, quarterly financials, share prices for the listed ones, and about 66,000 news articles in English and German from January 2022 to September 2026. No article names a person, and no company is real.
"""),
    code(SETUP),
    code(LOAD),
    md("## The issuers"),
    code('''iss = tables["issuers"]
display(iss.head(8))
display(iss.groupby("sector").size().rename("issuers").to_frame().T)'''),
    md("""
## How credit quality and ratings move

Each issuer has a hidden credit score in rating notches. It moves with sector shocks (real estate after the rate rise in 2022, chemicals on gas prices, automotive in 2024/25), slow deterioration that builds over four to eight months, and rare sudden events. The agency rating follows that score with a lag of one to three months, and outlook changes only come when the agency happens to review the name. That lag is the window an early-warning system can use.
"""),
    code('''a = tables["rating_actions"]
display(a["action"].value_counts().to_frame().T)
dg = a[a["action"] == "downgrade"]
dg.groupby(dg["month"].str[:4]).size().rename("downgrades per year").to_frame().T'''),
    md("## What the news looks like\n\nArticles come from templates, but the mix of topics follows each company's hidden path. A company sliding toward a downgrade gets more refinancing stories and profit warnings. Healthy companies get bad headlines too, troubled ones put out upbeat releases, some articles deny problems, and sector stories mention a company without being about it."),
    code('''n = tables["news"]
display(n.sample(8, random_state=7)[["date", "language", "source", "headline"]])
print(n["language"].value_counts(normalize=True).round(2).to_dict())'''),
    code('''lat = tables["latent"][["issuer_id", "month", "stress_gap", "momentum_3m"]]
mix = n.assign(month=n["date"].str[:7]).merge(lat, on=["issuer_id", "month"])
mix["state"] = pd.cut(mix["stress_gap"] + mix["momentum_3m"], [-99, 0.3, 1.0, 99], labels=["calm", "drifting", "stressed"])
top = mix.groupby("state")["true_topic"].value_counts(normalize=True).unstack().T
top.loc[["profit_warning", "refinancing", "covenant", "liquidity", "denial", "contract_win", "agm"]].round(3)'''),
    md("""
## The target

For every issuer and month: is the issuer downgraded in the next three months? Features use only what was known at the end of that month: articles dated in or before it, financials already published (two months after quarter end), past share prices. The last three months have no label yet.

Training runs to March 2025. The test covers July 2025 to June 2026. The three months in between are left out, so no training label looks into the test period.
"""),
    code('''p = run.panel
print(f"Labelled issuer-months: {p['labelled'].sum():,}, downgrade rate {p.loc[p['labelled'], 'y'].mean():.1%}")
print(f"Train {len(run.train):,} rows up to {run.train['month'].max()}, test {len(run.test):,} rows from {run.test['month'].min()}")'''),
    md("Before the text reaches a model, the company name, sector, city, quarter and every number are masked, and the words after a negation are marked. Notebook 03 explains why each of these was needed."),
    code('''ex = run.scored.sample(3, random_state=3)
for h, t in zip(ex["headline"], ex["text"]):
    print(h); print("  ->", t[:160]); print()'''),
]

NB2 = [
    md(f"""
# 02 · Models, alerts and explanations

{badge("02_models_and_alerts.ipynb")}

Two stages. First, an article model reads each news item and gives it a risk score: TF-IDF on words, word pairs and character n-grams (which also cope with German compounds), then logistic regression. Second, an issuer model combines those scores with the rating, outlook, financials, share price and keyword counts for each issuer and month, using gradient boosting.

Four versions are compared on the same test period, so it is clear what each source of information adds.
"""),
    code(SETUP),
    code(LOAD),
    md("## What the article model learned\n\nWords and phrases with the largest weights, English and German. Masked tokens and filler words are left out."),
    code('''display(explain.top_terms(run.text_model, 10, "en")[["term", "weight", "direction"]].reset_index(drop=True))
display(explain.top_terms(run.text_model, 8, "de")[["term", "weight", "direction"]].reset_index(drop=True))'''),
    md(f"""
## Comparison on the test period

Each model except the outlook rule gets the same review budget: the 15 highest-scoring issuers each month. The outlook rule flags every issuer on negative outlook, about 39 a month.
"""),
    code('''run.evaluation'''),
    code('''display(Image(filename=str(reporting.plot_model_comparison(run.evaluation, Path("outputs/figures/model_comparison.png")))))
display(Image(filename=str(reporting.plot_pr_curves(run.test, run.results, Path("outputs/figures/pr_curves.png")))))'''),
    md("""
Financials barely help in this data: they arrive two months after quarter end and are noisy. Keyword rules double the precision. The NLP scores add the rest: with the same 15 names a month, 29% of alerts were followed by a downgrade, against 25% for keywords and 13% for financials alone, and half of all downgrades were flagged in the three months before they happened. Shuffling the feature groups shows where the signal comes from.
"""),
    code('''explain.feature_group_importance(run.results[models.FULL], run.test)'''),
    md("## One issuer, start to finish"),
    code('''iss = pipeline.story_issuer(run)
name = tables["issuers"].set_index("issuer_id").loc[iss, "issuer_name"]
display(Image(filename=str(reporting.plot_issuer_story(run.panel, run.scored, run.scores_all, iss, name, run.alert_cut, Path("outputs/figures/issuer_story.png")))))
a = tables["rating_actions"]; display(a[a["issuer_id"] == iss])'''),
    md("The evidence an analyst would see for the first alert month: the three strongest articles and the words behind each score."),
    code('''fl = models.alerts(run.test, run.results[models.FULL].scores)
first = fl[fl["issuer_id"] == iss]["month"].min()
print("First alert:", first)
explain.issuer_evidence(run.scored, iss, first, run.text_model)'''),
    md("## The live watchlist\n\nFor September 2026, the latest month, there is no label yet. The issuer model is refitted on every labelled month and the top 15 go to the analysts, each with its strongest article."),
    code('''wl = pipeline.watchlist(run)
wl[["issuer_name", "sector", "rating", "outlook", "score", "headline"]]'''),
]

NB3 = [
    md(f"""
# 03 · Validating the model

{badge("03_model_validation.ipynb")}

An AUC on a test set says little about how a language model will behave on Monday morning. This notebook tests the text model the way you would test any model that reads language for a bank, a GenAI chatbot included: fixed inputs with a known right answer, checks across languages and sectors, calibration, and an honest list of what does not work.
"""),
    code(SETUP),
    code(LOAD),
    md("""
## A shortcut found and removed

The first version of the article model did not mask sectors, cities or quarters. Its strongest words were "transport", "utilities" and "automotive". Sector shocks and reporting seasons happen to line up with downgrades in the training years, so the model learned the calendar instead of the language. That will not hold next year. Masking those tokens cost a little in-sample fit and removed the shortcut. The current top words are about cash, refinancing and outlooks.
"""),
    code('''explain.top_terms(run.text_model, 8, "en")[["term", "weight", "direction"]].reset_index(drop=True)'''),
    md("## Behavioural tests"),
    code('''validation.behavioural_tests(run.text_model, tables["issuers"])'''),
    md("""
The company name has no effect, as intended. The other three results are mixed, and the reasons matter more than the score.

Start with denials. A sentence that denies liquidity problems scores almost as high as one that admits them. In this data that is right: the topic table below shows that issuers denying problems were downgraded within three months about 11% of the time, three to four times the rate after neutral news. Whether that holds for real companies should be checked before anyone relies on it.

Then unseen wording. On twelve sentences written by hand, in phrasings the templates never use, the model gets 7 right. A bag-of-words model trained on a limited vocabulary does not generalise far. With real news this is the main risk, and the fix would be human-labelled articles and a multilingual transformer or LLM classifier, tested with the same sentences.
"""),
    code('''validation.unseen_detail(run.text_model)'''),
    md("## Does the score follow the real topic?\n\nThe true topic of each article is known here, though the model never saw it. Scores by topic should rank credit stress first and good news last."),
    code('''ts = validation.topic_scores(run.scored, C.TEST_START)
display(Image(filename=str(reporting.plot_topic_scores(ts, Path("outputs/figures/topic_scores.png")))))'''),
    md("## Languages, sectors and calibration"),
    code('''display(validation.by_language(run.scored, C.TEST_START))
display(validation.by_segment(run.test, run.results[models.FULL].scores, "sector"))'''),
    md("German articles score about as well as English ones. Consumer goods had no downgrades in the test year, so it cannot be evaluated. The highest score bucket holds most of the downgrades; below it, scores are too low in absolute terms, so they should be read as a ranking until calibrated on recent data."),
    code('''validation.calibration(run.test, run.results[models.FULL].scores)'''),
    md("## Model card\n\nThe pipeline writes a one-page summary for model risk and for the client: purpose, data, design, results, validation and limits."),
    code('''out = pipeline.write_outputs(run)
print(Path("outputs/model_card.md").read_text()[:1500])'''),
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
        "01_data_and_news.ipynb": NB1,
        "02_models_and_alerts.ipynb": NB2,
        "03_model_validation.ipynb": NB3,
    }
    for name, cells in books.items():
        _execute(cells, NB_DIR)
        _write(cells, NB_DIR / name)
        print(f"built and executed {name}: {sum(c['cell_type'] == 'code' for c in cells)} code cells")


if __name__ == "__main__":
    main()
