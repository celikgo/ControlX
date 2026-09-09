"""MCP server: hand the vault to Cursor, Claude Code, Codex or Claude Desktop.

Binds 127.0.0.1 for HTTP transport. Pack text is data, never instructions - the
consuming agent decides what to do with it.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from ..context import AppContext
from ..core.models import Decision, Probe
from ..core.textutil import tokens
from ..errors import UserError
from ..services import audit as audit_service
from ..services import passport_markdown, resolve_patch

SERVER_NAME = "controlx"


def _server_class() -> tuple[type, int]:
    """MCP SDK 2.x renamed FastMCP to MCPServer. Support both, prefer the new one."""
    try:
        from mcp.server.mcpserver import MCPServer

        return MCPServer, 2
    except ImportError:
        pass
    try:
        from mcp.server.fastmcp import FastMCP

        return FastMCP, 1
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise UserError(
            "the MCP SDK is not installed",
            hint="pip install 'controlx[mcp]'",
        ) from exc


def build_server(home: Path | None = None):  # type: ignore[no-untyped-def]
    server_cls, major = _server_class()

    cfg_ctx = AppContext.load(home)
    if major >= 2:
        mcp = server_cls(name=SERVER_NAME)
    else:
        mcp = server_cls(SERVER_NAME, host=cfg_ctx.cfg.mcp_host, port=cfg_ctx.cfg.mcp_port)
    mcp.controlx_bind = (cfg_ctx.cfg.mcp_host, cfg_ctx.cfg.mcp_port)

    def ctx() -> AppContext:
        return AppContext.load(home)

    @mcp.tool()
    def list_packs() -> str:
        """List every pack in the ControlX vault with version and probe count."""
        context = ctx()
        rows = []
        for slug in context.store.list_packs():
            pack = context.store.load(slug)
            rows.append(
                {
                    "slug": pack.slug,
                    "name": pack.name,
                    "version": pack.version,
                    "probes": len(pack.probes),
                    "knowledge": len(pack.knowledge),
                }
            )
        return json.dumps(rows, indent=2)

    @mcp.tool()
    def get_pack(slug: str) -> str:
        """Full pack content: instructions, constraints, prompts, probes, decisions."""
        return ctx().store.load(slug).model_dump_json(indent=2)

    @mcp.tool()
    def search_packs(query: str) -> str:
        """Find packs whose instructions or prompts mention the query terms."""
        context = ctx()
        needles = tokens(query)
        hits = []
        for slug in context.store.list_packs():
            pack = context.store.load(slug)
            haystack = pack.instructions + " ".join(p.body for p in pack.prompts)
            overlap = needles & tokens(haystack)
            if overlap:
                hits.append({"slug": slug, "matched_terms": sorted(overlap)})
        return json.dumps(hits, indent=2)

    @mcp.tool()
    def get_latest_audit(source_slug: str | None = None) -> str:
        """The most recent sufficiency audit, optionally for one source pack."""
        context = ctx()
        audit_id = context.index.latest_audit_id(source_slug)
        if not audit_id:
            return json.dumps({"error": "no audits yet"})
        return context.index.load_audit(audit_id).model_dump_json(indent=2)

    @mcp.tool()
    def get_patch_preview(ident: str = "latest") -> str:
        """Markdown preview of a drafted patch. Read-only - applying stays manual."""
        return resolve_patch(ctx(), ident).preview_markdown

    @mcp.tool()
    def run_audit(source_slug: str, target_ref: str) -> str:
        """Run an audit (source pack vs target). Use pack:<slug> for an offline target."""
        context = ctx()
        result, patch = asyncio.run(
            audit_service(context, source_slug=source_slug, target_ref=target_ref)
        )
        return json.dumps(
            {
                "audit_id": result.id,
                "score_pct": result.score_pct,
                "patch_id": patch.id,
                "missing_instructions": result.missing_instructions,
                "conflicts": [c.model_dump() for c in result.conflicts],
            },
            indent=2,
        )

    @mcp.tool()
    def save_decision(slug: str, title: str, body: str, date: str | None = None) -> str:
        """Record a decision into a pack so the next session inherits it."""
        from datetime import date as date_cls

        context = ctx()
        pack = context.store.load(slug)
        pack.decisions.append(
            Decision(date=date or date_cls.today().isoformat(), title=title, body=body)
        )
        saved = context.store.save(pack, bump=True)
        return f"recorded '{title}' in {slug} v{saved.version}"

    @mcp.tool()
    def add_probe(slug: str, question: str, expected_signals: list[str] | None = None) -> str:
        """Add a sufficiency probe to a pack."""
        context = ctx()
        pack = context.store.load(slug)
        pack.probes.append(
            Probe(
                question=question,
                expected_signals=list(expected_signals or []),
                source_pack_id=pack.id,
            )
        )
        saved = context.store.save(pack, bump=True)
        return f"{slug} v{saved.version} now has {len(saved.probes)} probe(s)"

    @mcp.tool()
    def handoff_passport(slug: str) -> str:
        """Compact markdown passport to seed a new agent session."""
        return passport_markdown(ctx(), slug)

    return mcp


def serve(home: Path | None = None, transport: str = "stdio") -> None:
    server = build_server(home)
    if transport == "stdio":
        server.run(transport="stdio")
        return
    if transport not in {"http", "streamable-http", "sse"}:
        raise UserError(f"unsupported MCP transport '{transport}'", hint="stdio | http")

    host, port = getattr(server, "controlx_bind", ("127.0.0.1", 8765))
    candidates = ["sse"] if transport == "sse" else ["streamable-http", "sse"]
    for candidate in candidates:
        try:
            # localhost only: the vault is not something to expose on a LAN
            server.run(transport=candidate, host=host, port=port)
            return
        except TypeError:
            server.run(transport=candidate)
            return
        except ValueError:
            continue
    raise UserError(f"MCP transport '{transport}' is not supported by the installed SDK")
