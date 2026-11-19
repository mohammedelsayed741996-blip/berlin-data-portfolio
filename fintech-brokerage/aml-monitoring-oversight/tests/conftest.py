"""Shared fixtures: one generated dataset (about 40 seconds) and one oversight run."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aml_oversight import data, pipeline  # noqa: E402


@pytest.fixture(scope="session")
def tables(tmp_path_factory):
    folder = tmp_path_factory.mktemp("data")
    data.save(data.generate(), folder)
    return data.load(folder)


@pytest.fixture(scope="session")
def run(tables):
    return pipeline.run(tables)
