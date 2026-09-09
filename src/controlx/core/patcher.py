"""Apply a Patch to a Pack. Pure: takes a Pack, returns a new Pack + a log.

Idempotent by construction - re-applying a patch is a no-op, so a rerun after a
crash cannot duplicate instructions.
"""

from __future__ import annotations

import json
from datetime import date

from .models import Decision, KnowledgeDoc, Pack, Patch, PatchOp, Probe, PromptEntry
from .textutil import heading_set, normalize, split_sections


def apply_patch_to_pack(
    pack: Pack, patch: Patch, *, only: set[str] | None = None
) -> tuple[Pack, list[str]]:
    updated = pack.model_copy(deep=True)
    log: list[str] = []
    for op in patch.ops:
        if only is not None and op.id not in only:
            log.append(f"skip   {op.op} {op.target} (not selected)")
            continue
        log.append(_apply_op(updated, op))
    return updated, log


def _apply_op(pack: Pack, op: PatchOp) -> str:
    handler = {
        "append_instruction": _append_instruction,
        "replace_instruction_section": _replace_instruction,
        "add_prompt": _add_prompt,
        "add_knowledge_manifest": _add_knowledge,
        "add_probe": _add_probe,
        "record_decision": _record_decision,
        "set_variant": _set_variant,
    }[op.op]
    return handler(pack, op)


def _heading_of(target: str) -> str:
    return target.split("#", 1)[-1].strip()


def _append_instruction(pack: Pack, op: PatchOp) -> str:
    heading = _heading_of(op.target)
    if normalize(op.content) in normalize(pack.instructions):
        return f"skip   append_instruction {heading} (already present)"
    if heading.lower() in heading_set(pack.instructions):
        return _replace_instruction(pack, op)
    body = op.content.strip()
    if not body.lstrip().startswith("#"):
        body = f"## {heading}\n{body}"
    pack.instructions = (pack.instructions.rstrip() + "\n\n" + body + "\n").lstrip("\n")
    return f"apply  append_instruction {heading}"


def _replace_instruction(pack: Pack, op: PatchOp) -> str:
    heading = _heading_of(op.target)
    sections = split_sections(pack.instructions, source="instructions.md")
    if not sections:
        return _append_instruction(pack, op)
    rebuilt: list[str] = []
    replaced = False
    for section in sections:
        if section.heading.lower() == heading.lower():
            rebuilt.append(op.content.strip())
            replaced = True
        else:
            rebuilt.append(section.text)
    if not replaced:
        return _append_instruction(pack, op)
    pack.instructions = "\n\n".join(rebuilt).strip() + "\n"
    return f"apply  replace_instruction_section {heading}"


def _add_prompt(pack: Pack, op: PatchOp) -> str:
    if any(p.title.strip().lower() == op.target.strip().lower() for p in pack.prompts):
        return f"skip   add_prompt {op.target} (already present)"
    pack.prompts.append(PromptEntry(title=op.target, body=op.content))
    return f"apply  add_prompt {op.target}"


def _add_knowledge(pack: Pack, op: PatchOp) -> str:
    title = op.target.split("/", 1)[-1]
    if any(doc.title.strip().lower() == title.strip().lower() for doc in pack.knowledge):
        return f"skip   add_knowledge_manifest {title} (already present)"
    pack.knowledge.append(
        KnowledgeDoc(
            title=title,
            summary=op.content.strip(),
            text=(
                f"# {title}\n\nNEEDS_UPLOAD — summary carried by ControlX:"
                f"\n\n{op.content.strip()}\n"
            ),
            required=True,
        )
    )
    return f"apply  add_knowledge_manifest {title} (marked NEEDS_UPLOAD)"


def _add_probe(pack: Pack, op: PatchOp) -> str:
    try:
        data = json.loads(op.content)
    except json.JSONDecodeError:
        data = {"question": op.content.strip(), "expected_signals": []}
    question = str(data.get("question", "")).strip()
    if not question:
        return "skip   add_probe (empty question)"
    if any(p.question.strip().lower() == question.lower() for p in pack.probes):
        return f"skip   add_probe {question[:40]} (already present)"
    pack.probes.append(
        Probe(
            question=question,
            expected_signals=list(data.get("expected_signals", [])),
            weight=float(data.get("weight", 1.0)),
            source_pack_id=data.get("source_pack_id"),
        )
    )
    return f"apply  add_probe {question[:40]}"


def _record_decision(pack: Pack, op: PatchOp) -> str:
    title = op.target
    if any(d.title.strip().lower() == title.strip().lower() for d in pack.decisions):
        return f"skip   record_decision {title} (already recorded)"
    pack.decisions.append(
        Decision(date=date.today().isoformat(), title=title, body=op.content.strip())
    )
    return f"apply  record_decision {title}"


def _set_variant(pack: Pack, op: PatchOp) -> str:
    provider = _heading_of(op.target)
    if pack.provider_variants.get(provider, "").strip() == op.content.strip():
        return f"skip   set_variant {provider} (unchanged)"
    pack.provider_variants[provider] = op.content
    return f"apply  set_variant {provider}"
