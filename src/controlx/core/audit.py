"""The audit engine: probes in, sufficiency score and a patch out.

Algorithm (v0.1) is documented in docs/AUDIT.md. Summary:
  1. take source probes (or generate drafts from the instructions)
  2. ask the target adapter each probe independently
  3. judge each answer -> sufficient | partial | missing | conflict
  4. score = weighted average of verdict credit
  5. compose a patch from the missing signals; never auto-apply
"""

from __future__ import annotations

import json

from .ids import new_id
from .models import (
    Audit,
    Conflict,
    Pack,
    Patch,
    PatchOp,
    Probe,
    ProbeResult,
    Verdict,
)
from .ports import Completion, CompletionRequest, Judge, ProviderAdapter
from .textutil import contains_signal, excerpt, heading_set, split_sections

PROBE_SYSTEM = (
    "You are being evaluated as an AI workspace. Answer only from the project context "
    "available to you. Do not use outside knowledge. If the context is insufficient, "
    "reply with the single word INSUFFICIENT followed by a list of what is missing."
)

PROBE_TEMPLATE = """You are being evaluated as workspace {target}.
Answer only from your available project context.
If the context is insufficient, say INSUFFICIENT and list what is missing.

Question: {question}"""

MAX_GENERATED_PROBES = 8


# --------------------------------------------------------------------------- #
# Probe generation
# --------------------------------------------------------------------------- #
def generate_probes(pack: Pack, limit: int = MAX_GENERATED_PROBES) -> list[Probe]:
    """Draft probes from a pack's instruction headings. Marked generated=True."""
    probes: list[Probe] = []
    for section in split_sections(pack.instructions, source="instructions.md"):
        if not section.body.strip():
            continue
        signals = _salient_lines(section.body)
        probes.append(
            Probe(
                question=f"What does this project specify about {section.heading.lower()}?",
                expected_signals=signals,
                source_pack_id=pack.id,
                generated=True,
            )
        )
        if len(probes) >= limit:
            break
    return probes


def _salient_lines(body: str, limit: int = 2) -> list[str]:
    lines = [line.strip(" -*\t") for line in body.splitlines()]
    candidates = [line for line in lines if 12 <= len(line) <= 120]
    return candidates[:limit]


# --------------------------------------------------------------------------- #
# Judging
# --------------------------------------------------------------------------- #
class HeuristicJudge:
    """Deterministic, offline, explainable. The default judge.

    A signal counts as covered only when it appears as a normalized substring of
    the answer. Strict on purpose: a false 'sufficient' is the expensive mistake.
    """

    id = "heuristic"

    async def judge(self, probe: Probe, answer: Completion) -> ProbeResult:
        text = answer.text or ""
        matched = [s for s in probe.expected_signals if contains_signal(text, s)]
        missing = [s for s in probe.expected_signals if s not in matched]
        insufficient = "insufficient" in text.lower()[:200]

        if probe.expected_signals:
            if not matched:
                verdict = Verdict.MISSING
            elif missing:
                verdict = Verdict.PARTIAL
            else:
                verdict = Verdict.SUFFICIENT
        else:
            verdict = Verdict.MISSING if insufficient or not text.strip() else Verdict.PARTIAL

        rationale = _rationale(verdict, matched, missing, insufficient)
        return ProbeResult(
            probe_id=probe.id,
            question=probe.question,
            verdict=verdict,
            weight=probe.weight,
            target_answer_excerpt=excerpt(text),
            rationale=rationale,
            matched_signals=matched,
            missing_signals=missing,
            citations=list(answer.citations),
        )


def _rationale(verdict: Verdict, matched: list[str], missing: list[str], insufficient: bool) -> str:
    if verdict is Verdict.SUFFICIENT:
        return f"target covers all {len(matched)} expected signal(s)"
    if verdict is Verdict.PARTIAL:
        return f"covers {len(matched)}, missing: " + "; ".join(missing)
    if missing:
        return "target covers none of: " + "; ".join(missing)
    return "target declared the context insufficient" if insufficient else "no usable answer"


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #
def score(results: list[ProbeResult]) -> float:
    total_weight = sum(r.weight for r in results)
    if total_weight <= 0:
        return 0.0
    earned = sum(r.verdict.credit * r.weight for r in results)
    return round(100.0 * earned / total_weight, 1)


def detect_conflicts(source: Pack, target: Pack | None) -> list[Conflict]:
    """Same constraint key, different value = a real contradiction between projects."""
    if target is None:
        return []
    conflicts: list[Conflict] = []
    for constraint in source.constraints:
        other = target.constraint(constraint.key)
        if other is not None and other.value.strip().lower() != constraint.value.strip().lower():
            conflicts.append(
                Conflict(
                    key=constraint.key,
                    source_value=constraint.value,
                    target_value=other.value,
                    note="source and target disagree; resolve before applying",
                )
            )
    return conflicts


# --------------------------------------------------------------------------- #
# Running an audit
# --------------------------------------------------------------------------- #
async def run_audit(
    *,
    source: Pack,
    target_adapter: ProviderAdapter,
    target_ref: str,
    target_pack: Pack | None = None,
    judge: Judge | None = None,
    bridge_id: str | None = None,
    model: str | None = None,
) -> Audit:
    judge = judge or HeuristicJudge()
    probes = source.probes or generate_probes(source)

    results: list[ProbeResult] = []
    for probe in probes:
        request = CompletionRequest(
            prompt=PROBE_TEMPLATE.format(target=target_ref, question=probe.question),
            system=PROBE_SYSTEM,
            model=model,
            hints=list(probe.expected_signals),
        )
        answer = await target_adapter.complete(request)
        results.append(await judge.judge(probe, answer))

    conflicts = detect_conflicts(source, target_pack)
    _mark_conflicted(results, conflicts, source)

    audit = Audit(
        bridge_id=bridge_id,
        source_pack_id=source.id,
        source_slug=source.slug,
        target_ref=target_ref,
        score_pct=score(results),
        results=results,
        conflicts=conflicts,
        missing_instructions=_missing_instructions(source, target_pack, results),
        missing_knowledge=_missing_knowledge(source, target_pack, results),
        notes=f"{len(probes)} probe(s); judge={getattr(judge, 'id', 'llm')}",
    )
    return audit


def _mark_conflicted(results: list[ProbeResult], conflicts: list[Conflict], source: Pack) -> None:
    """A probe whose signals collide with a conflicting constraint is a conflict, not a miss."""
    for conflict in conflicts:
        for result in results:
            if any(
                contains_signal(conflict.source_value, signal)
                or contains_signal(signal, conflict.source_value)
                for signal in result.matched_signals + result.missing_signals
            ):
                result.verdict = Verdict.CONFLICT
                result.rationale = (
                    f"{result.rationale} | conflict on '{conflict.key}': "
                    f"source={conflict.source_value!r} target={conflict.target_value!r}"
                )


def _failing(results: list[ProbeResult]) -> list[ProbeResult]:
    return [r for r in results if r.verdict is not Verdict.SUFFICIENT]


def _missing_instructions(
    source: Pack, target: Pack | None, results: list[ProbeResult]
) -> list[str]:
    sections = split_sections(source.instructions, source="instructions.md")
    target_headings = heading_set(target.instructions) if target else set()
    missing: list[str] = []
    for result in _failing(results):
        for signal in result.missing_signals:
            for section in sections:
                if (
                    contains_signal(section.text, signal)
                    and section.heading.lower() not in target_headings
                    and section.heading not in missing
                ):
                    missing.append(section.heading)
    return missing


def _missing_knowledge(source: Pack, target: Pack | None, results: list[ProbeResult]) -> list[str]:
    if not source.knowledge:
        return []
    target_titles = {doc.title.lower() for doc in target.knowledge} if target else set()
    return [doc.title for doc in source.knowledge if doc.title.lower() not in target_titles]


# --------------------------------------------------------------------------- #
# Patch composition
# --------------------------------------------------------------------------- #
def compose_patch(*, audit: Audit, source: Pack, target_pack: Pack | None) -> Patch:
    """Turn gaps into concrete, reviewable operations. Nothing is applied here."""
    patch = Patch(id=new_id("patch"), audit_id=audit.id, target_ref=audit.target_ref)
    sections = split_sections(source.instructions, source="instructions.md")
    target_headings = heading_set(target_pack.instructions) if target_pack else set()
    target_questions = (
        {p.question.strip().lower() for p in target_pack.probes} if target_pack else set()
    )
    target_prompts = (
        {p.title.strip().lower() for p in target_pack.prompts} if target_pack else set()
    )
    seen_targets: set[str] = set()

    for result in _failing(audit.results):
        for signal in result.missing_signals:
            section = next((s for s in sections if contains_signal(s.text, signal)), None)
            if section is not None:
                key = f"instructions.md#{section.heading}"
                if key in seen_targets:
                    _link(result, patch, key)
                    continue
                seen_targets.add(key)
                op = PatchOp(
                    op=(
                        "replace_instruction_section"
                        if section.heading.lower() in target_headings
                        else "append_instruction"
                    ),
                    target=key,
                    content=section.text,
                    reason=f"probe '{excerpt(result.question, 80)}' misses: {signal}",
                )
                patch.ops.append(op)
                result.suggested_patch_ids.append(op.id)
                continue

            doc = next(
                (
                    d
                    for d in source.knowledge
                    if contains_signal((d.text or "") + " " + (d.summary or ""), signal)
                ),
                None,
            )
            if doc is not None:
                key = f"knowledge/{doc.title}"
                if key in seen_targets:
                    _link(result, patch, key)
                    continue
                seen_targets.add(key)
                op = PatchOp(
                    op="add_knowledge_manifest",
                    target=key,
                    content=(doc.summary or excerpt(doc.text or "", 600)),
                    reason=f"signal '{signal}' lives in source knowledge doc '{doc.title}'",
                )
                patch.ops.append(op)
                result.suggested_patch_ids.append(op.id)

        probe = next((p for p in source.probes if p.id == result.probe_id), None)
        if probe is not None and probe.question.strip().lower() not in target_questions:
            op = PatchOp(
                op="add_probe",
                target=probe.id,
                content=json.dumps(
                    {
                        "question": probe.question,
                        "expected_signals": probe.expected_signals,
                        "weight": probe.weight,
                        "source_pack_id": source.id,
                    },
                    indent=2,
                    ensure_ascii=False,
                ),
                reason="target should own the same sufficiency test",
            )
            patch.ops.append(op)
            result.suggested_patch_ids.append(op.id)

    for prompt in source.prompts:
        if prompt.title.strip().lower() in target_prompts:
            continue
        if any(
            contains_signal(prompt.body, signal)
            for result in _failing(audit.results)
            for signal in result.missing_signals
        ):
            patch.ops.append(
                PatchOp(
                    op="add_prompt",
                    target=prompt.title,
                    content=prompt.body,
                    reason="prompt encodes a missing signal",
                )
            )

    for conflict in audit.conflicts:
        patch.ops.append(
            PatchOp(
                op="record_decision",
                target=f"conflict-{conflict.key}",
                content=(
                    f"Conflict on '{conflict.key}'.\n"
                    f"- source: {conflict.source_value}\n"
                    f"- target: {conflict.target_value}\n\n"
                    "ControlX does not silently overwrite a contradiction. "
                    "Decide the winner, then edit the losing pack."
                ),
                reason="terminology or rule contradiction between projects",
            )
        )

    patch.preview_markdown = render_preview(audit, patch)
    audit.patch_id = patch.id
    return patch


def _link(result: ProbeResult, patch: Patch, target_key: str) -> None:
    op = next((o for o in patch.ops if o.target == target_key), None)
    if op is not None and op.id not in result.suggested_patch_ids:
        result.suggested_patch_ids.append(op.id)


def render_preview(audit: Audit, patch: Patch) -> str:
    lines = [
        f"# Patch {patch.id}",
        "",
        f"source: `{audit.source_slug}`  →  target: `{audit.target_ref}`",
        f"audit: `{audit.id}`  score: **{audit.score_pct}%**  ops: **{len(patch.ops)}**",
        "",
        "## Probe results",
        "",
    ]
    for result in audit.results:
        lines.append(f"- {result.verdict.glyph} `{result.verdict.value}` {result.question}")
        if result.rationale:
            lines.append(f"  - {result.rationale}")
    if audit.conflicts:
        lines += ["", "## Conflicts", ""]
        for conflict in audit.conflicts:
            lines.append(
                f"- ⚠ **{conflict.key}**: source `{conflict.source_value}` vs "
                f"target `{conflict.target_value}`"
            )
    lines += ["", "## Operations", ""]
    if not patch.ops:
        lines.append("_No operations. The target already carries this pack._")
    for index, op in enumerate(patch.ops, start=1):
        lines += [
            f"### {index}. `{op.op}` → `{op.target}`",
            f"_{op.reason}_",
            "",
            "```json" if op.op == "add_probe" else "```markdown",
            op.content.strip(),
            "```",
            "",
        ]
    return "\n".join(lines).rstrip() + "\n"
