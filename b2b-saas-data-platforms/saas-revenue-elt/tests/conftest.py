"""One full 92-day simulation shared by the integration tests (about 35 seconds)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from saas_elt import config  # noqa: E402
from saas_elt.pipeline import run_simulation  # noqa: E402


@pytest.fixture(scope="session")
def sim(tmp_path_factory):
    settings = config.RunSettings(workdir=tmp_path_factory.mktemp("sim"))
    return run_simulation(settings)


@pytest.fixture(scope="session")
def wh(sim):
    return sim.warehouse
