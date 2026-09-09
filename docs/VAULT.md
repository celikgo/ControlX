# The vault

Everything lives under `$CONTROLX_HOME` (default `~/.controlx`). Markdown is the source
of truth; SQLite is a rebuildable index.

```
~/.controlx/
  config.toml
  controlx.db                 # index only - deleting it loses no pack data
  logs/
  exports/                    # inject bundles, passports, exported packs
  vault/
    packs/<slug>/
      pack.yaml               # id, name, version, constraints, knowledge manifest
      instructions.md         # the standing rules
      probes.yaml             # sufficiency questions + expected signals
      prompts/<title>.md      # YAML front matter + body
      knowledge/<title>.md
      decisions/<date>-<title>.md
      variants/<provider>.md  # optional per-provider instruction overlay
    audits/<audit-id>.json
    patches/<patch-id>.json
```

## Why markdown

`git init` inside `~/.controlx/vault` and every instruction change becomes a reviewable
diff. Writes are deterministic — sorted YAML keys, stable file names — so a save with no
semantic change produces no diff noise.

## Versioning

`save(pack, bump=True)` sets `parent_version = version` and increments. A patch apply
always bumps, so `demo-thin v1 → v2` is the record that ControlX changed it.

## Probes

```yaml
- id: prb_tokenrefresh
  question: Explain how the client refreshes an access token after a 401.
  expected_signals:
  - refreshes on 401
  - single-flight
  - rotates the refresh token
  weight: 1.0
```

Write signals as **phrases that literally appear** in the instructions. The judge is a
substring matcher by default; scattered keywords will not (and should not) count.

## Constraints

```yaml
constraints:
- key: api_style
  value: REST only
  rationale: one transport keeps clients and gateways simple
```

Constraints are what the conflict detector compares between two packs. Use a stable key.

## Importing

- `controlx pack import ./some-pack` — a directory with `pack.yaml` round-trips exactly.
- `controlx pack import ./notes` — a plain folder of markdown becomes `instructions.md`
  (or `README.md`) plus one knowledge doc per remaining file.
