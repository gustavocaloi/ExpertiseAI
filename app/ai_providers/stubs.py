from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import PillarDef, PillarEvaluation, TranscriptionResult, Turn


class _UnimplementedProvider:
    name = "unimplemented"
    implemented = False

    def __init__(self, provider_name: str):
        self.name = provider_name

    async def transcribe(
        self,
        audio_path: Path,
        *,
        language: str | None = None,
    ) -> TranscriptionResult:
        raise NotImplementedError(
            f"Provedor '{self.name}' ainda não implementado. Use EXPAI_AI_PROVIDER=mock nesta fase."
        )

    async def evaluate_pillar(
        self,
        *,
        pillar: PillarDef,
        turns: list[Turn],
        metadata: dict[str, Any],
    ) -> PillarEvaluation:
        raise NotImplementedError(
            f"Provedor '{self.name}' ainda não implementado. Use EXPAI_AI_PROVIDER=mock nesta fase."
        )


class OpenAIProvider(_UnimplementedProvider):
    def __init__(self) -> None:
        super().__init__("openai")


class AnthropicProvider(_UnimplementedProvider):
    def __init__(self) -> None:
        super().__init__("anthropic")


class GroqProvider(_UnimplementedProvider):
    def __init__(self) -> None:
        super().__init__("groq")
