from pathlib import Path

import pytest

from controlx.adapters.vault import PackStore
from controlx.core.models import Decision, KnowledgeDoc, PromptEntry
from controlx.errors import NotFoundError, VaultError


def test_round_trip_preserves_every_part(ctx, complete_pack):
    complete_pack.prompts.append(PromptEntry(title="Review", body="do the thing", tags=["qa"]))
    complete_pack.knowledge.append(KnowledgeDoc(title="Retention", text="# Retention\n\n90 days"))
    complete_pack.decisions.append(Decision(date="2026-01-01", title="Use REST", body="because"))
    complete_pack.open_questions.append("who owns rollout?")
    ctx.store.save(complete_pack)

    loaded = ctx.store.load("complete")
    assert loaded.instructions == complete_pack.instructions
    assert [c.key for c in loaded.constraints] == ["api_style"]
    assert [p.title for p in loaded.prompts] == ["Review"]
    assert [d.title for d in loaded.decisions] == ["Use REST"]
    assert [k.title for k in loaded.knowledge] == ["Retention"]
    assert loaded.knowledge[0].text.strip().endswith("90 days")
    assert [p.question for p in loaded.probes] == [p.question for p in complete_pack.probes]
    assert loaded.open_questions == ["who owns rollout?"]


def test_save_is_deterministic(ctx, complete_pack):
    ctx.store.save(complete_pack)
    first = (ctx.cfg.packs_dir / "complete" / "pack.yaml").read_text()
    reloaded = ctx.store.load("complete")
    reloaded.updated_at = complete_pack.updated_at
    ctx.store.save(reloaded)
    second = (ctx.cfg.packs_dir / "complete" / "pack.yaml").read_text()
    assert _without_timestamp(first) == _without_timestamp(second)


def _without_timestamp(text: str) -> str:
    return "\n".join(line for line in text.splitlines() if not line.startswith("updated_at"))


def test_bump_records_parent_version(ctx, complete_pack):
    ctx.store.save(complete_pack)
    bumped = ctx.store.save(ctx.store.load("complete"), bump=True)
    assert (bumped.version, bumped.parent_version) == (2, 1)


def test_removed_children_are_deleted_from_disk(ctx, complete_pack):
    complete_pack.prompts.append(PromptEntry(title="Temp", body="x"))
    ctx.store.save(complete_pack)
    assert (ctx.cfg.packs_dir / "complete" / "prompts" / "temp.md").exists()
    pack = ctx.store.load("complete")
    pack.prompts = []
    ctx.store.save(pack)
    assert not (ctx.cfg.packs_dir / "complete" / "prompts").exists()


def test_create_rejects_duplicates(ctx):
    ctx.store.create("dupe")
    with pytest.raises(VaultError):
        ctx.store.create("dupe")


def test_load_missing_pack_raises(ctx):
    with pytest.raises(NotFoundError):
        ctx.store.load("nope")


def test_import_loose_markdown_folder(ctx, tmp_path: Path):
    folder = tmp_path / "notes"
    folder.mkdir()
    (folder / "instructions.md").write_text("## Rules\n\nbe kind\n")
    (folder / "glossary.md").write_text("# Glossary\n\ntenant = billing boundary\n")
    pack = ctx.store.import_dir(folder)
    assert pack.slug == "notes"
    assert "be kind" in pack.instructions
    assert [k.title for k in pack.knowledge] == ["Glossary"]


def test_import_under_a_different_slug(ctx, tmp_path: Path):
    source = tmp_path / "src"
    source.mkdir()
    (source / "instructions.md").write_text("## X\n\ny\n")
    ctx.store.import_dir(source)
    again = ctx.store.import_dir(source, slug="src-copy")
    assert again.slug == "src-copy"
    assert set(ctx.store.list_packs()) == {"src", "src-copy"}


def test_export_single_file_and_dir(ctx, complete_pack, tmp_path: Path):
    ctx.store.save(complete_pack)
    markdown = ctx.store.export_single_file(complete_pack)
    assert "## Instructions" in markdown and "widgets are immutable" in markdown
    target = ctx.store.export_dir(complete_pack, tmp_path / "out")
    assert (target / "pack.yaml").exists()


def test_store_is_usable_standalone(tmp_path: Path, complete_pack):
    store = PackStore(tmp_path / "packs")
    store.save(complete_pack)
    assert store.list_packs() == ["complete"]
