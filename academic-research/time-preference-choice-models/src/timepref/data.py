"""Write and read the experiment files.

participants.csv  one row per submission (pseudonymous code, condition, device, timing)
trials.csv.gz     one row per choice
truth.csv         the simulation's ground truth; a real study would not have this file
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from . import world

PUBLIC = ["pid", "submission", "trial", "frame", "ss_amount", "ss_delay", "ll_amount", "ll_delay", "catch", "choice_ll", "rt_ms"]


def generate(seed: int | None = None) -> dict[str, pd.DataFrame]:
    return world.simulate() if seed is None else world.simulate(seed)


def save(tables: dict[str, pd.DataFrame], folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    tables["participants"].to_csv(folder / "participants.csv", index=False)
    tables["trials"][PUBLIC].to_csv(folder / "trials.csv.gz", index=False)
    tables["trials"][["pid", "submission", "trial", "p_true"]].to_csv(folder / "truth_trials.csv.gz", index=False)
    tables["truth"].to_csv(folder / "truth.csv", index=False)


def load(folder: Path) -> dict[str, pd.DataFrame]:
    tr = pd.read_csv(folder / "trials.csv.gz").merge(pd.read_csv(folder / "truth_trials.csv.gz"), on=["pid", "submission", "trial"])
    return {"participants": pd.read_csv(folder / "participants.csv", parse_dates=["submitted_at"]),
            "trials": tr, "truth": pd.read_csv(folder / "truth.csv")}
