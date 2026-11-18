"""Shared fixtures: one generated dataset and one full run (about a minute)."""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
warnings.filterwarnings("ignore")

from downgrade_ews import data, pipeline  # noqa: E402


@pytest.fixture(scope="session")
def tables(tmp_path_factory):
    folder = tmp_path_factory.mktemp("data")
    data.save(data.generate(), folder)
    return data.load(folder)            # round trip through CSV, as the pipeline reads it


@pytest.fixture(scope="session")
def run(tables):
    return pipeline.run(tables)
