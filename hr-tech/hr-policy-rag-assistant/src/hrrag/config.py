"""Settings, read from environment variables so the same image runs locally, in Docker and in Kubernetes."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# who may read what: a role sees its own level and everything below it
ROLE_LEVEL = {"employee": 0, "manager": 1, "hr": 2}


@dataclass(frozen=True)
class Settings:
    policies_dir: Path = field(default_factory=lambda: Path(os.getenv("POLICIES_DIR", ROOT / "policies")))
    database_url: str = field(default_factory=lambda: os.getenv("DATABASE_URL", f"sqlite:///{ROOT / 'outputs' / 'app.db'}"))
    retriever: str = field(default_factory=lambda: os.getenv("RETRIEVER", "hybrid"))
    top_k: int = field(default_factory=lambda: int(os.getenv("TOP_K", "4")))
    # abstain when the best passage scores below this (calibrated on the evaluation set, see evaluate.calibrate)
    min_score: float = field(default_factory=lambda: float(os.getenv("MIN_SCORE", "0.17")))
    # optional LLM: any OpenAI-compatible chat endpoint; without it the assistant answers extractively
    llm_base_url: str = field(default_factory=lambda: os.getenv("LLM_BASE_URL", ""))
    llm_api_key: str = field(default_factory=lambda: os.getenv("LLM_API_KEY", ""))
    llm_model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", ""))
    log_queries: bool = field(default_factory=lambda: os.getenv("LOG_QUERIES", "true").lower() == "true")
