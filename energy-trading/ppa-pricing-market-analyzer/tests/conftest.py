import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ppalab import crm as C, market as M, pricing as P, trends as T  # noqa: E402


@pytest.fixture(scope="session")
def data(tmp_path_factory):
    d = tmp_path_factory.mktemp("raw")
    M.write(d)
    C.write(d)
    return M.load(d) | {"opp": C.load(d)}


@pytest.fixture(scope="session")
def hourly(data):
    return T.enrich(data["hourly"])


@pytest.fixture(scope="session")
def scen(data):
    return P.scenarios([2027, 2028], 20, data["curve"], 0.3)
