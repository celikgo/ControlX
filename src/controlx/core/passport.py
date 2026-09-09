"""Passport export.

Section language intentionally mirrors Context Passport (see NOTICE) so a
ControlX passport can be pasted into tools that already understand that shape.
"""

from __future__ import annotations

from .models import Audit, Pack


def render_passport(pack: Pack, audit: Audit | None = None) -> str:
    lines = [
        f"# ControlX Passport — {pack.slug} v{pack.version}",
        "",
        f"**Project:** {pack.name}  ",
        f"**Generated:** {pack.updated_at.isoformat()}",
        "",
        "## Standing instructions",
        "",
        pack.instructions.strip() or "_none_",
        "",
        "## Constraints",
        "",
    ]
    lines += [f"- **{c.key}**: {c.value}" for c in pack.constraints] or ["_none_"]

    lines += ["", "## Decisions", ""]
    lines += [
        f"- {d.date} — **{d.title}**" + (f": {d.body.strip()}" if d.body.strip() else "")
        for d in pack.decisions
    ] or ["_none recorded_"]

    lines += ["", "## Open questions", ""]
    lines += [f"- {q}" for q in pack.open_questions] or ["_none_"]

    lines += ["", "## Probe set", ""]
    if pack.probes:
        for probe in pack.probes:
            lines.append(f"- {probe.question}")
            for signal in probe.expected_signals:
                lines.append(f"  - expects: {signal}")
    else:
        lines.append("_none_")

    if audit is not None:
        lines += [
            "",
            "## Last audit",
            "",
            f"- target: `{audit.target_ref}`",
            f"- score: **{audit.score_pct}%**",
        ]
        lines += [f"- missing: {item}" for item in audit.missing_instructions]

    lines += [
        "",
        "## Resume prompt",
        "",
        "```text",
        f"You are continuing work on {pack.name} ({pack.slug} v{pack.version}).",
        "Adopt the standing instructions and constraints above as binding.",
        "Do not re-derive decisions already listed. Start by confirming the open",
        "questions that block the next step, then continue the work.",
        "```",
        "",
    ]
    return "\n".join(lines)


def render_inject_bundle(pack: Pack, patch_markdown: str | None = None) -> str:
    """Paste-ready block for provider UIs that have no write API."""
    lines = [
        f"===== ControlX inject bundle — {pack.slug} v{pack.version} =====",
        "",
        "STEP 1 — paste the block below into the project's custom instructions:",
        "",
        "-----8<----- BEGIN INSTRUCTIONS -----8<-----",
        pack.instructions.strip(),
        "",
        "Constraints:",
    ]
    lines += [f"- {c.key}: {c.value}" for c in pack.constraints] or ["- (none)"]
    lines += ["-----8<----- END INSTRUCTIONS -----8<-----", ""]

    if pack.knowledge:
        lines += ["STEP 2 — upload these files to the project's knowledge:", ""]
        lines += [
            f"  [ ] {doc.title}" + (f"  ({doc.path})" if doc.path else "") for doc in pack.knowledge
        ]
        lines.append("")
    if patch_markdown:
        lines += ["STEP 3 — the patch this bundle carries:", "", patch_markdown]
    return "\n".join(lines)
