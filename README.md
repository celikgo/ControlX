# ControlX

**Do not copy prompts. Measure whether one project can carry another, then apply the missing pieces to any provider.**

ControlX is an open-source, terminal-native engineering control plane for multi-project,
multi-provider AI work. It is not a chat app and not a multi-model playground.
The daily verb is `audit`, not `chat`.

```
controlx audit run --source demo-service --target pack:demo-thin

╭────────────────────── aud_1f2c9a4e77 ──────────────────────╮
│ demo-service → pack:demo-thin                              │
│ sufficiency: 41.7%                                         │
╰────────────────────────────────────────────────────────────╯
  ✓ How do Tenant and Workspace relate…?
  ✓ What shape does an HTTP error body take…?
  ✗ Explain how the client refreshes an access token after a 401.
      target covers none of: refreshes on 401; single-flight; rotates the refresh token
  ✗ What must happen before and during a production rollout?
  ⚠ Which API style does this product expose, and is GraphQL allowed?
  ◐ What are the logging and tracing requirements for a service?

  missing instructions: Auth token refresh, Deploy checklist, API style, Observability
  patch: pat_9c31be0a52  →  controlx patch preview pat_9c31be0a52
```

---

## The problem

You pay for ChatGPT, Claude and Grok. The same product knowledge lives in all three,
badly:

- ChatGPT Project A has the instructions, the files and the questions you keep asking.
- Claude Project B is missing half of it.
- Cursor, Claude Code and Codex start from zero every session.

So you copy the questions out of A, paste them into B, ask "is this enough?", read a
list of gaps, and patch B by hand. Then you do it again next week, in the other
direction, for the third provider.

## The thesis

Treat provider projects as **deploy targets** and a local pack as the **repository**.

```
select a source pack  →  run its probe set against a target
                      →  get a scored gap report
                      →  approve a patch
                      →  apply it (API, MCP, or a paste-ready bundle)
```

## Core objects

| Object | What it is |
| --- | --- |
| **Pack** | The canonical, versioned project brain: instructions, constraints, prompts, knowledge, probes, decisions. Markdown + YAML in your vault. |
| **Workspace** | A provider endpoint: an OpenAI project, a Claude project, a Grok conversation, an MCP agent. |
| **Probe** | One sufficiency question plus the signals a real answer must contain. |
| **Bridge** | A source pack → target workspace link. |
| **Audit** | Verdict per probe (`sufficient / partial / missing / conflict`) and a score. |
| **Patch** | The concrete operations that close the gap. Never applied without approval. |

---

## Install

```bash
# with uv (recommended)
uv sync
uv run controlx --help

# or plain pip
python3 -m venv .venv && .venv/bin/pip install -e ".[dev,mcp]"
.venv/bin/controlx --help

# as a tool
uv tool install controlx     # or: pipx install controlx
```

## 90-second demo (offline, no API keys)

```bash
controlx init
controlx demo
```

`controlx demo` imports two packs — `demo-service` (complete) and `demo-thin` (half) —
audits one against the other, drafts a patch, applies it and re-audits. Nothing leaves
your machine. Run it step by step instead:

```bash
controlx pack import examples/packs/demo-service
controlx pack import examples/packs/demo-thin

controlx audit run --source demo-service --target pack:demo-thin   # 41.7%
controlx patch preview latest
controlx patch apply latest --approve
controlx audit run --source demo-service --target pack:demo-thin   # 83.3%
```

The score does not reach 100%, and that is the point: `demo-thin` declares
`api_style: GraphQL first` while `demo-service` declares `REST only`. ControlX flags a
**conflict** and refuses to silently overwrite it. Contradictions are a human decision.

## BYOK — auditing a live provider project

```bash
controlx auth add --provider openai --mode api_key     # stored in the OS keyring
controlx auth test openai

controlx workspace add --provider anthropic --name "Claude / Nakitte" --model claude-sonnet-5
controlx audit run --source demo-service --target anthropic:default --min-score 70
```

Exit codes: `0` ok · `1` user error · `2` provider error · `3` audit below `--min-score`
(useful in CI: fail a build when the assistant context regresses).

### Subscriptions vs API keys

ControlX will **not** scrape private session cookies out of chatgpt.com, claude.ai or
grok.com. No vendor publishes a supported way for a third-party app to act on a consumer
subscription. So:

- `--mode api_key` → full automation: probe, audit, judge.
- `--mode session` → an explicit **LIMITED** paste-only workspace. `patch apply` emits an
  inject bundle (instruction block + file upload checklist), copies it to your clipboard,
  and tells you plainly that nothing was written remotely.

See [docs/PROVIDERS.md](docs/PROVIDERS.md).

## The terminal app

```bash
controlx           # four-pane TUI
controlx shell     # REPL over the same commands
controlx tmux attach   # cx-main / cx-audit / cx-mcp windows
```

```
┌ registry ────┬ pack ───────────────────────┬ audit / patch ─┐
│ ◆ demo-service│ ## Auth token refresh       │ aud_… 41.7%    │
│ ◆ demo-thin   │ - refreshes on 401, never…  │ ✓ domain model │
│ ● Claude / …  │ - single-flight refresh     │ ✗ token refresh│
│               ├ runner ─────────────────────┤ ⚠ api_style    │
│               │ audit demo-service → pack:… │ patch pat_… 9  │
└───────────────┴─────────────────────────────┴────────────────┘
 s source · t target · a audit · p preview · y apply · : palette · ? help
```

## MCP — hand the vault to your coding agent

```bash
controlx mcp serve            # stdio
```

```json
{
  "mcpServers": {
    "controlx": { "command": "controlx", "args": ["mcp", "serve"] }
  }
}
```

Tools: `list_packs`, `get_pack`, `search_packs`, `run_audit`, `get_latest_audit`,
`get_patch_preview`, `save_decision`, `add_probe`, `handoff_passport`.
HTTP transport binds `127.0.0.1` only.

## Non-goals (v0.1)

- Hosted SaaS, team permissions, SSO
- Replacing the native ChatGPT / Claude project UIs
- Silent full-chat memory sync — every change is an approved patch
- A general multi-model chat playground

## Security

- API keys live in the OS keyring (Keychain / secret-service / Credential Manager), with an
  optional passphrase-encrypted file fallback. Never in the vault, never in logs.
- Retrieved pack text is treated as **data**, never as instructions to execute.
- The MCP server binds `127.0.0.1`.
- No telemetry.

## Roadmap (P1)

Same-project twins across providers with drift view · provider-tuned prompt variants ·
bidirectional bridges · auto-probe generation · conflict detector across whole packs ·
cost router (cheap model probes, strong model synthesis) · `pack log` / `rollback`.

## Docs

[ARCHITECTURE](docs/ARCHITECTURE.md) · [AUDIT](docs/AUDIT.md) · [VAULT](docs/VAULT.md) ·
[PROVIDERS](docs/PROVIDERS.md) · [MCP](docs/MCP.md)

## Credits

ControlX stands on prior open-source work — Context Passport, vaultex, opencontext,
local-memory-mcp, memside, Agent-Mind-Bridge, ContextVolt, cross-llm-mcp, Textual, Rich and
the MCP SDK. See [NOTICE](NOTICE).

Apache-2.0.
