"""ControlX domain model.

These names are stable and are the vocabulary of the whole product:
Workspace, Pack, PromptEntry, Probe, Bridge, Audit, ProbeResult, Patch, PatchOp.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .ids import new_id

Provider = Literal["openai", "anthropic", "xai", "local", "mcp"]
AuthMode = Literal["api_key", "oauth", "session"]
EndpointKind = Literal["project", "custom_gpt", "conversation", "agent", "local_pack"]
Direction = Literal["forward", "reverse", "bidirectional"]


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


# --------------------------------------------------------------------------- #
# Workspace
# --------------------------------------------------------------------------- #
class Workspace(Base):
    id: str = Field(default_factory=lambda: new_id("workspace"))
    name: str
    provider: Provider
    auth_mode: AuthMode = "api_key"
    endpoint_kind: EndpointKind = "project"
    remote_ref: str | None = None
    model: str | None = None
    account: str = "default"
    last_seen_at: datetime | None = None
    notes: str | None = None

    @property
    def ref(self) -> str:
        """Canonical target reference, e.g. `openai:default`."""
        return f"{self.provider}:{self.account}"


# --------------------------------------------------------------------------- #
# Pack parts
# --------------------------------------------------------------------------- #
class PromptEntry(Base):
    id: str = Field(default_factory=lambda: new_id("prompt"))
    title: str
    body: str
    variables: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    provider_tune: Provider | None = None


class Probe(Base):
    id: str = Field(default_factory=lambda: new_id("probe"))
    question: str
    expected_signals: list[str] = Field(default_factory=list)
    weight: float = 1.0
    source_pack_id: str | None = None
    generated: bool = False


class KnowledgeDoc(Base):
    id: str = Field(default_factory=lambda: new_id("knowledge"))
    title: str
    path: str | None = None
    text: str | None = None
    hash: str | None = None
    summary: str | None = None
    required: bool = True


class Constraint(Base):
    key: str
    value: str
    rationale: str | None = None


class Decision(Base):
    id: str = Field(default_factory=lambda: new_id("decision"))
    date: str
    title: str
    body: str = ""


class Pack(Base):
    """The canonical, versioned project brain. Provider projects are endpoints."""

    id: str = Field(default_factory=lambda: new_id("pack"))
    slug: str
    name: str
    instructions: str = ""
    constraints: list[Constraint] = Field(default_factory=list)
    prompts: list[PromptEntry] = Field(default_factory=list)
    knowledge: list[KnowledgeDoc] = Field(default_factory=list)
    probes: list[Probe] = Field(default_factory=list)
    decisions: list[Decision] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    provider_variants: dict[str, str] = Field(default_factory=dict)
    version: int = 1
    parent_version: int | None = None
    updated_at: datetime = Field(default_factory=utcnow)

    def constraint(self, key: str) -> Constraint | None:
        return next((c for c in self.constraints if c.key == key), None)


# --------------------------------------------------------------------------- #
# Bridges, audits, patches
# --------------------------------------------------------------------------- #
class Bridge(Base):
    id: str = Field(default_factory=lambda: new_id("bridge"))
    source_pack_id: str
    target_workspace_id: str
    direction: Direction = "forward"
    last_audit_id: str | None = None


class Verdict(StrEnum):
    SUFFICIENT = "sufficient"
    PARTIAL = "partial"
    MISSING = "missing"
    CONFLICT = "conflict"

    @property
    def credit(self) -> float:
        return {"sufficient": 1.0, "partial": 0.5, "missing": 0.0, "conflict": 0.0}[self.value]

    @property
    def glyph(self) -> str:
        return {"sufficient": "✓", "partial": "◐", "missing": "✗", "conflict": "⚠"}[self.value]


class ProbeResult(Base):
    probe_id: str
    question: str
    verdict: Verdict
    weight: float = 1.0
    target_answer_excerpt: str = ""
    rationale: str = ""
    matched_signals: list[str] = Field(default_factory=list)
    missing_signals: list[str] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)
    suggested_patch_ids: list[str] = Field(default_factory=list)


class Conflict(Base):
    key: str
    source_value: str
    target_value: str
    note: str = ""


class Audit(Base):
    id: str = Field(default_factory=lambda: new_id("audit"))
    bridge_id: str | None = None
    source_pack_id: str
    source_slug: str
    target_ref: str
    created_at: datetime = Field(default_factory=utcnow)
    score_pct: float = 0.0
    results: list[ProbeResult] = Field(default_factory=list)
    conflicts: list[Conflict] = Field(default_factory=list)
    missing_instructions: list[str] = Field(default_factory=list)
    missing_knowledge: list[str] = Field(default_factory=list)
    patch_id: str | None = None
    notes: str = ""

    @property
    def counts(self) -> dict[str, int]:
        out = {v.value: 0 for v in Verdict}
        for r in self.results:
            out[r.verdict.value] += 1
        return out


OpKind = Literal[
    "append_instruction",
    "replace_instruction_section",
    "add_prompt",
    "add_knowledge_manifest",
    "add_probe",
    "record_decision",
    "set_variant",
]


class PatchOp(Base):
    id: str = Field(default_factory=lambda: new_id("op"))
    op: OpKind
    target: str
    content: str
    reason: str = ""
    approved: bool = False


class PatchStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    APPLIED = "applied"
    REJECTED = "rejected"


class Patch(Base):
    id: str = Field(default_factory=lambda: new_id("patch"))
    audit_id: str
    target_ref: str
    status: PatchStatus = PatchStatus.DRAFT
    ops: list[PatchOp] = Field(default_factory=list)
    preview_markdown: str = ""
    applied_at: datetime | None = None
    apply_note: str = ""
