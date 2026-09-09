"""Short, prefixed, sortable-enough identifiers."""

from __future__ import annotations

import re
import uuid

PREFIXES = {
    "pack": "pak",
    "prompt": "pmt",
    "probe": "prb",
    "knowledge": "knw",
    "decision": "dec",
    "workspace": "wsp",
    "bridge": "brg",
    "audit": "aud",
    "patch": "pat",
    "op": "op",
}


def new_id(kind: str) -> str:
    prefix = PREFIXES.get(kind, kind)
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(text: str, *, max_len: int = 48) -> str:
    slug = _SLUG_RE.sub("-", text.strip().lower()).strip("-")
    return slug[:max_len] or "untitled"
