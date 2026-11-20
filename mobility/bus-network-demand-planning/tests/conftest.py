import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bus_network import data, validation as V  # noqa: E402


@pytest.fixture(scope="session")
def tables():
    return data.generate()


@pytest.fixture(scope="session")
def trips(tables):
    return V.clean_trips(tables)
