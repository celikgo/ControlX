import httpx
import respx

from controlx.adapters.judge import LLMJudge
from controlx.adapters.providers.openai import OpenAIAdapter
from controlx.core.audit import HeuristicJudge
from controlx.core.models import Probe, Verdict
from controlx.core.ports import Completion

PROBE = Probe(question="q", expected_signals=["alpha rule", "beta rule"])


async def test_heuristic_verdicts():
    judge = HeuristicJudge()
    assert (
        await judge.judge(PROBE, Completion(text="alpha rule and beta rule"))
    ).verdict is Verdict.SUFFICIENT
    assert (
        await judge.judge(PROBE, Completion(text="only the alpha rule"))
    ).verdict is Verdict.PARTIAL
    assert (await judge.judge(PROBE, Completion(text="INSUFFICIENT"))).verdict is Verdict.MISSING


async def test_heuristic_without_signals_uses_the_insufficient_marker():
    probe = Probe(question="q")
    judge = HeuristicJudge()
    assert (
        await judge.judge(probe, Completion(text="INSUFFICIENT: no context"))
    ).verdict is Verdict.MISSING
    assert (
        await judge.judge(probe, Completion(text="here is an answer"))
    ).verdict is Verdict.PARTIAL


def _judge_response(payload: str) -> httpx.Response:
    return httpx.Response(200, json={"model": "m", "choices": [{"message": {"content": payload}}]})


@respx.mock
async def test_llm_judge_parses_json():
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=_judge_response(
            '{"verdict":"partial","matched":["alpha rule"],"missing_items":["beta rule"],'
            '"rationale":"half"}'
        )
    )
    result = await LLMJudge(OpenAIAdapter("k")).judge(PROBE, Completion(text="alpha rule"))
    assert result.verdict is Verdict.PARTIAL
    assert result.missing_signals == ["beta rule"]


@respx.mock
async def test_llm_judge_falls_back_when_the_model_misbehaves():
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(500, text="boom")
    )
    result = await LLMJudge(OpenAIAdapter("k")).judge(
        PROBE, Completion(text="alpha rule and beta rule")
    )
    assert result.verdict is Verdict.SUFFICIENT
    assert "fell back to heuristic" in result.rationale
