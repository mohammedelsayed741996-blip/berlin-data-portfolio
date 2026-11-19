"""Build the synthetic world and the first-line programme outputs; save and load them."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from . import config as C, monitoring, world

STR_COLS = {c: str for c in ["client_id", "tx_id", "alert_id", "hit_id", "entry_id", "rule", "analyst", "l1_rationale",
                               "l1_closed_date", "sar_date", "l2_decision", "psp", "counterparty", "month"]}


def generate(seed: int = C.SEED) -> dict[str, pd.DataFrame]:
    tables = world.generate(seed)
    tables.update(monitoring.run_programme(tables, seed))
    return tables


def save(tables: dict, folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        suffix = ".csv.gz" if len(df) > 20_000 else ".csv"
        df.to_csv(folder / f"{name}{suffix}", index=False)


def load(folder: Path) -> dict[str, pd.DataFrame]:
    out = {}
    for p in sorted(folder.glob("*.csv*")):
        out[p.name.split(".")[0]] = pd.read_csv(p, dtype=STR_COLS, keep_default_na=False, na_values=[])
    return out
