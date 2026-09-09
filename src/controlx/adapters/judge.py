"""LLM judge.

Used when the operator wants a model, not string matching, to decide whether an
answer covers a probe. Falls back to the deterministic HeuristicJudge whenever
the model returns something unusable - the audit must never silently invent a
verdict.
"""

from __future__ import annotations

import json
import re

from ..core.audit import HeuristicJudge
from ..core.models import Probe, ProbeResult, Verdict
from ..core.ports import Completion, CompletionRequest, ProviderAdapter
from ..core.textutil import excerpt
from ..errors import ProviderError

JUDGE_SYSTEM = (
    "You grade whether an AI workspace's answer already carries the required project "
    "context. You are strict: an answer that merely sounds plausible but does not state "
    "the expected content is not sufficient. Reply with JSON only."
)

JUDGE_TEMPLATE = """Question asked of the target workspace:
{question}

Expected signals (facts the answer must actually contain):
{signals}

The target workspace answered:
---
{answer}
---

Return JSON exactly:
{{"verdict": "sufficient|partial|missing|conflict",
  "confidence": 0.0-1.0,
  "matched": ["..."],
  "missing_items": ["..."],
  "conflict_with_source": ["..."],
  "rationale": "one sentence"}}"""

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


class LLMJudge:
    id = "llm"

    def __init__(self, adapter: ProviderAdapter, model: str | None = None) -> None:
        self.adapter = adapter
        self.model = model
        self._fallback = HeuristicJudge()

    async def judge(self, probe: Probe, answer: Completion) -> ProbeResult:
        prompt = JUDGE_TEMPLATE.format(
            question=probe.question,
            signals="\n".join(f"- {s}" for s in probe.expected_signals) or "- (none specified)",
            answer=answer.text[:6000],
        )
        try:
            verdict_completion = await self.adapter.complete(
                CompletionRequest(
                    prompt=prompt,
                    system=JUDGE_SYSTEM,
                    model=self.model,
                    json_mode=True,
                    max_tokens=600,
                )
            )
            data = _parse(verdict_completion.text)
        except (ProviderError, ValueError):
            result = await self._fallback.judge(probe, answer)
            result.rationale = f"llm judge unavailable, fell back to heuristic: {result.rationale}"
            return result

        verdict = Verdict(str(data.get("verdict", "missing")).lower())
        return ProbeResult(
            probe_id=probe.id,
            question=probe.question,
            verdict=verdict,
            weight=probe.weight,
            target_answer_excerpt=excerpt(answer.text),
            rationale=str(data.get("rationale", ""))[:400],
            matched_signals=[str(x) for x in data.get("matched", [])],
            missing_signals=[str(x) for x in data.get("missing_items", [])],
            citations=list(answer.citations),
        )


def _parse(text: str) -> dict:
    match = _JSON_RE.search(text or "")
    if not match:
        raise ValueError("judge returned no JSON")
    return dict(json.loads(match.group(0)))
