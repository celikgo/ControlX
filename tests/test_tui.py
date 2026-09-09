"""TUI smoke tests via the Textual pilot. The TUI must call the same services."""

from __future__ import annotations

from pathlib import Path

import pytest

from controlx.tui.app import ControlXApp


@pytest.fixture()
def app(demo_ctx, home: Path) -> ControlXApp:
    demo_ctx.close()
    return ControlXApp(home)


async def test_app_boots_and_lists_the_vault(app: ControlXApp):
    async with app.run_test() as pilot:
        await pilot.pause()
        refs = [ref for _, ref in app.entries]
        assert "pack:demo-service" in refs and "pack:demo-thin" in refs
        # the pack pane must show something without the user pressing anything
        await pilot.pause()
        assert "Domain model" in str(app.query_one("#viewer_body").content)
        assert app.source == "demo-service"
        assert app.target == "pack:demo-thin"


async def test_first_arrow_key_moves_the_cursor(app: ControlXApp):
    """Regression: a None index on mount swallowed the user's first arrow press."""
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.query_one("#registry").index == 0
        first = str(app.query_one("#viewer_body").content)

        await pilot.press("down")
        await pilot.pause()
        assert app.query_one("#registry").index == 1
        assert str(app.query_one("#viewer_body").content) != first


async def test_palette_runs_doctor(app: ControlXApp):
    async with app.run_test() as pilot:
        await pilot.press("colon")
        palette = app.query_one("#palette")
        assert palette.display and palette.has_focus
        palette.value = "doctor"
        await pilot.press("enter")
        await pilot.pause()
        assert not palette.display
        assert app.query_one("#registry").has_focus


async def test_palette_escape_closes_without_running(app: ControlXApp):
    async with app.run_test() as pilot:
        await pilot.press("colon")
        app.query_one("#palette").value = "pack new should-not-exist"
        await pilot.press("escape")
        await pilot.pause()
        assert not app.query_one("#palette").display
        assert not app.ctx.store.exists("should-not-exist")


async def test_audit_and_apply_from_the_keyboard(app: ControlXApp):
    async with app.run_test() as pilot:
        app.source, app.target = "demo-service", "pack:demo-thin"
        await pilot.press("a")
        await pilot.pause()
        while app.workers:
            await pilot.pause(0.05)
        assert app.patch_id is not None

        await pilot.press("p")  # preview
        await pilot.press("y")  # apply
        await pilot.pause()
        while app.workers:
            await pilot.pause(0.05)
        assert app.ctx.store.load("demo-thin").version == 2


async def test_help_and_quit_bindings(app: ControlXApp):
    async with app.run_test() as pilot:
        await pilot.press("question_mark")
        await pilot.press("q")
        await pilot.pause()


async def test_bracketed_vault_text_does_not_break_the_render(app: ControlXApp):
    """Regression: a `[` in a pack (or in a probe's JSON) must stay data, not markup."""
    pack = app.ctx.store.load("demo-thin")
    pack.instructions += "\n## Arrays\n\n- signals: [one, two]\n"
    app.ctx.store.save(pack)

    async with app.run_test() as pilot:
        app.action_refresh_registry()
        app.query_one("#registry").index = 1
        await pilot.pause()
        app.source, app.target = "demo-service", "pack:demo-thin"
        await pilot.press("a")
        await pilot.pause()
        while app.workers:
            await pilot.pause(0.05)
        await pilot.press("p")
        await pilot.pause()
        assert app.patch_id is not None
