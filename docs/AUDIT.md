# The audit algorithm (v0.1)

## Steps

1. **Probes.** Take `source.probes`. If the source has none, `generate_probes()` drafts
   up to 8 from its instruction headings and marks them `generated=true` so a human
   reviews them before they mean anything.

2. **Ask.** Each probe is sent to the target **independently**, with this framing:

   ```
   You are being evaluated as workspace {target}.
   Answer only from your available project context.
   If the context is insufficient, say INSUFFICIENT and list what is missing.

   Question: {probe.question}
   ```

   For an offline `pack:<slug>` target, "asking" means retrieving from that pack's own
   corpus (instructions, constraints, prompts, knowledge, decisions) — see
   `core/corpus.py`. The retrieval is hinted with the probe's expected signals, so the
   verdict answers exactly one question: *does the target pack contain this or not?*

3. **Judge.** Two implementations:

   - `HeuristicJudge` (default): a signal counts as covered only if it appears as a
     **normalized substring** of the answer (lowercased, markdown emphasis stripped,
     whitespace collapsed). Deliberately literal — no fuzzy token matching, because a
     false `sufficient` silently tells you a project carries context it does not.
   - `LLMJudge`: asks a model for structured JSON, and falls back to the heuristic
     whenever the model returns something unusable.

   | matched signals | verdict |
   | --- | --- |
   | all | `sufficient` |
   | some | `partial` |
   | none | `missing` |
   | any, but the constraint contradicts the source | `conflict` |

4. **Score.**

   ```
   credit = {sufficient: 1.0, partial: 0.5, missing: 0.0, conflict: 0.0}
   score  = 100 × Σ(credit × weight) / Σ(weight)
   ```

   A conflict scores zero *and* is reported separately: it is not a gap you can fill by
   copying text, it is a decision someone has to make.

5. **Conflicts.** Same constraint key, different value, between source and target packs.
   `api_style: REST only` vs `api_style: GraphQL first` is a conflict; a target that
   simply says nothing about `api_style` is a gap.

6. **Patch.** For each missing signal, find the source instruction section that contains
   it and emit `append_instruction` (or `replace_instruction_section` when the target
   already has that heading). Signals that live in a knowledge document become
   `add_knowledge_manifest` ops marked `NEEDS_UPLOAD`. Failing probes become `add_probe`
   ops so the target owns the same test. Conflicts become `record_decision` ops —
   ControlX never overwrites a contradiction.

Nothing is applied automatically. Ever.

## Why the score usually stops below 100

The shipped demo lands on **83.3%** after a full apply. The last probe is a conflict:
`demo-service` says REST only, `demo-thin` says GraphQL first. Copying text cannot
resolve that, so the score keeps showing it. That is the product working, not a bug.

## Tuning

- `weight` on a probe: make the token-refresh rule count triple if that is what breaks
  production.
- `--min-score` on `audit run`: exit code 3 below the threshold, so CI can fail a build
  when the assistant context regresses.
- `[judge] mode = "llm"` in `config.toml` plus a provider/model for model-graded audits.
