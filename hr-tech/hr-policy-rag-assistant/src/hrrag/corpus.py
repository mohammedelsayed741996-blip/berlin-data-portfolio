"""Load the policy documents and cut them into passages.

Each policy is a Markdown file with a front-matter header (policy id, version, effective date,
audience, owner). Passages follow the document's own sections (## headings), so a citation points
to a place a person can find, and every passage carries the metadata needed for access control.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class Passage:
    pid: str                # e.g. HR-01#carry-over
    policy_id: str
    title: str
    section: str
    text: str
    audience: str
    version: str
    effective_date: str
    source: str
    meta: dict = field(default_factory=dict)

    @property
    def citation(self) -> str:
        return f"{self.policy_id} {self.title}, section \"{self.section}\" (v{self.version})"


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def parse(path: Path) -> list[Passage]:
    raw = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", raw, re.S)
    if not m:
        raise ValueError(f"{path.name}: missing front matter")
    meta, body = yaml.safe_load(m.group(1)), m.group(2)
    for key in ("policy_id", "title", "version", "effective_date", "audience", "owner"):
        if key not in meta:
            raise ValueError(f"{path.name}: front matter lacks {key}")
    parts = re.split(r"^## +(.+)$", body, flags=re.M)
    out = []
    for heading, text in zip(parts[1::2], parts[2::2]):
        text = " ".join(text.split())
        if text:
            out.append(Passage(pid=f"{meta['policy_id']}#{slug(heading)}", policy_id=meta["policy_id"], title=meta["title"],
                               section=heading.strip(), text=text, audience=meta["audience"], version=str(meta["version"]),
                               effective_date=str(meta["effective_date"]), source=path.name, meta=meta))
    return out


def load(folder: Path) -> list[Passage]:
    passages = []
    for p in sorted(folder.glob("*.md")):
        passages.extend(parse(p))
    ids = [p.pid for p in passages]
    dup = {i for i in ids if ids.count(i) > 1}
    if dup:
        raise ValueError(f"duplicate passage ids: {sorted(dup)}")
    return passages
