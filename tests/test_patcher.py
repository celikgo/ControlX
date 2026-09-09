import json

from controlx.core.models import Pack, Patch, PatchOp
from controlx.core.patcher import apply_patch_to_pack


def pack() -> Pack:
    return Pack(slug="p", name="P", instructions="## Alpha\n\n- one\n")


def patch_with(*ops: PatchOp) -> Patch:
    return Patch(audit_id="aud_x", target_ref="pack:p", ops=list(ops))


def test_append_instruction_adds_a_section():
    updated, log = apply_patch_to_pack(
        pack(),
        patch_with(
            PatchOp(
                op="append_instruction", target="instructions.md#Beta", content="## Beta\n\n- two"
            )
        ),
    )
    assert "## Beta" in updated.instructions
    assert log[0].startswith("apply")


def test_append_instruction_is_idempotent():
    op = PatchOp(op="append_instruction", target="instructions.md#Beta", content="## Beta\n\n- two")
    once, _ = apply_patch_to_pack(pack(), patch_with(op))
    twice, log = apply_patch_to_pack(once, patch_with(op))
    assert twice.instructions == once.instructions
    assert log[0].startswith("skip")


def test_append_on_an_existing_heading_replaces_it():
    op = PatchOp(
        op="append_instruction", target="instructions.md#Alpha", content="## Alpha\n\n- one\n- two"
    )
    updated, log = apply_patch_to_pack(pack(), patch_with(op))
    assert updated.instructions.count("## Alpha") == 1
    assert "- two" in updated.instructions
    assert "replace_instruction_section" in log[0]


def test_add_probe_reads_json_payload():
    payload = json.dumps({"question": "why?", "expected_signals": ["because"], "weight": 2.0})
    updated, _ = apply_patch_to_pack(
        pack(), patch_with(PatchOp(op="add_probe", target="prb_1", content=payload))
    )
    assert updated.probes[0].question == "why?"
    assert updated.probes[0].expected_signals == ["because"]
    assert updated.probes[0].weight == 2.0


def test_add_probe_tolerates_plain_text():
    updated, _ = apply_patch_to_pack(
        pack(), patch_with(PatchOp(op="add_probe", target="prb_1", content="plain question"))
    )
    assert updated.probes[0].question == "plain question"


def test_knowledge_manifest_is_marked_needs_upload():
    updated, _ = apply_patch_to_pack(
        pack(),
        patch_with(
            PatchOp(op="add_knowledge_manifest", target="knowledge/Retention", content="90 days")
        ),
    )
    doc = updated.knowledge[0]
    assert doc.title == "Retention"
    assert "NEEDS_UPLOAD" in (doc.text or "")


def test_record_decision_and_set_variant():
    updated, _ = apply_patch_to_pack(
        pack(),
        patch_with(
            PatchOp(op="record_decision", target="conflict-api", content="pick one"),
            PatchOp(op="set_variant", target="variants#anthropic", content="be terse"),
        ),
    )
    assert updated.decisions[0].title == "conflict-api"
    assert updated.provider_variants["anthropic"] == "be terse"


def test_unselected_ops_are_skipped():
    keep = PatchOp(op="add_prompt", target="Keep", content="body")
    drop = PatchOp(op="add_prompt", target="Drop", content="body")
    updated, log = apply_patch_to_pack(pack(), patch_with(keep, drop), only={keep.id})
    assert [p.title for p in updated.prompts] == ["Keep"]
    assert "not selected" in log[1]


def test_source_pack_is_never_mutated():
    original = pack()
    apply_patch_to_pack(
        original,
        patch_with(PatchOp(op="append_instruction", target="instructions.md#Beta", content="x")),
    )
    assert "Beta" not in original.instructions
