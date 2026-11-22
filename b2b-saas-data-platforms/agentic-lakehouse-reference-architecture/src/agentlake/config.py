"""Settings for the reference implementation. Everything can be overridden with environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SEED = 20261122

# who may do what; the tools enforce this, the model never decides it
ROLES = {
    "account_manager": {"scope": "own_accounts", "actions": ["draft_payment_reminder"]},
    "finance": {"scope": "all_accounts", "actions": ["draft_payment_reminder", "propose_credit_hold"]},
    "head_of_finance": {"scope": "all_accounts", "actions": []},          # decides on credit holds
    "viewer": {"scope": "own_accounts", "actions": []},
}


@dataclass(frozen=True)
class Settings:
    lake_dir: Path = field(default_factory=lambda: Path(os.getenv("LAKE_DIR", ROOT / "lake")))
    docs_dir: Path = field(default_factory=lambda: Path(os.getenv("DOCS_DIR", ROOT / "docs" / "policies")))
    trace_dir: Path = field(default_factory=lambda: Path(os.getenv("TRACE_DIR", ROOT / "outputs" / "traces")))
    planner: str = field(default_factory=lambda: os.getenv("PLANNER", "rules"))          # rules | bedrock
    bedrock_model_id: str = field(default_factory=lambda: os.getenv("BEDROCK_MODEL_ID", "eu.anthropic.claude-sonnet-4-5-20250929-v1:0"))
    aws_region: str = field(default_factory=lambda: os.getenv("AWS_REGION", "eu-central-1"))
    max_steps: int = field(default_factory=lambda: int(os.getenv("MAX_STEPS", "6")))
    max_rows: int = field(default_factory=lambda: int(os.getenv("MAX_ROWS", "50")))
    # rough cost model for the dashboard (EUR per 1,000 tokens); replace with the contract price
    cost_in_per_1k: float = field(default_factory=lambda: float(os.getenv("COST_IN_PER_1K", "0.003")))
    cost_out_per_1k: float = field(default_factory=lambda: float(os.getenv("COST_OUT_PER_1K", "0.015")))
