"""Application services. The CLI, the TUI and the MCP server all call these -
never the adapters directly. That is what keeps CLI/TUI parity honest.
"""

from __future__ import annotations

import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from .config import Config, default_config, write_config
from .context import AppContext, Target
from .core.audit import compose_patch, generate_probes, run_audit
from .core.models import Audit, Bridge, Pack, Patch, PatchStatus, Workspace
from .core.passport import render_inject_bundle, render_passport
from .core.ports import ApplyResult
from .errors import NotFoundError, UserError


def _examples_dir() -> Path:
    """Packaged copy (wheel) first, repo checkout second."""
    packaged = Path(__file__).resolve().parent / "_examples" / "packs"
    if packaged.is_dir():
        return packaged
    return Path(__file__).resolve().parents[2] / "examples" / "packs"


EXAMPLES_DIR = _examples_dir()


# --------------------------------------------------------------------------- #
# init / doctor
# --------------------------------------------------------------------------- #
def init_home(home: Path | None = None, *, force: bool = False) -> Config:
    cfg = default_config(home)
    cfg.ensure_dirs()
    if force or not cfg.config_path.exists():
        write_config(cfg)
    return cfg


def doctor(ctx: AppContext) -> list[dict[str, str]]:
    import sys

    checks: list[dict[str, str]] = []

    def add(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "status": "ok" if ok else "warn", "detail": detail})

    add("python", sys.version_info >= (3, 11), sys.version.split()[0])
    add("home", ctx.cfg.home.exists(), str(ctx.cfg.home))
    add("config", ctx.cfg.config_path.exists(), str(ctx.cfg.config_path))
    add("vault", ctx.cfg.packs_dir.exists(), f"{len(ctx.store.list_packs())} pack(s)")
    add("database", ctx.cfg.db_path.exists(), str(ctx.index.stats()))
    add("secret backend", True, ctx.secrets.backend())
    for provider in ("openai", "anthropic", "xai"):
        key = ctx.secrets.get(provider)
        add(f"key:{provider}", bool(key), "configured" if key else "missing (BYOK optional)")
    try:
        import mcp  # noqa: F401

        add("mcp sdk", True, "installed")
    except ImportError:
        add("mcp sdk", False, "not installed - `pip install 'controlx[mcp]'`")
    add("tmux", shutil.which("tmux") is not None, shutil.which("tmux") or "not found (optional)")
    return checks


# --------------------------------------------------------------------------- #
# packs
# --------------------------------------------------------------------------- #
def import_pack(ctx: AppContext, source: Path, slug: str | None = None) -> Pack:
    return ctx.store.import_dir(Path(source), slug=slug)


def export_pack(ctx: AppContext, slug: str, fmt: str, out: Path | None = None) -> Path:
    pack = ctx.store.load(slug)
    destination = Path(out) if out else ctx.cfg.exports_dir
    destination.mkdir(parents=True, exist_ok=True)
    if fmt == "dir":
        return ctx.store.export_dir(pack, destination)
    if fmt == "md":
        path = destination / f"{pack.slug}.md"
        path.write_text(ctx.store.export_single_file(pack), encoding="utf-8")
        return path
    if fmt == "passport":
        path = destination / f"{pack.slug}-passport.md"
        path.write_text(passport_markdown(ctx, slug), encoding="utf-8")
        return path
    if fmt == "inject":
        path = destination / f"{pack.slug}-inject.md"
        path.write_text(render_inject_bundle(pack), encoding="utf-8")
        copy_to_clipboard(path.read_text("utf-8"))
        return path
    raise UserError(f"unknown export format '{fmt}'", hint="dir | md | passport | inject")


def passport_markdown(ctx: AppContext, slug: str) -> str:
    pack = ctx.store.load(slug)
    audit_id = ctx.index.latest_audit_id(slug)
    audit = ctx.index.load_audit(audit_id) if audit_id else None
    return render_passport(pack, audit)


def draft_probes(ctx: AppContext, slug: str, limit: int = 8) -> Pack:
    pack = ctx.store.load(slug)
    existing = {p.question.strip().lower() for p in pack.probes}
    for probe in generate_probes(pack, limit):
        if probe.question.strip().lower() not in existing:
            pack.probes.append(probe)
    return ctx.store.save(pack, bump=True)


# --------------------------------------------------------------------------- #
# workspaces
# --------------------------------------------------------------------------- #
def add_workspace(
    ctx: AppContext,
    *,
    provider: str,
    name: str,
    auth_mode: str = "api_key",
    endpoint_kind: str = "project",
    account: str = "default",
    model: str | None = None,
    remote_ref: str | None = None,
) -> Workspace:
    workspace = Workspace(
        name=name,
        provider=provider,  # type: ignore[arg-type]
        auth_mode=auth_mode,  # type: ignore[arg-type]
        endpoint_kind=endpoint_kind,  # type: ignore[arg-type]
        account=account,
        model=model,
        remote_ref=remote_ref,
        last_seen_at=datetime.now(UTC),
    )
    ctx.index.upsert_workspace(workspace)
    return workspace


# --------------------------------------------------------------------------- #
# audit / patch
# --------------------------------------------------------------------------- #
async def audit(
    ctx: AppContext, *, source_slug: str, target_ref: str, model: str | None = None
) -> tuple[Audit, Patch]:
    source = ctx.store.load(source_slug)
    target = ctx.resolve_target(target_ref)

    bridge = ctx.index.find_bridge(source.id, target.ref) or Bridge(
        source_pack_id=source.id, target_workspace_id=target.ref
    )

    result = await run_audit(
        source=source,
        target_adapter=target.adapter,
        target_ref=target.ref,
        target_pack=target.pack,
        judge=ctx.judge(),
        bridge_id=bridge.id,
        model=model,
    )
    patch = compose_patch(audit=result, source=source, target_pack=target.pack)

    ctx.index.save_audit(result)
    ctx.index.save_patch(patch)
    bridge.last_audit_id = result.id
    ctx.index.upsert_bridge(bridge)
    return result, patch


def resolve_patch(ctx: AppContext, ident: str | None) -> Patch:
    """Accept a patch id, an audit id, or nothing (= latest audit)."""
    if not ident or ident == "latest":
        audit_id = ctx.index.latest_audit_id()
        if not audit_id:
            raise NotFoundError("no audits yet", hint="run `controlx audit run` first")
        ident = audit_id
    if ident.startswith("pat_"):
        return ctx.index.load_patch(ident)
    patch = ctx.index.patch_for_audit(ident)
    if patch is None:
        raise NotFoundError(f"no patch found for '{ident}'")
    return patch


async def apply_patch(
    ctx: AppContext, ident: str | None, *, approve: bool = False, ops: list[str] | None = None
) -> tuple[Patch, ApplyResult]:
    patch = resolve_patch(ctx, ident)
    if patch.status is PatchStatus.APPLIED:
        return patch, ApplyResult(applied=False, detail="patch is already applied")
    if not approve and not ops:
        raise UserError(
            "patch not approved",
            hint="re-run with --approve, or select ops with --op <id> (repeatable)",
        )
    for op in patch.ops:
        op.approved = True if approve and not ops else (op.id in set(ops or []))
    if not any(op.approved for op in patch.ops):
        raise UserError("no operations selected")

    target = ctx.resolve_target(patch.target_ref)
    caps = await target.adapter.capabilities()
    if caps.can_write_instructions:
        result = await target.adapter.apply_patch(None, patch)
        # A writable target either changed or already carried every op; both are "applied".
        patch.status = PatchStatus.APPLIED
    else:
        result = await _fallback_to_inject(ctx, patch, target)
        patch.status = PatchStatus.APPROVED
    patch.applied_at = datetime.now(UTC)
    patch.apply_note = result.detail
    ctx.index.save_patch(patch)
    return patch, result


async def _fallback_to_inject(ctx: AppContext, patch: Patch, target: Target) -> ApplyResult:
    """No write API: emit a paste bundle and say so plainly."""
    audit_record = ctx.index.load_audit(patch.audit_id)
    source = ctx.store.load(audit_record.source_slug)
    bundle = render_inject_bundle(source, patch.preview_markdown)
    path = ctx.cfg.exports_dir / f"inject-{patch.id}.md"
    path.write_text(bundle, encoding="utf-8")
    copied = copy_to_clipboard(bundle)
    caps = await target.adapter.capabilities()
    detail = (
        f"'{target.ref}' cannot be written by ControlX ({caps.note}). "
        f"NOTHING was changed remotely. Inject bundle written to {path}"
        + (" and copied to the clipboard." if copied else ".")
    )
    return ApplyResult(applied=False, detail=detail, inject_bundle=bundle, inject_path=str(path))


# --------------------------------------------------------------------------- #
# misc
# --------------------------------------------------------------------------- #
CLIPBOARD_COMMANDS = (["pbcopy"], ["wl-copy"], ["xclip", "-selection", "clipboard"], ["clip.exe"])


def copy_to_clipboard(text: str) -> bool:
    for command in CLIPBOARD_COMMANDS:
        if shutil.which(command[0]) is None:
            continue
        try:
            subprocess.run(command, input=text.encode("utf-8"), check=True, timeout=10)
            return True
        except (subprocess.SubprocessError, OSError):
            continue
    return False
