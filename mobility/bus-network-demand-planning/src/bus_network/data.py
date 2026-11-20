"""Build, save and load the synthetic systems."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from . import config as C, world

STR = {c: str for c in ["trip_id", "line", "direction", "dep_time", "partner_id", "stop_id", "date", "month", "contract_end"]}


def generate(seed: int = C.SEED) -> dict[str, pd.DataFrame]:
    t = world.simulate(np.random.default_rng(seed))
    t.pop("trips_full")
    return t


def save(tables: dict, folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        suffix = ".csv.gz" if len(df) > 20_000 else ".csv"
        df.to_csv(folder / f"{name}{suffix}", index=False)


def load(folder: Path) -> dict[str, pd.DataFrame]:
    out = {}
    for p in sorted(folder.glob("*.csv*")):
        out[p.name.split(".")[0]] = pd.read_csv(p, dtype=STR)
    return out
