"""Honest fallbacks: what happens when the target cannot be written or probed."""

from __future__ import annotations

import pytest

from controlx.core.models import Patch, PatchOp
from controlx.errors import CapabilityError, NotFoundError
from controlx.services import add_workspace, apply_patch, audit


def _session_workspace(ctx):
    return add_workspace(
        ctx, provider="openai", name="ChatGPT / Nakitte", auth_mode="session", account="web"
    )


async def test_session_workspace_cannot_be_probed(ctx, complete_pack):
    ctx.store.save(complete_pack)
    _session_workspace(ctx)
    with pytest.raises(CapabilityError) as excinfo:
        await audit(ctx, source_slug="complete", target_ref="ChatGPT / Nakitte")
    assert "inject-only" in excinfo.value.message
    assert "pack:" in (excinfo.value.hint or "")


async def test_apply_to_a_non_writable_target_emits_an_inject_bundle(ctx, complete_pack):
    ctx.store.save(complete_pack)
    workspace = _session_workspace(ctx)

    result, _ = await audit(ctx, source_slug="complete", target_ref="pack:complete")
    patch = Patch(
        audit_id=result.id,
        target_ref=workspace.ref,
        ops=[
            PatchOp(op="append_instruction", target="instructions.md#Beta", content="## Beta\n\nx")
        ],
        preview_markdown="# preview",
    )
    ctx.index.save_patch(patch)

    _, applied = await apply_patch(ctx, patch.id, approve=True)

    assert not applied.applied
    assert "NOTHING was changed remotely" in applied.detail
    assert applied.inject_path and "inject-" in applied.inject_path
    bundle = applied.inject_bundle or ""
    assert "BEGIN INSTRUCTIONS" in bundle
    assert "widgets are immutable" in bundle


def test_target_resolution(ctx, complete_pack):
    ctx.store.save(complete_pack)
    assert ctx.resolve_target("pack:complete").is_local
    assert ctx.resolve_target("complete").ref == "pack:complete"  # bare slug works too

    workspace = _session_workspace(ctx)
    resolved = ctx.resolve_target(workspace.name)
    assert resolved.workspace is not None and resolved.pack is None

    implicit = ctx.resolve_target("anthropic:default")
    assert implicit.ref == "anthropic:default"

    with pytest.raises(NotFoundError):
        ctx.resolve_target("gemini:default")


async def test_local_target_capabilities_allow_direct_writes(ctx, complete_pack):
    ctx.store.save(complete_pack)
    caps = await ctx.resolve_target("pack:complete").adapter.capabilities()
    assert caps.can_write_instructions and not caps.requires_inject
