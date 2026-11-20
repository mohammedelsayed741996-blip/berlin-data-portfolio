import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from timepref import data, quality as Q  # noqa: E402


@pytest.fixture(scope="session")
def tables():
    return data.generate()


@pytest.fixture(scope="session")
def cleaned(tables):
    return Q.apply(tables)


@pytest.fixture(scope="session")
def clean(cleaned):
    return cleaned[0]


@pytest.fixture(scope="session")
def small(clean):
    """80 participants, enough for model tests that would be slow on everyone."""
    pids = clean["pid"].drop_duplicates().sample(80, random_state=1)
    return clean[clean["pid"].isin(pids)].reset_index(drop=True)
