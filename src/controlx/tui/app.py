"""ControlX TUI - a dense four-pane engineering console.

  1 registry   2 pack viewer   3 runner log   4 audit / patch

Keyboard first. Every action here has a CLI twin; both call `services`.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import (
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    RichLog,
    Static,
)

from ..context import AppContext
from ..core.models import Verdict
from ..errors import ControlXError
from ..services import (
    apply_patch,
    audit,
    doctor,
    draft_probes,
    export_pack,
    import_pack,
    resolve_patch,
)
from ..theme import ACCENT, CONFLICT, ERR, MUTED, OK, TEXTUAL_VARS, WARN


def esc(text: object) -> str:
    """Vault text is data, never markup: a `[` in a pack must not become a tag."""
    return str(text).replace("[", r"\[")


VERDICT_STYLE = {
    Verdict.SUFFICIENT: OK,
    Verdict.PARTIAL: WARN,
    Verdict.MISSING: ERR,
    Verdict.CONFLICT: CONFLICT,
}

HELP = f"""[b {ACCENT}]ControlX keys[/]
  [{ACCENT}]1..4[/] focus pane      [{ACCENT}]tab[/] cycle       [{ACCENT}]enter[/] open
  [{ACCENT}]s[/] set source         [{ACCENT}]t[/] set target    [{ACCENT}]a[/] run audit
  [{ACCENT}]p[/] patch preview      [{ACCENT}]y[/] apply patch   [{ACCENT}]n[/] reject patch
  [{ACCENT}]d[/] probe draft        [{ACCENT}]e[/] edit in $EDITOR
  [{ACCENT}]:[/] command palette    [{ACCENT}]?[/] this help     [{ACCENT}]q[/] quit

[b {ACCENT}]palette[/]
  [{MUTED}]doctor | refresh | audit run | patch preview | patch apply
  pack new <slug> | pack import <path> | pack export <slug> \\[dir|md|passport|inject]
  probe draft <slug> | workspace add <provider> <name> | mcp serve[/]
"""


class Registry(ListView):
    """Packs and workspaces in one list. The registry is the map of the world."""


class ControlXApp(App[None]):
    TITLE = "ControlX"
    SUB_TITLE = "audit, don't chat"

    CSS = (
        TEXTUAL_VARS
        + """
    Screen { layout: vertical; background: $cx-bg; color: $cx-text; }
    Header { background: $cx-surface; color: $cx-text; }
    Footer { background: $cx-surface; color: $cx-muted; }
    Footer > .footer--key { background: $cx-surface-alt; color: $cx-accent; }
    Footer > .footer--description { color: $cx-muted; }

    #body { height: 1fr; background: $cx-bg; }

    #registry {
        width: 34;
        background: $cx-surface;
        border: round $cx-border;
        border-title-color: $cx-muted;
        scrollbar-background: $cx-surface;
        scrollbar-color: $cx-border;
    }
    #registry:focus-within { border: round $cx-accent; border-title-color: $cx-accent; }
    #registry > ListItem { background: $cx-surface; color: $cx-text; padding: 0 1; }
    #registry > ListItem.--highlight { background: $cx-surface-alt; color: $cx-text; }
    #registry:focus > ListItem.--highlight { background: $cx-accent 30%; }

    #center { width: 1fr; }

    #viewer {
        height: 1fr;
        background: $cx-bg;
        color: $cx-text;
        border: round $cx-border;
        border-title-color: $cx-muted;
        padding: 0 1;
    }
    #viewer:focus { border: round $cx-accent; border-title-color: $cx-accent; }

    #runner {
        height: 45%;
        background: $cx-surface;
        color: $cx-text;
        border: round $cx-border;
        border-title-color: $cx-muted;
    }
    #runner:focus { border: round $cx-accent; border-title-color: $cx-accent; }

    #side {
        width: 56;
        background: $cx-bg;
        color: $cx-text;
        border: round $cx-border;
        border-title-color: $cx-muted;
        padding: 0 1;
    }
    #side:focus { border: round $cx-accent; border-title-color: $cx-accent; }

    #status { height: 1; background: $cx-surface-alt; color: $cx-muted; padding: 0 1; }

    #palette {
        dock: bottom;
        background: $cx-surface;
        color: $cx-text;
        border: tall $cx-accent;
    }
    #palette > .input--placeholder { color: $cx-muted; }

    .title { text-style: bold; }
    """
    )

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("1", "focus_pane('registry')", "registry", show=False),
        Binding("2", "focus_pane('viewer')", "pack", show=False),
        Binding("3", "focus_pane('runner')", "runner", show=False),
        Binding("4", "focus_pane('side')", "audit", show=False),
        Binding("s", "set_source", "source"),
        Binding("t", "set_target", "target"),
        Binding("a", "run_audit", "audit"),
        Binding("p", "preview_patch", "preview"),
        Binding("y", "apply_patch", "apply"),
        Binding("n", "reject_patch", "reject", show=False),
        Binding("d", "draft_probes", "probes", show=False),
        Binding("e", "edit_pack", "edit", show=False),
        Binding("colon", "palette", "palette"),
        Binding("escape", "close_palette", "close", show=False),
        Binding("question_mark", "help", "help"),
        Binding("r", "refresh_registry", "refresh", show=False),
        Binding("q", "quit", "quit"),
    ]

    def __init__(self, home: Path | None = None) -> None:
        super().__init__()
        self.ctx = AppContext.load(home)
        self.home = home
        self.entries: list[tuple[str, str]] = []
        self.source: str | None = None
        self.target: str | None = None
        self.patch_id: str | None = None

    # ------------------------------------------------------------- compose --
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="body"):
            yield Registry(id="registry")
            with Vertical(id="center"):
                yield VerticalScroll(Static(id="viewer_body"), id="viewer")
                yield RichLog(id="runner", markup=True, highlight=False, wrap=True)
            yield VerticalScroll(Static(id="side_body"), id="side")
        yield Static(id="status")
        yield Input(placeholder="command…", id="palette")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#viewer").border_title = "pack"
        self.query_one("#runner").border_title = "runner"
        self.query_one("#side").border_title = "audit / patch"
        self.query_one("#registry").border_title = "registry"
        self.query_one("#palette", Input).display = False
        self.action_refresh_registry()
        self.log_line(f"[{MUTED}]ControlX ready. `s` source, `t` target, `a` audit, `?` help.[/]")
        self._render_status()
        self._preselect()
        self.query_one("#registry").focus()
        self.action_help()
        self.call_after_refresh(self._select_first_row)

    # -------------------------------------------------------------- helpers --
    def log_line(self, text: str) -> None:
        self.query_one("#runner", RichLog).write(text)

    def set_viewer(self, text: str) -> None:
        self.query_one("#viewer_body", Static).update(text)

    def set_side(self, text: str) -> None:
        self.query_one("#side_body", Static).update(text)

    def _render_patch(self, patch) -> None:  # type: ignore[no-untyped-def]
        """Dense op list. The markdown document stays in `controlx patch preview`."""
        lines = [
            f"[b {ACCENT}]{patch.id}[/]  {len(patch.ops)} op(s)  →  {patch.target_ref}",
            f"[{MUTED}]audit {patch.audit_id} · status {patch.status.value}[/]",
            "",
        ]
        for index, op in enumerate(patch.ops, start=1):
            lines.append(f"[{MUTED}]{index:>2}[/] [{ACCENT}]{op.op}[/]  {esc(op.target)}")
            if op.reason:
                lines.append(f"    [{MUTED}]{esc(op.reason)}[/]")
            head = op.content.strip().splitlines()
            for content_line in head[:3]:
                lines.append(f"    [{MUTED}]│[/] {esc(content_line)}")
            if len(head) > 3:
                lines.append(f"    [{MUTED}]│ … {len(head) - 3} more line(s)[/]")
            lines.append("")
        lines.append(f"[{MUTED}]y apply · n reject · patch preview for the full diff[/]")
        self.set_side("\n".join(lines))

    def _render_status(self) -> None:
        source = self.source or f"[{MUTED}]-[/]"
        target = self.target or f"[{MUTED}]-[/]"
        self.query_one("#status", Static).update(
            f" source [b]{esc(source)}[/]   →   target [b]{esc(target)}[/]   "
            f"patch [b]{esc(self.patch_id or '-')}[/]"
        )

    def _selected(self) -> tuple[str, str] | None:
        listview = self.query_one("#registry", Registry)
        index = listview.index
        if index is None:
            # ListView children mount asynchronously; fall back to the first row
            index = 0
        if index >= len(self.entries):
            return None
        return self.entries[index]

    def _preselect(self) -> None:
        """Open on the first two packs so `a` works immediately."""
        packs = [ref.split(":", 1)[1] for kind, ref in self.entries if kind == "pack"]
        if packs:
            self.source = packs[0]
        if len(packs) > 1:
            self.target = f"pack:{packs[1]}"
        self._render_status()

    # -------------------------------------------------------------- actions --
    def _select_first_row(self) -> None:
        """Land the cursor on row 0 once ListView's children exist.

        ListView mounts children asynchronously, so an index set during compose
        does not stick - and an index of None swallows the user's first arrow key.
        """
        listview = self.query_one("#registry", Registry)
        if self.entries and listview.index is None:
            listview.index = 0
        self.action_open()

    def action_focus_pane(self, pane: str) -> None:
        self.query_one(f"#{pane}").focus()

    def action_refresh_registry(self) -> None:
        listview = self.query_one("#registry", Registry)
        listview.clear()
        self.entries = []
        for slug in self.ctx.store.list_packs():
            pack = self.ctx.store.load(slug)
            self.entries.append(("pack", f"pack:{slug}"))
            listview.append(ListItem(Label(f"◆ {slug}  [{MUTED}]v{pack.version}[/]")))
        for workspace in self.ctx.index.list_workspaces():
            self.entries.append(("workspace", workspace.ref))
            listview.append(
                ListItem(Label(f"● {workspace.name}  [{MUTED}]{workspace.provider}[/]"))
            )
        if not self.entries:
            listview.append(ListItem(Label(f"[{MUTED}]empty vault - `pack import`[/]")))

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        self.action_open()

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        # the viewer follows the cursor: an empty pane teaches the user nothing
        self.action_open()

    def action_open(self) -> None:
        entry = self._selected()
        if entry is None:
            return
        kind, ref = entry
        if kind != "pack":
            workspace = self.ctx.index.find_workspace(ref)
            self.set_viewer(
                f"[b]{esc(workspace.name)}[/]\nprovider {esc(workspace.provider)}\n"
                f"auth {esc(workspace.auth_mode)}\nkind {esc(workspace.endpoint_kind)}"
                if workspace
                else esc(ref)
            )
            return
        pack = self.ctx.store.load(ref.split(":", 1)[1])
        probes = "\n".join(f"  [{MUTED}]?[/] {esc(p.question)}" for p in pack.probes)
        constraints = "\n".join(f"  {esc(c.key)}: {esc(c.value)}" for c in pack.constraints)
        self.set_viewer(
            f"[b {ACCENT}]{esc(pack.name)}[/] ({esc(pack.slug)}) v{pack.version}\n\n"
            f"{esc(pack.instructions)}\n\n[b]constraints[/]\n{constraints or '  -'}\n\n"
            f"[b]probes[/]\n{probes or '  -'}"
        )

    def action_set_source(self) -> None:
        entry = self._selected()
        if entry and entry[0] == "pack":
            self.source = entry[1].split(":", 1)[1]
            self._render_status()
            self.log_line(f"source = [b]{self.source}[/]")
        else:
            self.log_line(f"[{WARN}]source must be a pack[/]")

    def action_set_target(self) -> None:
        entry = self._selected()
        if entry:
            self.target = entry[1]
            self._render_status()
            self.log_line(f"target = [b]{self.target}[/]")

    def action_run_audit(self) -> None:
        if not self.source or not self.target:
            self.log_line(f"[{WARN}]pick a source (s) and a target (t) first[/]")
            return
        self._audit_worker()

    @work(exclusive=True)
    async def _audit_worker(self) -> None:
        assert self.source and self.target
        self.log_line(f"[b]audit[/] {self.source} → {self.target} …")
        try:
            result, patch = await audit(self.ctx, source_slug=self.source, target_ref=self.target)
        except ControlXError as exc:
            self.log_line(f"[{ERR}]✗ {esc(exc.message)}[/]")
            if exc.hint:
                self.log_line(f"[{MUTED}]hint: {esc(exc.hint)}[/]")
            return
        self.patch_id = patch.id
        for probe_result in result.results:
            style = VERDICT_STYLE[probe_result.verdict]
            self.log_line(
                f"  [{style}]{probe_result.verdict.glyph}[/] {esc(probe_result.question)}"
            )
        self.log_line(f"[b]score {result.score_pct}%[/]  patch {patch.id}")
        self._render_status()
        self._render_audit(result, patch)

    def _render_audit(self, result, patch) -> None:  # type: ignore[no-untyped-def]
        lines = [
            f"[b]{result.id}[/]  {result.source_slug} → {result.target_ref}",
            f"sufficiency [b]{result.score_pct}%[/]",
            "",
        ]
        for probe_result in result.results:
            style = VERDICT_STYLE[probe_result.verdict]
            lines.append(f"[{style}]{probe_result.verdict.glyph}[/] {esc(probe_result.question)}")
            if probe_result.verdict is not Verdict.SUFFICIENT:
                lines.append(f"   [{MUTED}]{esc(probe_result.rationale)}[/]")
        for conflict in result.conflicts:
            lines.append(
                f"[{CONFLICT}]⚠[/] {esc(conflict.key)}: "
                f"{esc(conflict.source_value)} vs {esc(conflict.target_value)}"
            )
        lines += ["", f"[b]patch[/] {patch.id} — {len(patch.ops)} op(s), press p to preview"]
        self.set_side("\n".join(lines))

    def action_preview_patch(self) -> None:
        try:
            patch = resolve_patch(self.ctx, self.patch_id)
        except ControlXError as exc:
            self.log_line(f"[{WARN}]{esc(exc.message)}[/]")
            return
        self.patch_id = patch.id
        self._render_patch(patch)
        self.log_line(f"preview {patch.id} ({len(patch.ops)} ops) — press y to apply")

    def action_apply_patch(self) -> None:
        if not self.patch_id:
            self.log_line(f"[{WARN}]no patch selected; run an audit (a) first[/]")
            return
        self._apply_worker()

    @work(exclusive=True)
    async def _apply_worker(self) -> None:
        try:
            patch, result = await apply_patch(self.ctx, self.patch_id, approve=True)
        except ControlXError as exc:
            self.log_line(f"[{ERR}]✗ {esc(exc.message)}[/]")
            return
        glyph = f"[{OK}]✓[/]" if result.applied else f"[{WARN}]⚠[/]"
        self.log_line(f"{glyph} {patch.id} [{MUTED}]({patch.status.value})[/]")
        for line in result.detail.splitlines():
            self.log_line("  " + esc(line))
        self.action_refresh_registry()

    def action_reject_patch(self) -> None:
        if not self.patch_id:
            return
        from ..core.models import PatchStatus

        patch = resolve_patch(self.ctx, self.patch_id)
        patch.status = PatchStatus.REJECTED
        self.ctx.index.save_patch(patch)
        self.log_line(f"[{MUTED}]rejected {patch.id}[/]")

    def action_draft_probes(self) -> None:
        entry = self._selected()
        if not entry or entry[0] != "pack":
            self.log_line(f"[{WARN}]select a pack first[/]")
            return
        slug = entry[1].split(":", 1)[1]
        pack = draft_probes(self.ctx, slug)
        self.log_line(
            f"[{OK}]✓[/] {slug} v{pack.version}: {len(pack.probes)} probe(s) (review them)"
        )

    def action_edit_pack(self) -> None:
        import os
        import subprocess

        entry = self._selected()
        if not entry or entry[0] != "pack":
            return
        slug = entry[1].split(":", 1)[1]
        path = self.ctx.store.pack_dir(slug) / "instructions.md"
        editor = os.environ.get("EDITOR", "vi")
        with self.suspend():
            subprocess.run([editor, str(path)], check=False)
        self.log_line(f"reloaded {slug}")
        self.action_open()

    def action_help(self) -> None:
        self.set_side(HELP)

    # -------------------------------------------------------------- palette --
    def action_palette(self) -> None:
        palette = self.query_one("#palette", Input)
        palette.display = True
        palette.focus()

    def action_close_palette(self) -> None:
        palette = self.query_one("#palette", Input)
        palette.value = ""
        palette.display = False
        self.query_one("#registry").focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        command = event.value.strip()
        self.action_close_palette()
        if command:
            self._dispatch(command)

    def _dispatch(self, command: str) -> None:
        parts = command.split()
        head, args = parts[0], parts[1:]
        try:
            if head in {"quit", "q"}:
                self.exit()
            elif head == "refresh":
                self.action_refresh_registry()
            elif head == "doctor":
                for check in doctor(self.ctx):
                    glyph = f"[{OK}]✓[/]" if check["status"] == "ok" else f"[{WARN}]⚠[/]"
                    self.log_line(f"  {glyph} {check['name']}: {esc(check['detail'])}")
            elif head == "audit":
                self.action_run_audit()
            elif head == "patch" and args[:1] == ["preview"]:
                self.action_preview_patch()
            elif head == "patch" and args[:1] == ["apply"]:
                self.action_apply_patch()
            elif head == "pack" and args[:1] == ["new"]:
                pack = self.ctx.store.create(args[1])
                self.log_line(f"[{OK}]✓[/] created {pack.slug}")
                self.action_refresh_registry()
            elif head == "pack" and args[:1] == ["import"]:
                pack = import_pack(self.ctx, Path(args[1]))
                self.log_line(f"[{OK}]✓[/] imported {pack.slug}")
                self.action_refresh_registry()
            elif head == "pack" and args[:1] == ["export"]:
                fmt = args[2] if len(args) > 2 else "dir"
                self.log_line(f"[{OK}]✓[/] {export_pack(self.ctx, args[1], fmt)}")
            elif head == "probe" and args[:1] == ["draft"]:
                pack = draft_probes(self.ctx, args[1])
                self.log_line(f"[{OK}]✓[/] {pack.slug}: {len(pack.probes)} probe(s)")
            elif head == "workspace" and args[:1] == ["add"]:
                from ..services import add_workspace

                workspace = add_workspace(
                    self.ctx, provider=args[1], name=" ".join(args[2:]) or args[1]
                )
                self.log_line(f"[{OK}]✓[/] {workspace.name} → {workspace.ref}")
                self.action_refresh_registry()
            elif head == "mcp":
                self.log_line(
                    f"[{WARN}]run the MCP server in its own window:[/] controlx mcp serve "
                    "(or `controlx tmux attach`)"
                )
            elif head == "help":
                self.action_help()
            else:
                self.log_line(f"[{WARN}]unknown command:[/] {esc(command)}")
        except ControlXError as exc:
            self.log_line(f"[{ERR}]✗ {esc(exc.message)}[/]")
        except IndexError:
            self.log_line(f"[{WARN}]missing argument[/]")

    def on_unmount(self) -> None:
        self.ctx.close()


def run_tui(home: Path | None = None) -> None:
    ControlXApp(home).run()
