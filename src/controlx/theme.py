"""ControlX palette: X/Twitter "Dim".

One palette for the TUI (Textual CSS) and the CLI (Rich styles), so a score in
`controlx audit run` is the exact same green as the score in the TUI.

Semantic names only - never write a raw colour in a widget or a print.
"""

from __future__ import annotations

from rich.theme import Theme

# --- Dim surfaces ---------------------------------------------------------- #
BACKGROUND = "#15202B"
SURFACE = "#192734"
SURFACE_ALT = "#22303C"
BORDER = "#38444D"

# --- Type ------------------------------------------------------------------ #
TEXT = "#F7F9F9"
MUTED = "#8899A6"

# --- Signal ---------------------------------------------------------------- #
ACCENT = "#1D9BF0"
OK = "#00BA7C"
WARN = "#FFD400"
ERR = "#F4212E"
CONFLICT = "#7856FF"

RICH_STYLES = {
    "ok": OK,
    "warn": WARN,
    "err": ERR,
    "accent": ACCENT,
    "conflict": CONFLICT,
    "muted": MUTED,
    "heading": f"bold {TEXT}",
    "score.high": f"bold {OK}",
    "score.mid": f"bold {WARN}",
    "score.low": f"bold {ERR}",
}


def rich_theme() -> Theme:
    return Theme(RICH_STYLES)


#: Declared once at the top of the Textual stylesheet; widgets reference $cx-*.
TEXTUAL_VARS = f"""
$cx-bg: {BACKGROUND};
$cx-surface: {SURFACE};
$cx-surface-alt: {SURFACE_ALT};
$cx-border: {BORDER};
$cx-text: {TEXT};
$cx-muted: {MUTED};
$cx-accent: {ACCENT};
$cx-ok: {OK};
$cx-warn: {WARN};
$cx-err: {ERR};
$cx-conflict: {CONFLICT};
"""
