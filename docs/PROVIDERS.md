# Providers

| Provider | Complete | List projects | Write instructions | Upload files | Notes |
| --- | --- | --- | --- | --- | --- |
| `openai` | ✓ (API key) | — | — | — | Chat Completions; retries with `max_completion_tokens` |
| `anthropic` | ✓ (API key) | — | — | — | Messages API, `anthropic-version: 2023-06-01` |
| `xai` | ✓ (API key) | — | — | — | OpenAI-compatible wire format on `api.x.ai` |
| `local` (`pack:<slug>`) | ✓ offline | ✓ | ✓ | ✓ | ControlX owns the files |
| `inject` (`--mode session`) | — | — | — | — | **LIMITED**: paste bundle + upload checklist |

Aliases: `chatgpt`/`gpt` → `openai`, `claude` → `anthropic`, `grok`/`x` → `xai`.

## Subscriptions are not API credentials

A ChatGPT Plus, Claude Pro or X Premium subscription is a licence for *you* to use a web
UI. None of these vendors publishes a supported way for a third-party application to act
on that subscription — there is no OAuth flow, and no documented project-write API.

ControlX therefore:

- **does** support BYOK API keys for full automation;
- **does** support an explicit, user-created `session` workspace that produces a
  paste-ready bundle;
- **does not** scrape session cookies, drive a hidden browser, or call private endpoints.

`controlx auth add --mode oauth` prints exactly this and exits 1. That is deliberate:
pretending would produce a tool that breaks the week a vendor rotates a cookie format,
and would put the user's account at risk.

## What `patch apply` does per target

```
capabilities.can_write_instructions == True   → the adapter writes, version bumps
capabilities.can_write_instructions == False  → inject bundle written to
                                                ~/.controlx/exports/inject-<patch>.md,
                                                copied to the clipboard,
                                                and the CLI says NOTHING was changed
```

The fallback never reports success. Check `applied` in the output, or the patch status:
`applied` means written, `approved` means "you still have to paste it".

## Adding a provider

1. Subclass `HttpProviderAdapter` in `controlx/adapters/providers/`, implement
   `complete()` and any capability you can honestly claim.
2. Register it in `registry.py`.
3. Add a recorded-HTTP contract test in `tests/test_providers.py` (respx, no live keys).

## Keys

Resolution order: `CONTROLX_<PROVIDER>_API_KEY` → the vendor's own env var
(`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `XAI_API_KEY`) → OS keyring → passphrase-encrypted
file (`CONTROLX_PASSPHRASE`). Multiple accounts per provider via `--account`.
