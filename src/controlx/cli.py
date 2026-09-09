"""ControlX command line. Every TUI action has an equivalent here on purpose:
the tool has to be scriptable and CI-friendly, not only interactive.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import click
import typer
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from . import __version__
from .context import AppContext
from .core.models import Probe, Verdict
from .errors import ControlXError, ThresholdError, UserError
from .services import (
    add_workspace,
    apply_patch,
    draft_probes,
    export_pack,
    import_pack,
    init_home,
    passport_markdown,
    resolve_patch,
)
from .services import (
    audit as run_audit_service,
)
from .services import (
    doctor as doctor_service,
)
from .theme import rich_theme

VERDICT_STYLE = {
    Verdict.SUFFICIENT: "ok",
    Verdict.PARTIAL: "warn",
    Verdict.MISSING: "err",
    Verdict.CONFLICT: "conflict",
}

console = Console(theme=rich_theme())
err_console = Console(stderr=True, theme=rich_theme())


class ControlXGroup(typer.core.TyperGroup):
    """Maps ControlXError onto the documented exit codes: 1 user, 2 provider, 3 threshold.

    It lives on the group (not in main()) so `controlx` and CliRunner behave identically.
    """

    def invoke(self, ctx: click.Context):  # type: ignore[override]
        try:
            return super().invoke(ctx)
        except ControlXError as exc:
            err_console.print(f"[err]✗[/] {exc.message}")
            if exc.hint:
                err_console.print(f"[muted]hint: {exc.hint}[/]")
            raise SystemExit(exc.exit_code) from exc


app = typer.Typer(
    name="controlx",
    help="Terminal-native control plane for multi-project, multi-provider AI work.",
    no_args_is_help=False,
    add_completion=True,
    cls=ControlXGroup,
)
pack_app = typer.Typer(help="Create, import, export and inspect packs.")
workspace_app = typer.Typer(help="Provider endpoints (projects, custom GPTs, conversations).")
auth_app = typer.Typer(help="Credentials: API keys, OAuth, session/inject modes.")
probe_app = typer.Typer(help="Sufficiency questions owned by a pack.")
bridge_app = typer.Typer(help="Source pack -> target workspace links.")
audit_app = typer.Typer(help="Run and read sufficiency audits.")
patch_app = typer.Typer(help="Preview and apply gap patches.")
mcp_app = typer.Typer(help="Expose the vault to coding agents over MCP.")

app.add_typer(pack_app, name="pack")
app.add_typer(workspace_app, name="workspace")
app.add_typer(auth_app, name="auth")
app.add_typer(probe_app, name="probe")
app.add_typer(bridge_app, name="bridge")
app.add_typer(audit_app, name="audit")
app.add_typer(patch_app, name="patch")
app.add_typer(mcp_app, name="mcp")

_HOME: Path | None = None


def ctx() -> AppContext:
    return AppContext.load(_HOME)


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"controlx {__version__}")
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def main_callback(
    context: typer.Context,
    home: Path | None = typer.Option(
        None, "--home", envvar="CONTROLX_HOME", help="ControlX home (default ~/.controlx)."
    ),
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Print version and exit.",
    ),
) -> None:
    global _HOME
    _HOME = home
    if context.invoked_subcommand is None:
        from .tui.app import run_tui

        run_tui(home)


# --------------------------------------------------------------------------- #
# init / doctor
# --------------------------------------------------------------------------- #
@app.command()
def init(force: bool = typer.Option(False, "--force", help="Rewrite config.toml.")) -> None:
    """Create ~/.controlx (vault, index, config)."""
    cfg = init_home(_HOME, force=force)
    console.print(f"[ok]✓[/] ControlX home ready at [bold]{cfg.home}[/]")
    console.print(f"  vault   {cfg.vault_dir}")
    console.print(f"  index   {cfg.db_path}")
    console.print(f"  config  {cfg.config_path}")
    console.print("\nNext: [bold]controlx pack import examples/packs/demo-service[/]")


@app.command()
def doctor(as_json: bool = typer.Option(False, "--json")) -> None:
    """Check the local install: python, vault, keys, MCP, tmux."""
    checks = doctor_service(ctx())
    if as_json:
        console.print_json(json.dumps(checks))
        return
    table = Table("check", "status", "detail", box=None)
    for check in checks:
        glyph = "[ok]✓[/]" if check["status"] == "ok" else "[warn]⚠[/]"
        table.add_row(check["name"], glyph, check["detail"])
    console.print(table)


@app.command()
def demo() -> None:
    """Run the offline golden path end to end (no API keys needed)."""
    from .demo import run_demo

    run_demo(_HOME)


# --------------------------------------------------------------------------- #
# packs
# --------------------------------------------------------------------------- #
@pack_app.command("new")
def pack_new(
    slug: str,
    name: str | None = typer.Option(None, "--name"),
    empty: bool = typer.Option(False, "--empty", help="No starter instructions."),
) -> None:
    """Create an empty pack in the vault."""
    pack = ctx().store.create(slug, name, template=not empty)
    console.print(f"[ok]✓[/] created pack [bold]{pack.slug}[/] v{pack.version}")


@pack_app.command("import")
def pack_import(
    source: Path,
    slug: str | None = typer.Option(None, "--slug", help="Import under a different slug."),
) -> None:
    """Import a pack directory (or a folder of markdown) into the vault."""
    pack = import_pack(ctx(), source, slug)
    console.print(
        f"[ok]✓[/] imported [bold]{pack.slug}[/] v{pack.version} "
        f"({len(pack.probes)} probe(s), {len(pack.knowledge)} knowledge doc(s))"
    )


@pack_app.command("export")
def pack_export(
    slug: str,
    fmt: str = typer.Option("dir", "--format", help="dir | md | passport | inject"),
    out: Path | None = typer.Option(None, "--out"),
) -> None:
    """Export a pack. `inject` also copies a paste bundle to the clipboard."""
    path = export_pack(ctx(), slug, fmt, out)
    console.print(f"[ok]✓[/] wrote {path}")


@pack_app.command("ls")
def pack_ls() -> None:
    """List packs in the vault."""
    context = ctx()
    table = Table("slug", "name", "ver", "probes", "prompts", "knowledge", box=None)
    for slug in context.store.list_packs():
        pack = context.store.load(slug)
        table.add_row(
            pack.slug,
            pack.name,
            str(pack.version),
            str(len(pack.probes)),
            str(len(pack.prompts)),
            str(len(pack.knowledge)),
        )
    console.print(table if context.store.list_packs() else "[muted]no packs yet[/]")


@pack_app.command("show")
def pack_show(slug: str, raw: bool = typer.Option(False, "--raw")) -> None:
    """Print a pack's instructions, constraints and probes."""
    pack = ctx().store.load(slug)
    if raw:
        console.print(pack.model_dump_json(indent=2))
        return
    console.print(
        Panel.fit(f"[bold]{pack.name}[/] ({pack.slug}) v{pack.version}", border_style="accent")
    )
    console.print(Syntax(pack.instructions, "markdown", theme="nord-darker", word_wrap=True))
    if pack.constraints:
        table = Table("constraint", "value", box=None)
        for constraint in pack.constraints:
            table.add_row(constraint.key, constraint.value)
        console.print(table)
    for probe in pack.probes:
        console.print(f"  [muted]?[/] {probe.question}")


@pack_app.command("passport")
def pack_passport(slug: str) -> None:
    """Print the handoff passport for a pack (paste into any agent)."""
    # Raw stdout, not rich: a passport gets piped and pasted, so it must not be wrapped.
    sys.stdout.write(passport_markdown(ctx(), slug))


@pack_app.command("rm")
def pack_rm(slug: str, yes: bool = typer.Option(False, "--yes")) -> None:
    """Delete a pack from the vault."""
    if not yes:
        raise UserError(f"refusing to delete '{slug}' without --yes")
    ctx().store.delete(slug)
    console.print(f"[ok]✓[/] deleted {slug}")


# --------------------------------------------------------------------------- #
# probes
# --------------------------------------------------------------------------- #
@probe_app.command("add")
def probe_add(
    slug: str,
    question: str = typer.Option(..., "-q", "--question"),
    signal: list[str] = typer.Option([], "-s", "--signal", help="Expected signal (repeatable)."),
    weight: float = typer.Option(1.0, "--weight"),
) -> None:
    """Add a probe to a pack."""
    context = ctx()
    pack = context.store.load(slug)
    pack.probes.append(
        Probe(
            question=question, expected_signals=list(signal), weight=weight, source_pack_id=pack.id
        )
    )
    context.store.save(pack, bump=True)
    console.print(f"[ok]✓[/] {slug} now has {len(pack.probes)} probe(s), v{pack.version}")


@probe_app.command("ls")
def probe_ls(slug: str) -> None:
    """List a pack's probes."""
    pack = ctx().store.load(slug)
    table = Table("id", "weight", "question", "expects", box=None)
    for probe in pack.probes:
        table.add_row(
            probe.id, f"{probe.weight:g}", probe.question, "; ".join(probe.expected_signals)
        )
    console.print(table if pack.probes else "[muted]no probes; try `controlx probe draft`[/]")


@probe_app.command("draft")
def probe_draft(slug: str, limit: int = typer.Option(8, "--limit")) -> None:
    """Generate draft probes from the pack's own instructions."""
    pack = draft_probes(ctx(), slug, limit)
    console.print(f"[ok]✓[/] {slug} v{pack.version} now has {len(pack.probes)} probe(s)")
    console.print("[muted]review them: controlx probe ls " + slug + "[/]")


# --------------------------------------------------------------------------- #
# workspaces + auth
# --------------------------------------------------------------------------- #
@workspace_app.command("add")
def workspace_add(
    provider: str = typer.Option(..., "--provider", help="openai | anthropic | xai | mcp"),
    name: str = typer.Option(..., "--name"),
    mode: str = typer.Option("api_key", "--mode", help="api_key | oauth | session"),
    kind: str = typer.Option(
        "project", "--kind", help="project | custom_gpt | conversation | agent"
    ),
    account: str = typer.Option("default", "--account"),
    model: str | None = typer.Option(None, "--model"),
    remote_ref: str | None = typer.Option(None, "--remote-ref"),
) -> None:
    """Register a provider endpoint."""
    workspace = add_workspace(
        ctx(),
        provider=provider,
        name=name,
        auth_mode=mode,
        endpoint_kind=kind,
        account=account,
        model=model,
        remote_ref=remote_ref,
    )
    console.print(f"[ok]✓[/] workspace [bold]{workspace.name}[/] → target ref `{workspace.ref}`")
    if mode == "session":
        console.print("[warn]⚠[/] session mode is LIMITED: paste-only, cannot be probed.")


@workspace_app.command("list")
def workspace_list() -> None:
    """List registered workspaces."""
    workspaces = ctx().index.list_workspaces()
    table = Table("name", "ref", "provider", "auth", "kind", "model", box=None)
    for workspace in workspaces:
        table.add_row(
            workspace.name,
            workspace.ref,
            workspace.provider,
            workspace.auth_mode,
            workspace.endpoint_kind,
            workspace.model or "-",
        )
    console.print(table if workspaces else "[muted]no workspaces yet[/]")


@workspace_app.command("rm")
def workspace_rm(name: str) -> None:
    """Remove a workspace from the registry."""
    context = ctx()
    workspace = context.index.find_workspace(name)
    if workspace is None:
        raise UserError(f"no workspace matching '{name}'")
    context.index.delete_workspace(workspace.id)
    console.print(f"[ok]✓[/] removed {workspace.name}")


@auth_app.command("add")
def auth_add(
    provider: str = typer.Option(..., "--provider"),
    mode: str = typer.Option("api_key", "--mode", help="api_key | oauth | session"),
    account: str = typer.Option("default", "--account"),
    key: str | None = typer.Option(None, "--key", help="Read from stdin/prompt when omitted."),
) -> None:
    """Store a credential. Keys go to the OS keyring, never to the vault."""
    context = ctx()
    if mode == "api_key":
        secret = key or typer.prompt(f"{provider} API key", hide_input=True)
        backend = context.secrets.set(provider, secret.strip(), account)
        console.print(f"[ok]✓[/] stored {provider}:{account} in {backend}")
        return
    if mode == "oauth":
        console.print(
            "[warn]⚠ LIMITED[/] No consumer AI provider currently publishes an OAuth flow that "
            "lets a third-party app act on a ChatGPT/Claude/Grok subscription.\n"
            "ControlX will not scrape private session cookies. Use --mode api_key for automated "
            "probing, or --mode session for an explicit paste-only workspace.\n"
            "See docs/PROVIDERS.md."
        )
        raise typer.Exit(code=1)
    if mode == "session":
        add_workspace(
            context,
            provider=provider,
            name=f"{provider}:{account} (inject)",
            auth_mode="session",
            account=account,
        )
        console.print(
            f"[ok]✓[/] registered a paste-only workspace for {provider}:{account}.\n"
            "[muted]Apply will emit an inject bundle; probes cannot run automatically.[/]"
        )
        return
    raise UserError(f"unknown auth mode '{mode}'", hint="api_key | oauth | session")


@auth_app.command("list")
def auth_list() -> None:
    """Show which providers have credentials (redacted)."""
    from .adapters.secrets import redact

    context = ctx()
    table = Table("provider", "key", "backend", box=None)
    for provider in ("openai", "anthropic", "xai"):
        table.add_row(provider, redact(context.secrets.get(provider)), context.secrets.backend())
    console.print(table)


@auth_app.command("test")
def auth_test(provider: str, model: str | None = typer.Option(None, "--model")) -> None:
    """Send one tiny live request to verify a credential."""
    from .adapters.providers.registry import build_adapter, canonical_provider

    context = ctx()
    name = canonical_provider(provider)
    adapter = build_adapter(
        name, api_key=context.secrets.get(name), model=model or context.cfg.model_for(name)
    )
    health = asyncio.run(adapter.health())
    if health.ok:
        console.print(f"[ok]✓[/] {name}: {health.detail}")
    else:
        err_console.print(f"[err]✗[/] {name}: {health.detail}")
        raise typer.Exit(code=2)


@auth_app.command("rm")
def auth_rm(provider: str, account: str = typer.Option("default", "--account")) -> None:
    """Delete a stored credential."""
    ctx().secrets.delete(provider, account)
    console.print(f"[ok]✓[/] removed {provider}:{account}")


# --------------------------------------------------------------------------- #
# bridges / audits
# --------------------------------------------------------------------------- #
@bridge_app.command("create")
def bridge_create(
    source: str = typer.Option(..., "--source"),
    target: str = typer.Option(..., "--target"),
    direction: str = typer.Option("forward", "--direction"),
) -> None:
    """Link a source pack to a target workspace."""
    from .core.models import Bridge

    context = ctx()
    pack = context.store.load(source)
    resolved = context.resolve_target(target)
    bridge = Bridge(
        source_pack_id=pack.id,
        target_workspace_id=resolved.ref,
        direction=direction,  # type: ignore[arg-type]
    )
    context.index.upsert_bridge(bridge)
    console.print(f"[ok]✓[/] bridge {pack.slug} → {resolved.ref} ({bridge.id})")


@bridge_app.command("ls")
def bridge_ls() -> None:
    """List bridges."""
    context = ctx()
    slugs = {context.store.load(s).id: s for s in context.store.list_packs()}
    table = Table("id", "source", "target", "direction", "last audit", box=None)
    for bridge in context.index.list_bridges():
        table.add_row(
            bridge.id,
            slugs.get(bridge.source_pack_id, bridge.source_pack_id),
            bridge.target_workspace_id,
            bridge.direction,
            bridge.last_audit_id or "-",
        )
    console.print(table)


@audit_app.command("run")
def audit_run(
    source: str = typer.Option(..., "--source", help="Source pack slug."),
    target: str = typer.Option(
        ..., "--target", help="pack:<slug> | <workspace> | <provider>:<account>"
    ),
    model: str | None = typer.Option(None, "--model"),
    min_score: float | None = typer.Option(None, "--min-score", help="Exit 3 below this score."),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Ask the target the source pack's probes and score its sufficiency."""
    context = ctx()
    result, patch = asyncio.run(
        run_audit_service(context, source_slug=source, target_ref=target, model=model)
    )
    if as_json:
        console.print(result.model_dump_json(indent=2))
    else:
        _render_audit(result, patch.id)
    threshold = min_score if min_score is not None else None
    if threshold is not None and result.score_pct < threshold:
        raise ThresholdError(
            f"audit {result.id} scored {result.score_pct}% (min {threshold}%)",
            hint=f"controlx patch preview {result.id}",
        )


def _render_audit(result, patch_id: str) -> None:  # type: ignore[no-untyped-def]
    colour = (
        "score.high"
        if result.score_pct >= 70
        else "score.mid"
        if result.score_pct >= 40
        else "score.low"
    )
    console.print(
        Panel.fit(
            f"[bold]{result.source_slug}[/] → [bold]{result.target_ref}[/]\n"
            f"sufficiency: [{colour}]{result.score_pct}%[/]",
            title=result.id,
            border_style=colour,
        )
    )
    for probe_result in result.results:
        style = VERDICT_STYLE[probe_result.verdict]
        console.print(f"  [{style}]{probe_result.verdict.glyph}[/] {probe_result.question}")
        if probe_result.verdict is not Verdict.SUFFICIENT:
            console.print(f"      [muted]{probe_result.rationale}[/]")
    for conflict in result.conflicts:
        console.print(
            f"  [conflict]⚠[/] conflict [bold]{conflict.key}[/]: "
            f"source={conflict.source_value!r} target={conflict.target_value!r}"
        )
    if result.missing_instructions:
        console.print("\n  missing instructions: " + ", ".join(result.missing_instructions))
    if result.missing_knowledge:
        console.print("  missing knowledge: " + ", ".join(result.missing_knowledge))
    console.print(f"\n  patch: [bold]{patch_id}[/]  →  controlx patch preview {patch_id}")


@audit_app.command("show")
def audit_show(audit_id: str, as_json: bool = typer.Option(False, "--json")) -> None:
    """Show a stored audit."""
    context = ctx()
    result = context.index.load_audit(audit_id)
    if as_json:
        console.print(result.model_dump_json(indent=2))
        return
    _render_audit(result, result.patch_id or "-")


@audit_app.command("ls")
def audit_ls(
    source: str | None = typer.Option(None, "--source"),
    limit: int = typer.Option(20, "--limit"),
) -> None:
    """List recent audits."""
    rows = ctx().index.list_audits(source, limit)
    table = Table("id", "source", "target", "score", "when", box=None)
    for row in rows:
        table.add_row(
            row["id"],
            row["source_slug"],
            row["target_ref"],
            f"{row['score_pct']}%",
            row["created_at"][:19],
        )
    console.print(table if rows else "[muted]no audits yet[/]")


# --------------------------------------------------------------------------- #
# patches
# --------------------------------------------------------------------------- #
@patch_app.command("preview")
def patch_preview(
    ident: str | None = typer.Argument(None, help="patch id, audit id, or latest"),
) -> None:
    """Show exactly what would change. Nothing is written."""
    patch = resolve_patch(ctx(), ident)
    console.print(Syntax(patch.preview_markdown, "markdown", theme="nord-darker", word_wrap=True))
    console.print(f"[muted]apply with:[/] controlx patch apply {patch.id} --approve")


@patch_app.command("apply")
def patch_apply(
    ident: str | None = typer.Argument(None),
    approve: bool = typer.Option(False, "--approve", help="Approve every operation."),
    op: list[str] = typer.Option([], "--op", help="Approve only these op ids (repeatable)."),
) -> None:
    """Apply an approved patch to its target."""
    context = ctx()
    patch, result = asyncio.run(apply_patch(context, ident, approve=approve, ops=list(op)))
    glyph = "[ok]✓[/]" if result.applied else "[warn]⚠[/]"
    console.print(f"{glyph} patch {patch.id} → {patch.target_ref} [muted]({patch.status.value})[/]")
    console.print(result.detail)


@patch_app.command("ls")
def patch_ls(limit: int = typer.Option(20, "--limit")) -> None:
    """List patches by audit."""
    context = ctx()
    table = Table("patch", "audit", "target", "status", "ops", box=None)
    for row in context.index.list_audits(limit=limit):
        patch = context.index.patch_for_audit(row["id"])
        if patch:
            table.add_row(
                patch.id, patch.audit_id, patch.target_ref, patch.status.value, str(len(patch.ops))
            )
    console.print(table)


# --------------------------------------------------------------------------- #
# mcp / tmux
# --------------------------------------------------------------------------- #
@mcp_app.command("serve")
def mcp_serve(
    transport: str = typer.Option("stdio", "--transport", help="stdio | http"),
) -> None:
    """Serve the vault over MCP for Cursor, Claude Code, Codex, Claude Desktop."""
    from .mcp.server import serve

    serve(_HOME, transport=transport)


@app.command("tmux")
def tmux_cmd(
    action: str = typer.Argument("attach", help="attach | split"),
) -> None:
    """Open ControlX panes in tmux (cx-audit, cx-mcp)."""
    from .tmuxutil import tmux_attach, tmux_split

    if action == "attach":
        tmux_attach(_HOME)
    elif action == "split":
        tmux_split()
    else:
        raise UserError("tmux action must be 'attach' or 'split'")


@app.command("shell")
def shell_cmd() -> None:
    """Interactive command loop (the same palette the TUI uses)."""
    from .shell import run_shell

    run_shell(_HOME)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
