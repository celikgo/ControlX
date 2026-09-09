"""`controlx shell` - a tiny REPL over the same CLI commands.

Exists so the TUI command palette and the terminal speak one language.
"""

from __future__ import annotations

import shlex
from pathlib import Path

from rich.console import Console

from .errors import ControlXError
from .theme import rich_theme

console = Console(theme=rich_theme())

BANNER = """ControlX shell. Type CLI commands without the `controlx` prefix.
  pack ls | audit run --source A --target pack:B | patch preview | doctor | quit
"""


def run_shell(home: Path | None = None) -> None:
    from .cli import app

    console.print(BANNER)
    while True:
        try:
            line = console.input("[accent bold]controlx[/] › ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print()
            return
        if not line:
            continue
        if line in {"quit", "exit", ":q"}:
            return
        argv = shlex.split(line)
        if home is not None:
            argv = ["--home", str(home), *argv]
        try:
            app(argv, standalone_mode=False)
        except ControlXError as exc:
            console.print(f"[err]✗[/] {exc.message}")
            if exc.hint:
                console.print(f"[muted]hint: {exc.hint}[/]")
        except SystemExit:
            pass
        except Exception as exc:
            console.print(f"[err]✗[/] {type(exc).__name__}: {exc}")
