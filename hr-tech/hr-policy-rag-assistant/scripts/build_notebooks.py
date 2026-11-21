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
BASE = "https://colab.research.google.com/github/mohammedelsayed741996-blip/berlin-data-portfolio/blob/main/hr-tech/hr-policy-rag-assistant/notebooks"

SETUP = '''import os, sys, subprocess, warnings
from pathlib import Path

REPO = "https://github.com/mohammedelsayed741996-blip/berlin-data-portfolio.git"
PROJECT = "hr-tech/hr-policy-rag-assistant"

if "google.colab" in sys.modules:
    if not Path("/content/berlin-data-portfolio").exists():
        subprocess.run(["git", "clone", "--depth", "1", REPO, "/content/berlin-data-portfolio"], check=True)
    os.chdir(f"/content/berlin-data-portfolio/{PROJECT}")
else:
    here = Path.cwd()
    while not (here / "src" / "hrrag").exists() and here != here.parent:
        here = here.parent
    os.chdir(here)

sys.path.insert(0, str(Path.cwd() / "src"))
warnings.filterwarnings("ignore")
import pandas as pd
pd.set_option("display.max_columns", 20)
pd.set_option("display.width", 160)
pd.set_option("display.max_colwidth", 90)
from IPython.display import Image, display
print("Project folder:", Path.cwd().name)'''

LOAD = '''from hrrag.config import Settings
from hrrag.corpus import load
from hrrag.retrieval import Retriever, visible
from hrrag.answer import Assistant

passages = load(Path("policies"))
retriever = Retriever(passages, "hybrid")
assistant = Assistant(retriever, Settings())
print(f"{len(passages)} passages from {len({p.policy_id for p in passages})} policies")'''


def md(text: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": text.strip("\n")}


def code(text: str) -> dict:
    return {"cell_type": "code", "metadata": {}, "source": text.strip("\n"), "execution_count": None, "outputs": []}


def badge(name: str) -> str:
    return f"[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)]({BASE}/{name})"


NB1 = [
    md(f"""
# 01 · Policies, retrieval and access control

{badge("01_corpus_retrieval_and_access.ipynb")}

The assistant answers employees' HR questions from the company's own policies, and from nothing else.
The policies here belong to a fictional car maker, Northlake Motors GmbH: 13 documents on leave,
sickness, shifts, travel, parental leave and more, written for this project. Two of them are
restricted: one for managers and one for HR only.
"""),
    code(SETUP),
    code(LOAD),
    md("""
## From documents to passages

Each policy is a Markdown file with a header: id, version, effective date, audience and owner.
Passages follow the document's own sections, so a citation points to a place a person can open
and check.
"""),
    code('''pd.DataFrame([{"pid": p.pid, "audience": p.audience, "version": p.version, "words": len(p.text.split()), "text": p.text[:70] + "…"}
              for p in passages]).head(10)'''),
    code('''pd.Series([p.audience for p in passages]).value_counts().rename("passages")'''),
    md("""
## Access control happens before ranking

Passages the role may not read are removed before anything is scored, so they cannot leak
through a score, a snippet or a citation. The same question gets different results for an
employee and for HR.
"""),
    code('''q = "What is the merit budget for 2026?"
for role in ("employee", "hr"):
    hits, conf = retriever.search(q, role=role, k=3)
    print(f"{role:>8}  confidence {conf:.2f}  ", [h.passage.pid for h in hits])'''),
    md("""
## Questions in employees' own words

People ask "how much Urlaub", "doctor's note" or "home office", while the policies say "annual
leave", "medical certificate" and "mobile work". A synonym map adds the policies' own words to the
query, and character n-grams absorb typos and word forms.
"""),
    code('''from hrrag.text import expand
for q in ["How much Urlaub do I have?", "Do I need a Krankmeldung on day 2?", "Can I do home office from Spain?"]:
    print(q, "->", expand(q))'''),
    code('''for q in ["How much Urlaub do I have?", "Do I need a doctors note on day 2?", "night shift Zuschlag", "Can I work from Spain for a few weeks?"]:
    a = assistant.ask(q)
    src = f"{a.citations[0]['policy_id']}, {a.citations[0]['section']}" if a.citations else "none (declined)"
    print(f"Q: {q}\\nA: {a.text}\\n   source: {src}, confidence {a.confidence:.2f}\\n")'''),
    md("""
The first two are right. The last two show the limits, and they are left in on purpose. The
Zuschlag question lands on the section about how allowances are taxed instead of the one with the
rates, because both mention night work. The question about Spain scores 0.167, just under the 0.17
threshold, so the assistant declines rather than guessing. Notebook 02 counts misses like these
systematically.
"""),
]

NB2 = [
    md(f"""
# 02 · Evaluation: does it answer correctly, and does it know when not to?

{badge("02_evaluation.ipynb")}

93 hand-written questions, phrased the way employees ask. 77 have an answer in the policies, each
with the passage it should cite and the facts the answer must contain. The other 16 should be
declined: 10 are out of scope, and 6 ask for restricted content with a role that may not see it.
Half the questions are a dev split, used for every design choice and for the decline threshold.
The other half are a test split, reported only.
"""),
    code(SETUP),
    code(LOAD + '''
from hrrag import evaluate as E
gold = E.gold()
gold.sample(6, random_state=2)[["question", "role", "expected", "must_include", "split"]]'''),
    md("""
## Retrievers

BM25 (keywords), TF-IDF on words and character n-grams, and a hybrid of both by reciprocal rank
fusion, each with and without synonym expansion. The hybrid with synonyms was chosen on dev.
On the test split the variants are within one or two questions of each other.
"""),
    code('''pd.concat({"dev": E.ablation(passages, gold, "dev"), "test": E.ablation(passages, gold, "test")}).round(3)'''),
    md("""
## When to say "I don't know"

The assistant declines when its best passage scores below a threshold. Too low, and it answers
questions it should not; too high, and it refuses questions it could answer. The threshold is
chosen on dev.
"""),
    code('''f = E.full(passages)
print("threshold:", f["threshold"])
display(Image("outputs/figures/decline_threshold.png"))'''),
    md("""
## Results on held-out questions
"""),
    code('''pd.DataFrame({"test": f["test"], "dev": f["dev"]}).round(3)'''),
    md("""
The gap between dev and test, 83% against 70% correct answers, is why the test split exists:
it is the more honest number. The CI pipeline fails if test performance drops below 65% correct
answers, 90% top-3 retrieval or 95% correct refusals, or if a single restricted passage is cited.

## Where it goes wrong

In most misses the right passage is ranked second or third. An LLM that reads all four retrieved
passages, or a reranker, should fix many of them, since the right passage is in the top 3 for
95% of test questions.
"""),
    code('''r = f["results"]
r.query("split == 'test' and should_answer and not (answered and cited_expected)")[["question", "expected", "rank", "citations"]]'''),
]

NB3 = [
    md(f"""
# 03 · The service: API, privacy and an optional LLM

{badge("03_service_privacy_and_llm.ipynb")}

The assistant runs as a small web service (Starlette and uvicorn) with a TypeScript front end, in
Docker, with PostgreSQL for the question log and Kubernetes manifests for deployment. This
notebook calls the API in-process, so it runs anywhere, including Colab.
"""),
    code(SETUP),
    code('''import asyncio, json
from hrrag.api import create_app
from hrrag.config import Settings

app = create_app(Settings(database_url="sqlite:///:memory:"))

def call(method, path, body=None, headers=None, query=""):
    """Call the ASGI app directly, the way a test client would."""
    data = json.dumps(body).encode() if body is not None else b""
    msgs, sent = [], False
    async def receive():
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": data, "more_body": False}
        return {"type": "http.disconnect"}
    async def send(m):
        msgs.append(m)
    hdrs = [(b"content-type", b"application/json")] + [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    scope = {"type": "http", "method": method, "path": path, "query_string": query.encode(), "headers": hdrs,
             "http_version": "1.1", "scheme": "http", "server": ("nb", 80), "client": ("127.0.0.1", 1), "root_path": ""}
    asyncio.run(app(scope, receive, send))
    status = next(m["status"] for m in msgs if m["type"] == "http.response.start")
    return status, json.loads(b"".join(m.get("body", b"") for m in msgs if m["type"] == "http.response.body"))

call("GET", "/health")'''),
    md("""
## Personal data never reaches the log

Employees sometimes paste their own details into a question. Names, employee IDs, emails, phone
numbers, IBANs, tax IDs and dates are replaced before the question is answered or stored, and the
log is deleted after 90 days.
"""),
    code('''status, out = call("POST", "/api/ask", {"question": "Hi, my name is Lena Fischer (E-204871), how long can I take Elternzeit?", "session": "nb"})
print(out["answer"]); print("removed:", out["redacted"])
print("stored:", app.state.store._exec("SELECT question FROM queries").fetchall())'''),
    md("""
## The role comes from the identity proxy, not the browser

In production a single sign-on proxy sets the `X-User-Role` header. A request that claims to be
HR in its body is still treated as an employee when the header says so.
"""),
    code('''for headers in ({"X-User-Role": "employee"}, {"X-User-Role": "hr"}):
    _, out = call("POST", "/api/ask", {"question": "What is the merit budget for 2026?", "role": "hr"}, headers=headers)
    print(headers["X-User-Role"], "->", out["answered"], "|", out["answer"][:90])'''),
    md("""
## Plugging in an LLM, with guardrails

Set `LLM_BASE_URL`, `LLM_API_KEY` and `LLM_MODEL` to use any OpenAI-compatible model. The prompt
allows only the numbered passages, and the reply is checked: an answer without a citation, or with a
citation to a passage it was not given, is replaced by the extractive answer. Here a fake model
shows each case.
"""),
    code('''from hrrag.answer import Assistant, LLMAnswerer
from hrrag.corpus import load
from hrrag.retrieval import Retriever

retriever = Retriever(load(Path("policies")))
def fake(reply):
    return LLMAnswerer(Settings(llm_base_url="http://llm", llm_model="demo"), transport=lambda payload: {"choices": [{"message": {"content": reply}}]})

for reply in ["Office staff can work remotely up to two days a week [1].", "Probably three days or so.", "Two days [7].", "NOT_FOUND"]:
    a = Assistant(retriever, answerer=fake(reply)).ask("How many days a week can I work remotely?")
    print(f"model said: {reply!r:60} -> answered={a.answered}: {a.text[:70]}")'''),
    code('''print(LLMAnswerer.prompt("How many days a week can I work remotely?", retriever.search("remote work days", k=2)[0])[0]["content"])'''),
    md("""
## Running it for real

```bash
docker compose up --build          # the app and PostgreSQL, on http://localhost:8000
kubectl apply -f deploy/k8s/        # Deployment, Service, ConfigMap, autoscaler (add the Secret first)
```

CI builds the image, starts it, and checks `/health` and a real question against the running
container. It also runs the test suite against a PostgreSQL service.
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
        "01_corpus_retrieval_and_access.ipynb": NB1,
        "02_evaluation.ipynb": NB2,
        "03_service_privacy_and_llm.ipynb": NB3,
    }
    for name, cells in books.items():
        _execute(cells, NB_DIR)
        _write(cells, NB_DIR / name)
        print(f"built and executed {name}: {sum(c['cell_type'] == 'code' for c in cells)} code cells")


if __name__ == "__main__":
    main()
