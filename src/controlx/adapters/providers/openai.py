"""OpenAI (and any OpenAI-compatible endpoint)."""

from __future__ import annotations

from ...core.ports import Completion, CompletionRequest
from ...errors import ProviderError
from .http_base import HttpProviderAdapter


class OpenAIAdapter(HttpProviderAdapter):
    id = "openai"
    base_url = "https://api.openai.com/v1"
    default_model = "gpt-4.1-mini"

    def _payload(self, req: CompletionRequest, *, token_key: str) -> dict:
        messages = []
        if req.system:
            messages.append({"role": "system", "content": req.system})
        messages.append({"role": "user", "content": req.prompt})
        payload: dict = {
            "model": req.model or self.model,
            "messages": messages,
            token_key: req.max_tokens,
        }
        if req.temperature is not None:
            payload["temperature"] = req.temperature
        if req.json_mode:
            payload["response_format"] = {"type": "json_object"}
        return payload

    async def complete(self, req: CompletionRequest) -> Completion:
        try:
            data = await self._post("/chat/completions", self._payload(req, token_key="max_tokens"))
        except ProviderError as exc:
            # Newer OpenAI models reject max_tokens and want max_completion_tokens.
            if "max_tokens" not in str(exc):
                raise
            data = await self._post(
                "/chat/completions", self._payload(req, token_key="max_completion_tokens")
            )
        return _completion_from_chat(data, fallback_model=req.model or self.model)


def _completion_from_chat(data: dict, fallback_model: str) -> Completion:
    choices = data.get("choices") or []
    text = ""
    if choices:
        text = (choices[0].get("message") or {}).get("content") or ""
    usage = {k: int(v) for k, v in (data.get("usage") or {}).items() if isinstance(v, int)}
    return Completion(text=text, model=data.get("model", fallback_model), usage=usage)
