"""MCP surface: the vault, exposed to coding agents."""

from __future__ import annotations

import json

import pytest

from controlx.mcp.server import build_server

pytest.importorskip("mcp")


async def _call(server, name: str, **kwargs) -> str:
    """Normalize the MCP 1.x tuple return and the 2.x CallToolResult."""
    result = await server.call_tool(name, kwargs)
    content = getattr(result, "content", result)
    if isinstance(content, tuple):
        content = content[0]
    first = content[0]
    return getattr(first, "text", str(first))


async def test_expected_tools_are_exposed(demo_ctx, home):
    demo_ctx.close()
    server = build_server(home)
    names = {tool.name for tool in await server.list_tools()}
    assert {
        "list_packs",
        "get_pack",
        "search_packs",
        "run_audit",
        "get_latest_audit",
        "get_patch_preview",
        "save_decision",
        "add_probe",
        "handoff_passport",
    } <= names


async def test_list_and_read_a_pack(demo_ctx, home):
    demo_ctx.close()
    server = build_server(home)
    packs = json.loads(await _call(server, "list_packs"))
    assert {row["slug"] for row in packs} == {"demo-service", "demo-thin"}

    pack = json.loads(await _call(server, "get_pack", slug="demo-service"))
    assert "Auth token refresh" in pack["instructions"]

    hits = json.loads(await _call(server, "search_packs", query="canary rollout"))
    assert any(row["slug"] == "demo-service" for row in hits)


async def test_save_decision_and_add_probe_write_through_to_the_vault(demo_ctx, home):
    demo_ctx.close()
    server = build_server(home)
    await _call(server, "save_decision", slug="demo-thin", title="Adopt REST", body="agreed")
    await _call(
        server,
        "add_probe",
        slug="demo-thin",
        question="Which style?",
        expected_signals=["REST only"],
    )

    from controlx.context import AppContext

    ctx = AppContext.load(home)
    pack = ctx.store.load("demo-thin")
    assert [d.title for d in pack.decisions] == ["Adopt REST"]
    assert [p.question for p in pack.probes] == ["Which style?"]
    ctx.close()


async def test_handoff_passport_has_a_resume_prompt(demo_ctx, home):
    demo_ctx.close()
    passport = await _call(build_server(home), "handoff_passport", slug="demo-service")
    assert "## Resume prompt" in passport
    assert "## Open questions" in passport
