"""Adapter contract tests. Recorded HTTP only - no live keys, ever."""

from __future__ import annotations

import httpx
import pytest
import respx

from controlx.adapters.providers.anthropic import AnthropicAdapter
from controlx.adapters.providers.openai import OpenAIAdapter
from controlx.adapters.providers.registry import build_adapter, canonical_provider
from controlx.adapters.providers.xai import XAIAdapter
from controlx.core.ports import CompletionRequest
from controlx.errors import AuthError, CapabilityError, ProviderError, UserError

CHAT_RESPONSE = {
    "model": "gpt-4.1-mini",
    "choices": [{"message": {"role": "assistant", "content": "the answer"}}],
    "usage": {"prompt_tokens": 10, "completion_tokens": 4},
}

MESSAGES_RESPONSE = {
    "model": "claude-sonnet-5",
    "content": [{"type": "text", "text": "the answer"}],
    "usage": {"input_tokens": 9, "output_tokens": 3},
}


@respx.mock
async def test_openai_completion():
    route = respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=CHAT_RESPONSE)
    )
    adapter = OpenAIAdapter("sk-test")
    completion = await adapter.complete(CompletionRequest(prompt="hi", system="sys"))
    assert completion.text == "the answer"
    assert completion.usage["prompt_tokens"] == 10
    sent = route.calls.last.request
    assert sent.headers["authorization"] == "Bearer sk-test"
    body = sent.content.decode()
    assert '"system"' in body and "max_tokens" in body


@respx.mock
async def test_openai_retries_with_max_completion_tokens():
    responses = [
        httpx.Response(400, text="Unsupported parameter: 'max_tokens' is not supported"),
        httpx.Response(200, json=CHAT_RESPONSE),
    ]
    route = respx.post("https://api.openai.com/v1/chat/completions").mock(side_effect=responses)
    completion = await OpenAIAdapter("sk-test").complete(CompletionRequest(prompt="hi"))
    assert completion.text == "the answer"
    assert route.call_count == 2
    assert "max_completion_tokens" in route.calls[1].request.content.decode()


@respx.mock
async def test_anthropic_completion_uses_x_api_key():
    route = respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=httpx.Response(200, json=MESSAGES_RESPONSE)
    )
    completion = await AnthropicAdapter("sk-ant").complete(
        CompletionRequest(prompt="hi", system="sys")
    )
    assert completion.text == "the answer"
    request = route.calls.last.request
    assert request.headers["x-api-key"] == "sk-ant"
    assert request.headers["anthropic-version"] == "2023-06-01"
    assert '"system"' in request.content.decode()


@respx.mock
async def test_xai_uses_its_own_host():
    route = respx.post("https://api.x.ai/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=CHAT_RESPONSE)
    )
    await XAIAdapter("xai-key").complete(CompletionRequest(prompt="hi"))
    assert route.called


@respx.mock
async def test_401_becomes_auth_error():
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(401, json={"error": "nope"})
    )
    with pytest.raises(AuthError):
        await OpenAIAdapter("bad").complete(CompletionRequest(prompt="hi"))


@respx.mock
async def test_500_becomes_provider_error():
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(500, text="boom")
    )
    with pytest.raises(ProviderError):
        await OpenAIAdapter("sk").complete(CompletionRequest(prompt="hi"))


async def test_missing_key_is_an_auth_error():
    with pytest.raises(AuthError):
        await OpenAIAdapter(None).complete(CompletionRequest(prompt="hi"))


@respx.mock
async def test_health_reports_failure_without_raising():
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(401, text="nope")
    )
    health = await OpenAIAdapter("bad").health()
    assert not health.ok


async def test_api_adapters_do_not_claim_write_capability():
    for adapter in (OpenAIAdapter("k"), AnthropicAdapter("k"), XAIAdapter("k")):
        caps = await adapter.capabilities()
        assert not caps.can_write_instructions
        assert caps.requires_inject
        result = await adapter.apply_patch(None, None)  # type: ignore[arg-type]
        assert not result.applied
        with pytest.raises(CapabilityError):
            await adapter.pull_project("anything")


def test_registry_aliases():
    assert canonical_provider("claude") == "anthropic"
    assert canonical_provider("chatgpt") == "openai"
    assert canonical_provider("grok") == "xai"
    assert isinstance(build_adapter("claude", api_key="k"), AnthropicAdapter)
    with pytest.raises(UserError):
        build_adapter("gemini", api_key="k")
