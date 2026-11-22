import json
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from spendcube import cube as C, generate, sources as S, suppliers as SU  # noqa: E402
from spendcube.pipeline import load_indices  # noqa: E402


@pytest.fixture(scope="session")
def raw_dir(tmp_path_factory):
    """Generate the exports from scratch in a temporary folder, as CI does."""
    d = tmp_path_factory.mktemp("raw")
    generate.write(d)
    return d


@pytest.fixture(scope="session")
def raw(raw_dir):
    return S.read_raw(raw_dir)


@pytest.fixture(scope="session")
def key(raw_dir):
    return json.loads((raw_dir / "_answer_key.json").read_text())


@pytest.fixture(scope="session")
def truth(raw_dir):
    return pd.read_csv(raw_dir / "_truth_lines.csv.gz")


@pytest.fixture(scope="session")
def matched(raw):
    return SU.match(SU.stack_masters(raw))


@pytest.fixture(scope="session")
def model(raw, matched, tmp_path_factory):
    recs, _, _ = matched
    lines, log = C.clean(S.harmonise(raw), recs, raw)
    tables = C.build(lines, SU.golden_records(recs), tmp_path_factory.mktemp("model"))
    return tables, C.to_sqlite(tables), log


@pytest.fixture(scope="session")
def indices(raw):
    return load_indices(raw)
