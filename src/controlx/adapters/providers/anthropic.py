"""Anthropic Messages API."""

from __future__ import annotations

from ...core.ports import Completion, CompletionRequest
from .http_base import HttpProviderAdapter

API_VERSION = "2023-06-01"


class AnthropicAdapter(HttpProviderAdapter):
    id = "anthropic"
    base_url = "https://api.anthropic.com/v1"
    default_model = "claude-sonnet-5"

    def headers(self) -> dict[str, str]:
        return {
            "x-api-key": self._require_key(),
            "anthropic-version": API_VERSION,
            "Content-Type": "application/json",
        }

    async def complete(self, req: CompletionRequest) -> Completion:
        payload: dict = {
            "model": req.model or self.model,
            "max_tokens": req.max_tokens,
            "temperature": req.temperature,
            "messages": [{"role": "user", "content": req.prompt}],
        }
        if req.system:
            payload["system"] = req.system
        data = await self._post("/messages", payload)
        blocks = data.get("content") or []
        text = "".join(block.get("text", "") for block in blocks if block.get("type") == "text")
        usage = {k: int(v) for k, v in (data.get("usage") or {}).items() if isinstance(v, int)}
        return Completion(text=text, model=data.get("model", req.model or self.model), usage=usage)
