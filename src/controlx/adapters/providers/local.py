"""Local pack target.

Lets ControlX answer the core question - "can pack B carry pack A?" - with no
network, no keys, and a deterministic result. This is the golden path.
"""

from __future__ import annotations

from ...core.corpus import answer_from_pack
from ...core.models import Pack, Patch, PatchStatus
from ...core.patcher import apply_patch_to_pack
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
    can_complete=True,
    can_list_projects=True,
    can_write_instructions=True,
    can_upload_files=True,
    can_oauth=False,
    requires_inject=False,
    note="local vault pack; ControlX owns the files, so patches apply directly",
)


class LocalPackAdapter:
    """`pack:<slug>` targets. Answers are grounded retrieval over the pack corpus."""

    def __init__(self, pack: Pack, store=None) -> None:  # type: ignore[no-untyped-def]
        self.id = f"pack:{pack.slug}"
        self.pack = pack
        self.store = store

    async def health(self) -> Health:
        return Health(ok=True, detail=f"pack {self.pack.slug} v{self.pack.version}")

    async def complete(self, req: CompletionRequest) -> Completion:
        question = req.prompt.split("Question:", 1)[-1].strip() or req.prompt
        text, citations = answer_from_pack(self.pack, question, req.hints)
        return Completion(text=text, model="local-retrieval", citations=citations)

    async def list_remote_projects(self) -> list[RemoteRef]:
        return [RemoteRef(id=self.pack.slug, name=self.pack.name, kind="local_pack")]

    async def pull_project(self, ref: str) -> Pack:
        return self.pack

    async def apply_patch(self, ref: str | None, patch: Patch) -> ApplyResult:
        if self.store is None:
            raise CapabilityError("local adapter has no pack store bound")
        selected = {op.id for op in patch.ops if op.approved} or None
        updated, log = apply_patch_to_pack(self.pack, patch, only=selected)
        changed = any(line.startswith("apply") for line in log)
        if changed:
            self.store.save(updated, bump=True)
            self.pack = updated
        patch.status = PatchStatus.APPLIED
        detail = "\n".join(log) if log else "no operations"
        if not changed:
            detail += "\n(no changes: patch was already applied)"
        return ApplyResult(applied=changed, detail=detail)

    async def capabilities(self) -> Capabilities:
        return CAPS
