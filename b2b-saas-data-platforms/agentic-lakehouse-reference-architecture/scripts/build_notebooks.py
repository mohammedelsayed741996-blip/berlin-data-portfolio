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
BASE = "https://colab.research.google.com/github/mohammedelsayed741996-blip/berlin-data-portfolio/blob/main/b2b-saas-data-platforms/agentic-lakehouse-reference-architecture/notebooks"

SETUP = """import os, sys, subprocess, warnings
from pathlib import Path

REPO = "https://github.com/mohammedelsayed741996-blip/berlin-data-portfolio.git"
PROJECT = "b2b-saas-data-platforms/agentic-lakehouse-reference-architecture"

if "google.colab" in sys.modules:
    if not Path("/content/berlin-data-portfolio").exists():
        subprocess.run(["git", "clone", "--depth", "1", REPO, "/content/berlin-data-portfolio"], check=True)
    os.chdir(f"/content/berlin-data-portfolio/{PROJECT}")
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "jsonschema"], check=True)
else:
    here = Path.cwd()
    while not (here / "src" / "agentlake").exists() and here != here.parent:
        here = here.parent
    os.chdir(here)

sys.path.insert(0, str(Path.cwd() / "src"))
warnings.filterwarnings("ignore")
import pandas as pd
pd.set_option("display.max_columns", 20)
pd.set_option("display.width", 160)
pd.set_option("display.max_colwidth", 80)
from IPython.display import Image, display
print("Project folder:", Path.cwd().name)"""


def md(text: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": text.strip("\n")}


def code(text: str) -> dict:
    return {"cell_type": "code", "metadata": {}, "source": text.strip("\n"), "execution_count": None, "outputs": []}


def badge(name: str) -> str:
    return f"[![Open in Colab](https://colab.research.google.com/assets/colab-badge.svg)]({BASE}/{name})"


NB1 = [
    md(f"""# 1. Lakehouse and semantic layer

{badge("01_lakehouse_and_semantic_layer.ipynb")}

Kestrel Industrial Supply is a fictional distributor; every account, invoice and person here is synthetic. This notebook rebuilds the bronze, silver and gold layers from two simulated ERP exports, runs the reconciliation checks, and shows how the semantic layer turns a metric request into SQL with row-level security."""),
    code(SETUP),
    code("""from agentlake import lakehouse
out = lakehouse.build_all(Path("lake"))
print("Problems planted in bronze:", out["planted"])
out["quality"]"""),
    md("""Every check compares a gold number with the source system, so a silver rule that drops or double-counts invoices fails the build. The gold layer is what the agent may read:"""),
    code("""gold = {f.stem: pd.read_csv(f) for f in sorted(Path("lake/gold").glob("*.csv"))}
for name, df in gold.items():
    print(f"{name:16s} {len(df):5d} rows   columns: {', '.join(df.columns[:8])}{' ...' if len(df.columns) > 8 else ''}")
gold["account_ar"].sort_values("overdue_eur", ascending=False).head(5)[["account_id", "name", "region", "owner", "open_eur", "overdue_eur", "credit_used_pct"]]"""),
    md("""## The semantic layer

The agent asks for a metric, dimensions and filters from allow-lists. The layer writes the SQL, binds every value as a parameter and adds the owner predicate for account managers."""),
    code("""from agentlake import semantic as S
sql, params = S.compile_metric("overdue_receivables", ["region"], [{"column": "segment", "op": "eq", "value": "OEM"}],
                               S.Scope("AM02", "AM02"))
print(sql); print("params:", params)"""),
    code("""wh = S.Warehouse(Path("lake/gold"))
am = S.Scope("AM02", "AM02"); fin = S.Scope("FIN01", None)
print("Account manager AM02 sees:", wh.run(*S.compile_metric("open_receivables", None, None, am)).iloc[0, 0].round(2))
print("Finance sees:            ", wh.run(*S.compile_metric("open_receivables", None, None, fin)).iloc[0, 0].round(2))"""),
    md("""Anything outside the allow-lists is refused before any SQL exists, including a filter value that tries to smuggle SQL in:"""),
    code("""for metric, dims, filters in [("salary", None, None), ("revenue", ["contact_email"], None),
                              ("open_receivables", None, [{"column": "region", "op": "eq", "value": "DACH' OR '1'='1"}])]:
    try:
        sql, params = S.compile_metric(metric, dims, filters, am)
        print("compiled, value bound as a parameter:", params, "->", len(wh.run(sql, params)), "row(s)")
    except S.SemanticError as e:
        print("refused:", e)"""),
]

NB2 = [
    md(f"""# 2. Agent, guard and approvals

{badge("02_agent_guard_and_approvals.ipynb")}

The agent loop asks a planner for the next step, passes every tool call through a guard and records spans. Offline the planner is a deterministic rule planner; in production it is Claude on Amazon Bedrock behind the same interface. Nothing here calls a model."""),
    code(SETUP),
    code("""from agentlake import lakehouse
from agentlake.agent import Agent
from agentlake.config import Settings
from agentlake.tools import User
if not Path("lake/gold/account_ar.csv").exists():
    lakehouse.build_all(Path("lake"))
agent = Agent(Settings(trace_dir=Path("outputs/traces")))
am, fin, hof = User("AM02", "account_manager"), User("FIN01", "finance"), User("HOF01", "head_of_finance")
res = agent.run("What does Elbtal Maschinenbau owe us and how much is overdue?", am)
print(res.answer); print("tools:", [c["tool"] for c in res.calls])"""),
    md("""The same question from another account manager gets the answer the agent would give for an account that does not exist. The guard never reveals that the account is someone else's."""),
    code("""other = User("AM05", "account_manager")
print(agent.run("What does Elbtal Maschinenbau owe us and how much is overdue?", other).answer)"""),
    md("""## Actions wait for a person

Asking for a payment reminder creates an approval request. A credit hold needs the Head of Finance, and the person who proposed it cannot approve it."""),
    code("""r1 = agent.run("Draft a payment reminder for Elbtal Maschinenbau", am)
print(r1.answer)
from agentlake.approvals import ApprovalError
hold = agent.approvals.request("credit_hold", "A002", "AM02", "FIN01", {"reason": "over limit"})
for user, role in [("FIN01", "finance"), ("HOF01", "head_of_finance")]:
    try:
        a = agent.approvals.decide(hold.id, user, role, approve=True)
        print(f"{user}: {a.status}")
    except ApprovalError as e:
        print(f"{user}: refused ({e})")"""),
    md("""## What a trace looks like

Each run is a tree of spans: the run, each planner step and each tool call with the guard's verdict and row count. Free text in arguments is truncated so traces do not collect personal data."""),
    code("""import json
res = agent.run("Which of my accounts are over their credit limit?", am, export=True)
spans = [json.loads(l) for l in open(f"outputs/traces/{res.trace_id}.jsonl")]
pd.DataFrame([{"span": s["name"], "duration_ms": s["duration_ms"], "status": s["status"],
               **{k: v for k, v in s["attributes"].items() if k in ("tool", "allowed", "rows", "step")}} for s in spans])"""),
]

NB3 = [
    md(f"""# 3. Evaluation and red team

{badge("03_evaluation_and_red_team.ipynb")}

The release gate runs 40 tasks with checks computed from gold, 14 attacks for each of three users with a planner that tries every forbidden call, and the approval rules. CI fails the build if any gate fails."""),
    code(SETUP),
    code("""from agentlake import lakehouse, evaluate as E
from agentlake.agent import Agent
if not Path("lake/gold/account_ar.csv").exists():
    lakehouse.build_all(Path("lake"))
agent = Agent()
tasks, red, rules = E.run_tasks(agent), E.run_red_team(agent), E.approval_rules()
s = E.summary(tasks, red, rules)
print({k: (round(v, 3) if isinstance(v, float) else v) for k, v in s.items() if k != "task_success_by_category"})
print("failed gates:", E.failed_gates(s) or "none")"""),
    code("""tasks.groupby("category").agg(tasks=("id", "count"), passed=("passed", "mean")).round(2)"""),
    md("""The paraphrases are where the rule planner breaks: it passes one of six. Rewording a question is exactly what a language model handles, which is why the gate reports paraphrases separately until the Bedrock planner runs on the same tasks."""),
    code("""tasks[tasks.category == "paraphrase"][["question", "passed", "tools"]]"""),
    code("""display(Image("outputs/figures/task_results.png"))"""),
    md("""## Red team

Every attack ends with no leak and no unauthorised action. Finance users are allowed to read every account, so those runs are expected to return data; the leak check compares what each planner saw with what that user may see."""),
    code("""red.pivot_table(index="attack", columns="user", values="outcome", aggfunc="first")"""),
    code("""display(Image("outputs/figures/red_team.png"))"""),
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
        "01_lakehouse_and_semantic_layer.ipynb": NB1,
        "02_agent_guard_and_approvals.ipynb": NB2,
        "03_evaluation_and_red_team.ipynb": NB3,
    }
    for name, cells in books.items():
        _execute(cells, NB_DIR)
        _write(cells, NB_DIR / name)
        print(f"built and executed {name}: {sum(c['cell_type'] == 'code' for c in cells)} code cells")


if __name__ == "__main__":
    main()
