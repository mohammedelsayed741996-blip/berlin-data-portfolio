"""Settings for the simulated intertemporal choice experiment and the analysis."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

SEED = 20261121

# ---------------------------------------------------------------- experiment design
N_PARTICIPANTS = 400            # genuine sign-ups before duplicates and careless responders are added
N_TRIALS = 60                   # money-earlier-or-later trials per participant
N_CATCH = 4                     # dominated-option attention checks per participant
CONDITIONS = ("delay", "date")  # between subjects: "in 30 days" vs "on 21 December"
SS_DELAYS = (0, 0, 0, 7, 30)    # front-end delay of the sooner option, in days (now is drawn more often)
INTERVALS = (7, 14, 30, 60, 90, 180)
SS_AMOUNT = (5, 80)             # euros
LL_RATIO = (1.02, 2.5)          # larger-later / smaller-sooner

# ---------------------------------------------------------------- the people (simulation truth)
TYPE_SHARES = {"hyperbolic": 0.35, "quasi_hyperbolic": 0.25, "exponential": 0.15, "itch": 0.25}
DATE_FRAME_LOGK_SHIFT = -0.5    # date framing multiplies k by exp(-0.5) = 0.61 (Read et al. 2005 report lower discounting)
DATE_FRAME_BETA_SHIFT = 0.07    # and weakens present bias
DATE_FRAME_ITCH_TR = 0.6        # heuristic users weigh relative delay less under date framing
MAGNITUDE_EXPONENT = -0.35      # k scales with (amount / 40) ** -0.35: larger amounts are discounted less
LAPSE = 0.02                    # chance a genuine participant clicks at random on a trial

# ---------------------------------------------------------------- planted data-quality problems
PLANTED = {
    "duplicate_submissions": 12,   # participants who took the study twice
    "random_clickers": 8,          # fast, random answers
    "straightliners": 8,           # always click the later option
}

# ---------------------------------------------------------------- pre-registered exclusion rules
MAX_CATCH_FAILS = 1             # exclude if 2 or more of 4 catch trials are failed
MIN_MEDIAN_RT_MS = 450          # exclude if the median response time is faster than this

# ---------------------------------------------------------------- evaluation
CV_FOLDS = 4                    # folds over each participant's trials
BOOT = 2000


@dataclass
class Paths:
    root: Path = field(default_factory=lambda: Path(__file__).resolve().parents[2])

    @property
    def data(self) -> Path:
        return self.root / "data"

    @property
    def outputs(self) -> Path:
        return self.root / "outputs"

    @property
    def figures(self) -> Path:
        return self.root / "outputs" / "figures"
