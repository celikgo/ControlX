"""tmux helper.

The TUI is the control plane; tmux is optional scaffolding for people who want
long-running jobs in their own window.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from .errors import UserError

SESSION = "controlx"


def _require_tmux() -> str:
    path = shutil.which("tmux")
    if path is None:
        raise UserError("tmux is not installed", hint="brew install tmux (optional)")
    return path


def inside_tmux() -> bool:
    return bool(os.environ.get("TMUX"))


def tmux_attach(home: Path | None = None) -> None:
    """Create (or reuse) a `controlx` session with cx-main / cx-audit / cx-mcp."""
    tmux = _require_tmux()
    env = f"CONTROLX_HOME={home} " if home else ""
    exists = (
        subprocess.run([tmux, "has-session", "-t", SESSION], capture_output=True).returncode == 0
    )
    if not exists:
        subprocess.run(
            [tmux, "new-session", "-d", "-s", SESSION, "-n", "cx-main", f"{env}controlx"],
            check=True,
        )
        subprocess.run([tmux, "new-window", "-t", SESSION, "-n", "cx-audit"], check=True)
        subprocess.run(
            [tmux, "new-window", "-t", SESSION, "-n", "cx-mcp", f"{env}controlx mcp serve"],
            check=True,
        )
    if inside_tmux():
        os.execvp(tmux, [tmux, "switch-client", "-t", SESSION])
    os.execvp(tmux, [tmux, "attach-session", "-t", SESSION])


def tmux_split(command: str = "controlx shell") -> None:
    """Split the current tmux pane and run a ControlX command in it."""
    tmux = _require_tmux()
    if not inside_tmux():
        raise UserError("not inside tmux", hint="run `controlx tmux attach` instead")
    subprocess.run([tmux, "split-window", "-h", command], check=True)
