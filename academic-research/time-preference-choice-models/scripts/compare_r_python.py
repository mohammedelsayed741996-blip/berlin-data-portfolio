"""Check that the R replication (r/fit_hyperbolic.R) matches the Python estimates.

Run after:  Rscript r/fit_hyperbolic.R data outputs/hyperbolic_fits_r.csv
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

root = Path(__file__).resolve().parents[1]
r = pd.read_csv(root / "outputs" / "hyperbolic_fits_r.csv")
py = pd.read_csv(root / "outputs" / "model_fits.csv.gz").query("model == 'hyperbolic'")[["pid", "theta0", "theta1"]]
m = r.merge(py, on="pid", how="outer", indicator=True)
missing = (m["_merge"] != "both").sum()
diff = (m["log_k"] - m["theta0"]).abs()
corr = np.corrcoef(m["log_k"], m["theta0"])[0, 1]
print(f"participants: R {len(r)}, Python {len(py)}, unmatched {missing}")
print(f"log k: correlation {corr:.5f}, median abs diff {diff.median():.5f}, max abs diff {diff.max():.4f}")
ok = missing == 0 and corr > 0.999 and diff.median() < 0.01
print("R and Python agree" if ok else "R and Python DISAGREE")
sys.exit(0 if ok else 1)
