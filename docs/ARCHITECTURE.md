# Architecture

ControlX is hexagonal. `core/` holds the domain and the algorithms and imports **no**
I/O framework. Everything that touches a disk, a socket or a keyring is an adapter
behind a port.

```
┌──────────────────────────────────────────────────────────────────────┐
│                        controlx TUI (Textual)                        │
│   registry │ pack viewer │ runner log │ audit-patch │ palette        │
└───────────────┬──────────────────────────────────────┬───────────────┘
                │                                      │
        ┌───────▼────────┐                    ┌────────▼────────┐
        │  services.py   │  ◄── CLI (Typer) ──┤   MCP server    │
        │  (use cases)   │                    │   (FastMCP /    │
        └───────┬────────┘                    │    MCPServer)   │
                │                             └─────────────────┘
    ┌───────────┼───────────────┬────────────────┐
    ▼           ▼               ▼                ▼
 PackStore   Index          SecretStore     Provider adapters
 (markdown)  (sqlite)       (keyring)       openai │ anthropic │ xai
                                            local  │ inject
                │
                ▼
        core/  models · audit · patcher · corpus · passport · textutil
```

## Layers

| Package | Rule |
| --- | --- |
| `controlx/core` | Pure domain. `mypy --strict` clean. No httpx, no sqlite, no Textual. |
| `controlx/adapters` | Vault, SQLite index, keyring, provider HTTP, LLM judge. |
| `controlx/services.py` | Use cases. The **only** thing the CLI, TUI and MCP call. |
| `controlx/cli.py` | Typer surface. Maps `ControlXError` to exit codes at the group level. |
| `controlx/tui` | Textual app. Never calls an adapter directly. |
| `controlx/mcp` | Tool surface over the same services. |

`services.py` is what keeps CLI/TUI parity honest: if a button exists in the TUI and
no command exists in the CLI, they would have to diverge on purpose.

## Ports

`core/ports.py` defines them as `Protocol`s:

- `ProviderAdapter` — `health`, `complete`, `list_remote_projects`, `pull_project`,
  `apply_patch`, `capabilities`
- `Judge` — `judge(probe, answer) -> ProbeResult`
- `PackStorePort`, `IndexPort`

Every adapter answers `capabilities()` with a `Capabilities` record. That record —
not a hard-coded `if provider == "openai"` — decides whether `patch apply` writes or
falls back to an inject bundle.

## Data flow of one audit

```
source Pack ──probes──► target adapter.complete()  ──answer──► Judge
                                                                 │
              conflicts ◄── constraints diff                     ▼
                    │                                       ProbeResult[]
                    └──────────────► Audit (score) ──► compose_patch ──► Patch
                                                                          │
                                              approve ────────────────────┘
                                                 │
                       writable target ──────────┼────────── non-writable target
                       patcher.apply_patch_to_pack        render_inject_bundle
                       (version bump in the vault)        (file + clipboard)
```

## Why Python

The workload is I/O and text, not compute: HTTP calls to model APIs, markdown reads,
substring matching. Textual is the strongest dense-TUI toolkit available, the MCP SDK
is first-party, and the target user already has a Python toolchain. The domain in
`core/` is deliberately dependency-light (pydantic only) so it stays portable if the
distribution story ever demands a single static binary.

## Concurrency

Provider calls are `async` (httpx). The CLI wraps them in `asyncio.run`; the TUI runs
them in Textual workers on the same event loop — never in a thread, because the SQLite
connection is single-threaded by design.
