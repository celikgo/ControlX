"""Pure text helpers used by the audit engine.

Signal matching is deliberately literal: a probe's expected signal must appear
as a normalized substring of the answer. No fuzzy token soup - a false
"sufficient" is worse than a false "missing", because it silently tells the
user a project carries context that it does not.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_MD_NOISE = re.compile(r"[*`_#>\[\]]")
_WS = re.compile(r"\s+")
_PUNCT_EDGE = re.compile(r"^[\s.,;:!?-]+|[\s.,;:!?-]+$")
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_TOKEN = re.compile(r"[a-z0-9]{3,}")


def normalize(text: str) -> str:
    """Lowercase, drop markdown emphasis noise, collapse whitespace."""
    lowered = _MD_NOISE.sub(" ", text.lower())
    return _WS.sub(" ", lowered).strip()


def contains_signal(haystack: str, signal: str) -> bool:
    needle = _PUNCT_EDGE.sub("", normalize(signal))
    if not needle:
        return False
    return needle in normalize(haystack)


def tokens(text: str) -> set[str]:
    return set(_TOKEN.findall(normalize(text)))


@dataclass(frozen=True)
class Section:
    """A named chunk of a document. `source` is a stable citation label."""

    source: str
    heading: str
    body: str

    @property
    def text(self) -> str:
        return f"## {self.heading}\n\n{self.body}".strip() if self.heading else self.body.strip()


def split_sections(
    markdown: str, *, source: str, default_heading: str = "Overview"
) -> list[Section]:
    """Split a markdown document on ATX headings into citable sections."""
    sections: list[Section] = []
    heading = default_heading
    buf: list[str] = []

    def flush() -> None:
        body = "\n".join(buf).strip()
        if body or heading != default_heading:
            sections.append(Section(source=f"{source}#{heading}", heading=heading, body=body))

    for line in markdown.splitlines():
        match = _HEADING.match(line.rstrip())
        if match:
            flush()
            buf = []
            heading = match.group(2).strip()
        else:
            buf.append(line)
    flush()
    return [s for s in sections if s.body.strip() or s.heading != default_heading]


def heading_set(markdown: str) -> set[str]:
    return {
        m.group(2).strip().lower()
        for m in (_HEADING.match(line.rstrip()) for line in markdown.splitlines())
        if m
    }


def excerpt(text: str, limit: int = 400) -> str:
    flat = _WS.sub(" ", text).strip()
    return flat if len(flat) <= limit else flat[: limit - 1].rstrip() + "…"
