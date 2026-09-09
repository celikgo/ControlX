"""The golden path: complete pack vs incomplete pack, no network, no keys."""

from __future__ import annotations

import pytest

from controlx.core.models import Verdict
from controlx.services import apply_patch, audit


async def test_incomplete_target_scores_below_threshold(ctx, complete_pack, incomplete_pack):
    ctx.store.save(complete_pack)
    ctx.store.save(incomplete_pack)

    result, patch = await audit(ctx, source_slug="complete", target_ref="pack:incomplete")

    assert result.score_pct < 70
    assert result.score_pct == 50.0  # one of two probes covered
    verdicts = {r.question: r.verdict for r in result.results}
    assert verdicts["What is the alpha rule?"] is Verdict.SUFFICIENT
    assert verdicts["What is the beta rule?"] is Verdict.MISSING
    assert result.missing_instructions == ["Beta"]
    assert any(op.op == "append_instruction" and "Beta" in op.target for op in patch.ops)


async def test_apply_then_reaudit_raises_the_score(ctx, complete_pack, incomplete_pack):
    ctx.store.save(complete_pack)
    ctx.store.save(incomplete_pack)
    before, patch = await audit(ctx, source_slug="complete", target_ref="pack:incomplete")

    _, applied = await apply_patch(ctx, patch.id, approve=True)
    assert applied.applied

    after, _ = await audit(ctx, source_slug="complete", target_ref="pack:incomplete")
    assert after.score_pct == 100.0
    assert after.score_pct > before.score_pct
    assert ctx.store.load("incomplete").version == 2


async def test_apply_is_idempotent(ctx, complete_pack, incomplete_pack):
    ctx.store.save(complete_pack)
    ctx.store.save(incomplete_pack)
    _, patch = await audit(ctx, source_slug="complete", target_ref="pack:incomplete")
    await apply_patch(ctx, patch.id, approve=True)
    version_after_first = ctx.store.load("incomplete").version

    _, second = await apply_patch(ctx, patch.id, approve=True)
    assert not second.applied
    assert "already applied" in second.detail
    assert ctx.store.load("incomplete").version == version_after_first


async def test_apply_requires_approval(ctx, complete_pack, incomplete_pack):
    from controlx.errors import UserError

    ctx.store.save(complete_pack)
    ctx.store.save(incomplete_pack)
    _, patch = await audit(ctx, source_slug="complete", target_ref="pack:incomplete")
    with pytest.raises(UserError):
        await apply_patch(ctx, patch.id, approve=False)
    assert ctx.store.load("incomplete").version == 1


async def test_selective_op_approval_applies_only_that_op(ctx, complete_pack, incomplete_pack):
    ctx.store.save(complete_pack)
    ctx.store.save(incomplete_pack)
    _, patch = await audit(ctx, source_slug="complete", target_ref="pack:incomplete")
    instruction_op = next(op for op in patch.ops if op.op == "append_instruction")

    await apply_patch(ctx, patch.id, ops=[instruction_op.id])
    patched = ctx.store.load("incomplete")
    assert "trace id" in patched.instructions
    assert patched.probes == []  # the add_probe op was not selected


async def test_conflict_is_flagged_and_never_auto_resolved(ctx, complete_pack, conflicting_pack):
    ctx.store.save(complete_pack)
    ctx.store.save(conflicting_pack)
    complete_pack.probes[0].expected_signals.append("REST only")
    complete_pack.instructions += "\n## API style\n\n- REST only over JSON.\n"
    ctx.store.save(complete_pack)

    result, patch = await audit(ctx, source_slug="complete", target_ref="pack:conflicting")

    assert [c.key for c in result.conflicts] == ["api_style"]
    assert any(r.verdict is Verdict.CONFLICT for r in result.results)
    assert any(op.op == "record_decision" for op in patch.ops)

    await apply_patch(ctx, patch.id, approve=True)
    after = ctx.store.load("conflicting")
    # the contradicting constraint survives: resolving it is a human decision
    assert after.constraint("api_style").value == "GraphQL first"
    assert any("conflict" in d.title for d in after.decisions)


async def test_shipped_demo_packs_reproduce_the_readme_numbers(demo_ctx):
    before, patch = await audit(demo_ctx, source_slug="demo-service", target_ref="pack:demo-thin")
    assert before.score_pct == 41.7
    assert "Auth token refresh" in before.missing_instructions
    assert "Deploy checklist" in before.missing_instructions

    await apply_patch(demo_ctx, patch.id, approve=True)
    after, _ = await audit(demo_ctx, source_slug="demo-service", target_ref="pack:demo-thin")
    assert after.score_pct == 83.3
    assert [c.key for c in after.conflicts] == ["api_style"]


async def test_audit_generates_probes_when_the_source_has_none(ctx, incomplete_pack):
    ctx.store.save(incomplete_pack)
    ctx.store.create("empty-target", template=False)
    result, _ = await audit(ctx, source_slug="incomplete", target_ref="pack:empty-target")
    assert result.results
    assert all(r.verdict is not Verdict.SUFFICIENT for r in result.results)
