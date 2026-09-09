"""Markdown + YAML pack store.

Markdown is the human and git source of truth; SQLite is only an index.
Writes are deterministic (sorted keys, stable file names) so a pack diffs
cleanly in git.
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from typing import Any

import yaml

from ...core.ids import slugify
from ...core.models import (
    Constraint,
    Decision,
    KnowledgeDoc,
    Pack,
    Probe,
    PromptEntry,
    utcnow,
)
from ...errors import NotFoundError, VaultError
from . import frontmatter

PACK_FILE = "pack.yaml"
INSTRUCTIONS_FILE = "instructions.md"
PROBES_FILE = "probes.yaml"


class PackStore:
    """CRUD over ~/.controlx/vault/packs/<slug>/."""

    def __init__(self, packs_dir: Path) -> None:
        self.packs_dir = Path(packs_dir)

    # ---------------------------------------------------------------- paths --
    def pack_dir(self, slug: str) -> Path:
        return self.packs_dir / slug

    def exists(self, slug: str) -> bool:
        return (self.pack_dir(slug) / PACK_FILE).exists()

    def list_packs(self) -> list[str]:
        if not self.packs_dir.exists():
            return []
        return sorted(path.name for path in self.packs_dir.iterdir() if (path / PACK_FILE).exists())

    # ----------------------------------------------------------------- read --
    def load(self, slug: str) -> Pack:
        directory = self.pack_dir(slug)
        if not (directory / PACK_FILE).exists():
            raise NotFoundError(
                f"pack '{slug}' not found in {self.packs_dir}",
                hint="run `controlx pack ls` to see what is in the vault",
            )
        return self.read_dir(directory)

    def read_dir(self, directory: Path) -> Pack:
        """Read a pack from any directory (vault or an importable folder)."""
        meta: dict[str, Any] = yaml.safe_load((directory / PACK_FILE).read_text("utf-8")) or {}
        instructions_file = meta.get("instructions_file", INSTRUCTIONS_FILE)
        instructions_path = directory / instructions_file
        instructions = instructions_path.read_text("utf-8") if instructions_path.exists() else ""

        probes: list[Probe] = []
        probes_path = directory / PROBES_FILE
        if probes_path.exists():
            raw = yaml.safe_load(probes_path.read_text("utf-8")) or []
            probes = [Probe(**item) for item in raw]

        prompts = [self._read_prompt(path) for path in sorted((directory / "prompts").glob("*.md"))]
        decisions = [
            self._read_decision(path) for path in sorted((directory / "decisions").glob("*.md"))
        ]

        knowledge: list[KnowledgeDoc] = []
        for item in meta.get("knowledge", []) or []:
            doc = KnowledgeDoc(**item)
            local = directory / "knowledge" / f"{slugify(doc.title)}.md"
            if doc.text is None and local.exists():
                doc.text = local.read_text("utf-8")
            knowledge.append(doc)

        variants: dict[str, str] = {}
        for provider, rel in (meta.get("provider_variants", {}) or {}).items():
            path = directory / rel
            variants[provider] = path.read_text("utf-8") if path.exists() else ""

        return Pack(
            id=meta.get("id") or Pack(slug="x", name="x").id,
            slug=meta.get("slug", directory.name),
            name=meta.get("name", directory.name),
            instructions=instructions,
            constraints=[Constraint(**c) for c in meta.get("constraints", []) or []],
            prompts=prompts,
            knowledge=knowledge,
            probes=probes,
            decisions=decisions,
            open_questions=list(meta.get("open_questions", []) or []),
            provider_variants=variants,
            version=int(meta.get("version", 1)),
            parent_version=meta.get("parent_version"),
            updated_at=meta.get("updated_at") or utcnow(),
        )

    def _read_prompt(self, path: Path) -> PromptEntry:
        meta, body = frontmatter.parse(path.read_text("utf-8"))
        return PromptEntry(
            id=meta.get("id") or PromptEntry(title="x", body="").id,
            title=meta.get("title", path.stem),
            body=body,
            variables=list(meta.get("variables", []) or []),
            tags=list(meta.get("tags", []) or []),
            provider_tune=meta.get("provider_tune"),
        )

    def _read_decision(self, path: Path) -> Decision:
        meta, body = frontmatter.parse(path.read_text("utf-8"))
        return Decision(
            id=meta.get("id") or Decision(date="", title="x").id,
            date=str(meta.get("date", path.stem[:10])),
            title=meta.get("title", path.stem),
            body=body,
        )

    # ---------------------------------------------------------------- write --
    def save(self, pack: Pack, *, bump: bool = False) -> Pack:
        if bump:
            pack.parent_version = pack.version
            pack.version += 1
        pack.updated_at = utcnow()

        directory = self.pack_dir(pack.slug)
        directory.mkdir(parents=True, exist_ok=True)
        (directory / INSTRUCTIONS_FILE).write_text(
            pack.instructions.rstrip() + "\n", encoding="utf-8"
        )

        meta: dict[str, Any] = {
            "id": pack.id,
            "slug": pack.slug,
            "name": pack.name,
            "version": pack.version,
            "parent_version": pack.parent_version,
            "updated_at": pack.updated_at.isoformat(),
            "instructions_file": INSTRUCTIONS_FILE,
            "constraints": [c.model_dump(exclude_none=True) for c in pack.constraints],
            "open_questions": pack.open_questions,
            "knowledge": [
                {
                    **doc.model_dump(exclude={"text"}, exclude_none=True),
                    "hash": doc.hash or _hash(doc.text or doc.title),
                }
                for doc in pack.knowledge
            ],
            "provider_variants": {
                provider: f"variants/{provider}.md" for provider in sorted(pack.provider_variants)
            },
        }
        (directory / PACK_FILE).write_text(
            yaml.safe_dump(meta, sort_keys=True, allow_unicode=True), encoding="utf-8"
        )

        (directory / PROBES_FILE).write_text(
            yaml.safe_dump(
                [p.model_dump(exclude_none=True) for p in pack.probes],
                sort_keys=True,
                allow_unicode=True,
            ),
            encoding="utf-8",
        )

        self._write_children(
            directory / "prompts",
            {
                f"{slugify(p.title)}.md": frontmatter.dump(
                    {
                        "id": p.id,
                        "title": p.title,
                        "variables": p.variables,
                        "tags": p.tags,
                        **({"provider_tune": p.provider_tune} if p.provider_tune else {}),
                    },
                    p.body,
                )
                for p in pack.prompts
            },
        )
        self._write_children(
            directory / "decisions",
            {
                f"{d.date}-{slugify(d.title)}.md": frontmatter.dump(
                    {"id": d.id, "date": d.date, "title": d.title}, d.body
                )
                for d in pack.decisions
            },
        )
        self._write_children(
            directory / "knowledge",
            {
                f"{slugify(doc.title)}.md": (doc.text or f"# {doc.title}\n\n{doc.summary or ''}\n")
                for doc in pack.knowledge
            },
        )
        self._write_children(
            directory / "variants",
            {f"{provider}.md": body for provider, body in pack.provider_variants.items()},
        )
        return pack

    def _write_children(self, directory: Path, files: dict[str, str]) -> None:
        if not files:
            if directory.exists():
                shutil.rmtree(directory)
            return
        directory.mkdir(parents=True, exist_ok=True)
        for existing in directory.glob("*.md"):
            if existing.name not in files:
                existing.unlink()
        for name, content in files.items():
            (directory / name).write_text(content, encoding="utf-8")

    def create(self, slug: str, name: str | None = None, *, template: bool = True) -> Pack:
        if self.exists(slug):
            raise VaultError(f"pack '{slug}' already exists")
        pack = Pack(
            slug=slug,
            name=name or slug.replace("-", " ").title(),
            instructions=_STARTER if template else "",
        )
        return self.save(pack)

    def delete(self, slug: str) -> None:
        directory = self.pack_dir(slug)
        if not directory.exists():
            raise NotFoundError(f"pack '{slug}' not found")
        shutil.rmtree(directory)

    # --------------------------------------------------------------- import --
    def import_dir(self, source: Path, *, slug: str | None = None) -> Pack:
        source = Path(source).expanduser().resolve()
        if not source.exists():
            raise NotFoundError(f"no such directory: {source}")
        if (source / PACK_FILE).exists():
            pack = self.read_dir(source)
        else:
            pack = self._import_loose_markdown(source)
        if slug:
            pack.slug = slug
        if self.exists(pack.slug):
            raise VaultError(
                f"pack '{pack.slug}' already exists in the vault",
                hint="pass --slug to import under a different name",
            )
        return self.save(pack)

    def _import_loose_markdown(self, source: Path) -> Pack:
        """A folder of markdown becomes instructions + knowledge docs."""
        instructions_path = next(
            (
                source / candidate
                for candidate in (INSTRUCTIONS_FILE, "README.md")
                if (source / candidate).exists()
            ),
            None,
        )
        instructions = instructions_path.read_text("utf-8") if instructions_path else ""
        knowledge = [
            KnowledgeDoc(
                title=path.stem.replace("-", " ").title(),
                path=str(path),
                text=path.read_text("utf-8"),
                hash=_hash(path.read_text("utf-8")),
            )
            for path in sorted(source.glob("*.md"))
            if path != instructions_path
        ]
        return Pack(
            slug=slugify(source.name),
            name=source.name.replace("-", " ").title(),
            instructions=instructions,
            knowledge=knowledge,
        )

    # --------------------------------------------------------------- export --
    def export_dir(self, pack: Pack, destination: Path) -> Path:
        destination = Path(destination).expanduser()
        destination.mkdir(parents=True, exist_ok=True)
        source_dir = self.pack_dir(pack.slug)
        if not source_dir.exists():
            raise NotFoundError(f"pack '{pack.slug}' is not in the vault")
        target = destination / pack.slug
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(source_dir, target)
        return target

    def export_single_file(self, pack: Pack) -> str:
        parts = [
            f"# {pack.name} (`{pack.slug}` v{pack.version})",
            "",
            "## Instructions",
            "",
            pack.instructions.strip(),
            "",
            "## Constraints",
            "",
        ]
        parts += [f"- **{c.key}**: {c.value}" for c in pack.constraints] or ["_none_"]
        if pack.prompts:
            parts += ["", "## Prompts", ""]
            for prompt in pack.prompts:
                parts += [f"### {prompt.title}", "", prompt.body.strip(), ""]
        if pack.probes:
            parts += ["", "## Probes", ""]
            parts += [f"- {probe.question}" for probe in pack.probes]
        if pack.knowledge:
            parts += ["", "## Knowledge manifest", ""]
            parts += [
                f"- {doc.title}" + (f" ({doc.path})" if doc.path else "") for doc in pack.knowledge
            ]
        return "\n".join(parts).rstrip() + "\n"


_STARTER = """## Purpose

Describe what this project is and who it serves.

## Constraints

State the rules an AI workspace must never violate.
"""


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
