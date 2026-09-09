"""xAI / Grok. OpenAI-compatible wire format on a different host."""

from __future__ import annotations

from .openai import OpenAIAdapter


class XAIAdapter(OpenAIAdapter):
    id = "xai"
    base_url = "https://api.x.ai/v1"
    default_model = "grok-4"
