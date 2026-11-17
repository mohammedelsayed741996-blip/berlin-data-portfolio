"""Data contracts: schema, value and privacy checks applied before anything lands.

Each source has a YAML contract in ``contracts/``. Every incoming record is
checked against it; records that fail go to quarantine with the reasons, the
rest land in the raw layer. Fields the contract does not know are either a
violation or, if the contract allows it, kept and reported as schema drift.

A privacy guard runs on every string value. If a record carries something
that looks like an e-mail address, phone number or IBAN, it is rejected and
the offending value is masked before the record is written to quarantine, so
personal data never reaches the warehouse, not even the error tables.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import yaml

from . import config

PII_PATTERNS: dict[str, re.Pattern[str]] = {
    "email": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    "iban": re.compile(r"\b[A-Z]{2}[0-9]{2}(?:\s?[0-9A-Z]{4}){3,7}\b"),
    "phone": re.compile(r"(?:\+|00)[1-9][0-9 ()/-]{7,}[0-9]"),
}
MASK = "***REDACTED***"


@dataclass
class FieldSpec:
    name: str
    type: str
    required: bool = False
    enum: list | None = None
    pattern: str | None = None
    min: float | None = None
    max: float | None = None
    max_length: int | None = None


@dataclass
class Contract:
    """A parsed data contract."""

    name: str
    version: str
    primary_key: str
    cursor_field: str
    allow_extra_fields: bool
    fields: dict[str, FieldSpec]
    rules: list[dict] = field(default_factory=list)
    freshness_hours: int = 36
    pii: str = "none"
    retention_days: int | None = None

    @property
    def columns(self) -> list[str]:
        return list(self.fields)


@dataclass
class ValidationResult:
    ok: bool
    reasons: list[str]
    extra_fields: list[str]
    safe_record: dict  # record with any personal data masked


def load_contract(name: str, contracts_dir: Path = config.CONTRACTS_DIR) -> Contract:
    path = contracts_dir / f"{name}.yml"
    if not path.exists():
        raise FileNotFoundError(f"No contract named {name!r} in {contracts_dir}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    for key in ("name", "version", "primary_key", "fields"):
        if key not in raw:
            raise ValueError(f"Contract {name} is missing '{key}'")
    fields = {k: FieldSpec(name=k, **v) for k, v in raw["fields"].items()}
    if raw["primary_key"] not in fields:
        raise ValueError(f"Contract {name}: primary key {raw['primary_key']} is not a field")
    return Contract(
        name=raw["name"], version=str(raw["version"]), primary_key=raw["primary_key"],
        cursor_field=raw.get("cursor_field", "updated_at"), allow_extra_fields=bool(raw.get("allow_extra_fields", False)),
        fields=fields, rules=raw.get("rules", []) or [], freshness_hours=int(raw.get("freshness_hours", 36)),
        pii=raw.get("pii", "none"), retention_days=raw.get("retention_days"),
    )


def scan_pii(record: dict) -> tuple[list[str], dict]:
    """Return the kinds of personal data found and a masked copy of the record."""
    found: list[str] = []
    masked = dict(record)
    for key, value in record.items():
        if not isinstance(value, str) or key == "user_hash":
            continue
        for kind, pat in PII_PATTERNS.items():
            if pat.search(value):
                found.append(f"{kind} in {key}")
                masked[key] = MASK
    return found, masked


def _check_type(value, ftype: str) -> bool:
    if ftype == "string":
        return isinstance(value, str)
    if ftype == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if ftype == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if ftype == "date":
        try:
            date.fromisoformat(value)
            return isinstance(value, str) and len(value) == 10
        except (TypeError, ValueError):
            return False
    if ftype == "datetime":
        try:
            datetime.fromisoformat(value)
            return isinstance(value, str)
        except (TypeError, ValueError):
            return False
    raise ValueError(f"Unknown contract type {ftype!r}")


def validate(record: dict, contract: Contract) -> ValidationResult:
    """Check one record against its contract."""
    reasons: list[str] = []
    pii, safe = scan_pii(record)
    reasons += [f"pii_detected: {p}" for p in pii]

    extra = [k for k in record if k not in contract.fields]
    if extra and not contract.allow_extra_fields:
        reasons.append(f"unexpected_fields: {sorted(extra)}")

    for name, spec in contract.fields.items():
        value = record.get(name)
        if value is None:
            if spec.required:
                reasons.append(f"missing: {name}")
            continue
        if not _check_type(value, spec.type):
            reasons.append(f"bad_type: {name} expected {spec.type}")
            continue
        if spec.enum is not None and value not in spec.enum:
            reasons.append(f"not_in_enum: {name}={value!r}")
        if spec.pattern is not None and not re.fullmatch(spec.pattern, value):
            reasons.append(f"pattern_mismatch: {name}")
        if spec.min is not None and value < spec.min:
            reasons.append(f"below_min: {name}={value} < {spec.min}")
        if spec.max is not None and value > spec.max:
            reasons.append(f"above_max: {name}={value} > {spec.max}")
        if spec.max_length is not None and len(value) > spec.max_length:
            reasons.append(f"too_long: {name}")

    if not reasons:
        scope = {k: record.get(k) for k in contract.fields}
        for rule in contract.rules:
            try:
                passed = bool(eval(rule["expression"], {"__builtins__": {}, "abs": abs}, scope))  # noqa: S307
            except Exception as exc:  # a broken rule is reported, not swallowed
                reasons.append(f"rule_error: {rule['name']}: {exc}")
                continue
            if not passed:
                reasons.append(f"rule_failed: {rule['name']}")

    return ValidationResult(ok=not reasons, reasons=reasons, extra_fields=extra, safe_record=safe)
