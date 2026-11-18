from __future__ import annotations

from typing import Any

from .. import config
from .base import AIProvider
from .mock import MockAIProvider
from .stubs import AnthropicProvider, GroqProvider, OpenAIProvider


_PROVIDERS: dict[str, type] = {
    "mock": MockAIProvider,
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "claude": AnthropicProvider,
    "groq": GroqProvider,
}


def validate_provider(name: str) -> None:
    factory = _PROVIDERS.get(name)
    if factory is None:
        raise ValueError(f"Provedor desconhecido: {name}")
    if name != "mock" and not config.MONITORIA_REAL_AI_ENABLED:
        raise ValueError("IA real desativada pela flag EXPAI_MONITORIA_REAL_AI_ENABLED")
    if not getattr(factory, "implemented", True):
        raise ValueError(f"Provedor '{name}' ainda não implementado; a flag não habilita uma integração inexistente")


def get_ai_provider(provider_name: str | None = None, **_: Any) -> AIProvider:
    name = (provider_name or config.AI_PROVIDER or "mock").strip().lower() or "mock"
    validate_provider(name)
    return _PROVIDERS[name]()
