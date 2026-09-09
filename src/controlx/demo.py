"""`controlx demo` - the 90-second offline golden path.

No API keys, no network. Proves the product thesis on two local packs.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from rich.console import Console
from rich.rule import Rule

from .context import AppContext
from .services import EXAMPLES_DIR, apply_patch, audit, import_pack, init_home
from .theme import rich_theme

console = Console(theme=rich_theme())


def run_demo(home: Path | None = None) -> None:
    init_home(home)
    context = AppContext.load(home)

    console.print(Rule("1. import the two demo packs"))
    for slug in ("demo-service", "demo-thin"):
        if context.store.exists(slug):
            console.print(f"  [muted]{slug} already in vault[/]")
        else:
            pack = import_pack(context, EXAMPLES_DIR / slug)
            console.print(f"  [ok]✓[/] imported {pack.slug} v{pack.version}")

    console.print(Rule("2. can demo-thin carry demo-service?"))
    before, patch = asyncio.run(
        audit(context, source_slug="demo-service", target_ref="pack:demo-thin")
    )
    _summary(before)

    console.print(Rule("3. patch preview (nothing written yet)"))
    console.print(f"  {len(patch.ops)} operation(s) drafted → controlx patch preview {patch.id}")

    console.print(Rule("4. apply"))
    _, result = asyncio.run(apply_patch(context, patch.id, approve=True))
    for line in result.detail.splitlines():
        console.print("  " + line)

    console.print(Rule("5. re-audit"))
    after, _ = asyncio.run(audit(context, source_slug="demo-service", target_ref="pack:demo-thin"))
    _summary(after)

    delta = round(after.score_pct - before.score_pct, 1)
    console.print(
        f"\n[bold]sufficiency {before.score_pct}% → {after.score_pct}%[/] ([ok]+{delta}[/])"
    )
    if after.conflicts:
        console.print(
            "[conflict]⚠[/] the remaining gap is a real conflict "
            f"({', '.join(c.key for c in after.conflicts)}); ControlX never resolves that for you."
        )
    context.close()


def _summary(result) -> None:  # type: ignore[no-untyped-def]
    counts = result.counts
    console.print(
        f"  score [bold]{result.score_pct}%[/]  "
        f"✓{counts['sufficient']} ◐{counts['partial']} ✗{counts['missing']} ⚠{counts['conflict']}"
    )
    for item in result.missing_instructions:
        console.print(f"    [err]missing instruction:[/] {item}")
