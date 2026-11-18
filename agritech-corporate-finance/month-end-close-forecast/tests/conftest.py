"""Shared fixtures: one generated extract and one full close run (about 10 seconds)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from close_forecast import data_generator, pipeline  # noqa: E402


@pytest.fixture(scope="session")
def tables(tmp_path_factory):
    folder = tmp_path_factory.mktemp("data")
    data_generator.save(data_generator.generate(), folder)
    return data_generator.load(folder)   # round trip through CSV, as the pipeline reads it


@pytest.fixture(scope="session")
def run(tables):
    return pipeline.run(tables)


@pytest.fixture(scope="session")
def checks(run):
    return {c.check_id: c for c in run.checks}
