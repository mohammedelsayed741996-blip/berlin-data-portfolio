"""Build, save and load the synthetic dataset."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from . import config as C, news, world

DTYPES = {"issuer_id": str, "month": str, "quarter_end": str, "published": str, "date": str}


def generate(seed: int = C.SEED) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    issuers = world.make_issuers(rng)
    w = world.simulate(issuers, rng)
    articles = news.generate_news(issuers, w["latent"], w["rating_actions"], rng)
    return {"issuers": issuers, **w, "news": articles}


def save(tables: dict[str, pd.DataFrame], folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        suffix = ".csv.gz" if name in ("news", "latent", "ratings", "equity") else ".csv"
        df.to_csv(folder / f"{name}{suffix}", index=False)


def load(folder: Path) -> dict[str, pd.DataFrame]:
    out = {}
    for p in sorted(folder.glob("*.csv*")):
        out[p.name.split(".")[0]] = pd.read_csv(p, dtype=DTYPES, keep_default_na=False, na_values=[""])
    return out
