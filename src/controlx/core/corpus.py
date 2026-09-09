"""Turn a Pack into citable sections and retrieve from them.

This is the offline half of ControlX: when the audit target is another local
pack, "asking" it means retrieving from its own corpus.
"""

from __future__ import annotations

from .models import Pack
from .textutil import Section, contains_signal, split_sections, tokens


def pack_sections(pack: Pack) -> list[Section]:
    sections: list[Section] = list(split_sections(pack.instructions, source="instructions.md"))

    if pack.constraints:
        body = "\n".join(
            f"- {c.key}: {c.value}" + (f" ({c.rationale})" if c.rationale else "")
            for c in pack.constraints
        )
        sections.append(Section("pack.yaml#constraints", "Constraints", body))

    for prompt in pack.prompts:
        sections.append(Section(f"prompts/{prompt.id}", prompt.title, prompt.body))

    for doc in pack.knowledge:
        body = doc.text or doc.summary or ""
        if body:
            sections.append(Section(f"knowledge/{doc.id}", doc.title, body))

    for decision in pack.decisions:
        sections.append(
            Section(f"decisions/{decision.id}", f"{decision.date} {decision.title}", decision.body)
        )

    if pack.open_questions:
        sections.append(
            Section(
                "pack.yaml#open_questions",
                "Open questions",
                "\n".join(f"- {q}" for q in pack.open_questions),
            )
        )
    return sections


def retrieve(
    sections: list[Section], query: str, hints: list[str] | None = None, k: int = 6
) -> list[Section]:
    """Rank sections by explicit signal hits first, then term overlap."""
    hints = hints or []
    query_tokens = tokens(query)
    scored: list[tuple[float, int, Section]] = []
    for idx, section in enumerate(sections):
        score = 0.0
        for hint in hints:
            if contains_signal(section.text, hint):
                score += 100.0
        score += len(query_tokens & tokens(section.text))
        if score > 0:
            scored.append((score, -idx, section))
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [section for _, _, section in scored[:k]]


def answer_from_pack(
    pack: Pack, question: str, hints: list[str] | None = None
) -> tuple[str, list[str]]:
    """Best-effort grounded answer plus citations, or an explicit INSUFFICIENT."""
    hits = retrieve(pack_sections(pack), question, hints)
    if not hits:
        return (
            "INSUFFICIENT: this project has no context covering the question.",
            [],
        )
    blocks = [f"[{section.source}]\n{section.text}" for section in hits]
    return "\n\n".join(blocks), [section.source for section in hits]
