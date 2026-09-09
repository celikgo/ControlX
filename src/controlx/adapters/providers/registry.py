"""Provider registry: name -> adapter class."""

from __future__ import annotations

from ...core.ports import ProviderAdapter
from ...errors import UserError
from .anthropic import AnthropicAdapter
from .openai import OpenAIAdapter
from .xai import XAIAdapter

ProviderRegistry: dict[str, type[OpenAIAdapter | AnthropicAdapter]] = {
    "openai": OpenAIAdapter,
    "anthropic": AnthropicAdapter,
    "xai": XAIAdapter,
}

ALIASES = {
    "chatgpt": "openai",
    "gpt": "openai",
    "claude": "anthropic",
    "grok": "xai",
    "x": "xai",
}


def canonical_provider(name: str) -> str:
    key = name.strip().lower()
    return ALIASES.get(key, key)


def build_adapter(
    provider: str,
    *,
    api_key: str | None,
    model: str | None = None,
    base_url: str | None = None,
    client=None,  # type: ignore[no-untyped-def]
) -> ProviderAdapter:
    name = canonical_provider(provider)
    if name not in ProviderRegistry:
        raise UserError(
            f"unknown provider '{provider}'",
            hint="known: "
            + ", ".join(sorted(ProviderRegistry))
            + " (plus local packs: pack:<slug>)",
        )
    return ProviderRegistry[name](api_key, model=model, base_url=base_url, client=client)
