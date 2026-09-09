"""Ports (hexagonal boundaries). `core` never imports an adapter."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from .models import Audit, Pack, Patch, Probe, ProbeResult, Workspace


@dataclass(slots=True)
class Capabilities:
    """What an endpoint can actually do. Drives honest fallbacks."""

    can_complete: bool = True
    can_list_projects: bool = False
    can_write_instructions: bool = False
    can_upload_files: bool = False
    can_oauth: bool = False
    requires_inject: bool = True
    note: str = ""


@dataclass(slots=True)
class Health:
    ok: bool
    detail: str = ""


@dataclass(slots=True)
class CompletionRequest:
    prompt: str
    system: str | None = None
    model: str | None = None
    max_tokens: int = 900
    temperature: float = 0.0
    json_mode: bool = False
    # Retrieval hints let offline pack targets answer from their own corpus.
    hints: list[str] = field(default_factory=list)


@dataclass(slots=True)
class Completion:
    text: str
    model: str = ""
    citations: list[str] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)


@dataclass(slots=True)
class RemoteRef:
    id: str
    name: str
    kind: str = "project"


@dataclass(slots=True)
class ApplyResult:
    applied: bool
    detail: str
    inject_bundle: str | None = None
    inject_path: str | None = None


@runtime_checkable
class ProviderAdapter(Protocol):
    """Every target - API, local pack, or paste-only web project - is one of these."""

    id: str

    async def health(self) -> Health: ...

    async def complete(self, req: CompletionRequest) -> Completion: ...

    async def list_remote_projects(self) -> list[RemoteRef]: ...

    async def pull_project(self, ref: str) -> Pack: ...

    async def apply_patch(self, ref: str | None, patch: Patch) -> ApplyResult: ...

    async def capabilities(self) -> Capabilities: ...


@runtime_checkable
class Judge(Protocol):
    """Turns (probe, answer) into a verdict."""

    async def judge(self, probe: Probe, answer: Completion) -> ProbeResult: ...


class PackStorePort(Protocol):
    def list_packs(self) -> list[str]: ...
    def load(self, slug: str) -> Pack: ...
    def save(self, pack: Pack, *, bump: bool = False) -> Pack: ...
    def exists(self, slug: str) -> bool: ...


class IndexPort(Protocol):
    def upsert_workspace(self, ws: Workspace) -> None: ...
    def list_workspaces(self) -> list[Workspace]: ...
    def save_audit(self, audit: Audit) -> None: ...
    def save_patch(self, patch: Patch) -> None: ...
