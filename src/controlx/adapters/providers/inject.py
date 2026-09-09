"""Inject-only target: a provider UI with no public write API.

ControlX refuses to pretend. An inject workspace can receive a paste bundle and
an upload checklist; it cannot be probed automatically.
"""

from __future__ import annotations

from ...core.models import Pack, Patch
from ...core.ports import (
    ApplyResult,
    Capabilities,
    Completion,
    CompletionRequest,
    Health,
    RemoteRef,
)
from ...errors import CapabilityError

CAPS = Capabilities(
    can_complete=False,
    can_list_projects=False,
    can_write_instructions=False,
    can_upload_files=False,
    can_oauth=False,
    requires_inject=True,
    note="manual paste target: LIMITED. No supported API for reads or writes.",
)


class InjectAdapter:
    def __init__(self, label: str) -> None:
        self.id = label

    async def health(self) -> Health:
        return Health(ok=True, detail="inject-only target (manual paste)")

    async def complete(self, req: CompletionRequest) -> Completion:
        raise CapabilityError(
            f"'{self.id}' is an inject-only workspace: probes cannot be run automatically",
            hint=(
                "add an API-backed workspace for the same provider "
                "(`controlx auth add --provider <p> --mode api_key`), or audit against a local "
                "pack target (`--target pack:<slug>`)"
            ),
        )

    async def list_remote_projects(self) -> list[RemoteRef]:
        return []

    async def pull_project(self, ref: str) -> Pack:
        raise CapabilityError(f"'{self.id}' cannot be read programmatically")

    async def apply_patch(self, ref: str | None, patch: Patch) -> ApplyResult:
        return ApplyResult(
            applied=False,
            detail=f"'{self.id}' is inject-only; nothing was written remotely",
        )

    async def capabilities(self) -> Capabilities:
        return CAPS
