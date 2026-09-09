"""Minimal YAML front-matter reader/writer (no extra dependency)."""

from __future__ import annotations

from typing import Any

import yaml

DELIM = "---"


def parse(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith(DELIM):
        return {}, text
    parts = text.split("\n")
    if parts[0].strip() != DELIM:
        return {}, text
    for index in range(1, len(parts)):
        if parts[index].strip() == DELIM:
            meta = yaml.safe_load("\n".join(parts[1:index])) or {}
            body = "\n".join(parts[index + 1 :]).lstrip("\n")
            return dict(meta), body
    return {}, text


def dump(meta: dict[str, Any], body: str) -> str:
    head = yaml.safe_dump(meta, sort_keys=True, allow_unicode=True).strip()
    return f"{DELIM}\n{head}\n{DELIM}\n\n{body.rstrip()}\n"
