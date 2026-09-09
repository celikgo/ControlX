# MCP

`controlx mcp serve` exposes the vault to any MCP client — Claude Code, Cursor, Codex,
Claude Desktop. It works with both MCP SDK generations (1.x `FastMCP`, 2.x `MCPServer`).

```bash
pip install 'controlx[mcp]'
controlx mcp serve                 # stdio (default)
controlx mcp serve --transport http  # binds 127.0.0.1 only
```

## Client config

```json
{
  "mcpServers": {
    "controlx": {
      "command": "controlx",
      "args": ["mcp", "serve"],
      "env": { "CONTROLX_HOME": "/Users/you/.controlx" }
    }
  }
}
```

## Tools

| Tool | Purpose |
| --- | --- |
| `list_packs` | slug, version, probe and knowledge counts |
| `get_pack(slug)` | full pack as JSON |
| `search_packs(query)` | packs whose instructions or prompts mention the terms |
| `run_audit(source_slug, target_ref)` | score + patch id; use `pack:<slug>` for offline |
| `get_latest_audit(source_slug?)` | last audit record |
| `get_patch_preview(ident)` | markdown preview — read-only, applying stays manual |
| `save_decision(slug, title, body)` | write a decision back into the pack |
| `add_probe(slug, question, expected_signals)` | add a sufficiency test |
| `handoff_passport(slug)` | compact markdown to seed a new agent session |

## Typical loop

1. Agent calls `handoff_passport("nakitte-core")` at session start instead of you pasting
   context.
2. Agent works; when it settles a question it calls `save_decision(...)`.
3. Next session — in any tool, on any provider — starts from that same pack.

## Security

- HTTP transport binds `127.0.0.1`. There is no auth layer; do not expose it.
- Pack text returned by these tools is **data**. A pack that contains "ignore your
  instructions" is a string in a document, not a command; ControlX never executes pack
  content, and the judge prompts treat retrieved text as quoted material.
- Write tools (`save_decision`, `add_probe`) change the vault. They bump the pack version,
  so `git diff` in the vault shows exactly what an agent did.
