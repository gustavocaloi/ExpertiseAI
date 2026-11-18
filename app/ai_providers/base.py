from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Protocol


@dataclass
class Turn:
    turn_index: int
    speaker: str
    text: str
    t_start: Optional[float] = None
    t_end: Optional[float] = None


@dataclass
class TranscriptionResult:
    turns: list[Turn]
    language: Optional[str] = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PillarDef:
    id: int
    name: str
    description: str
    prompt: str
    weight: float = 1.0
    version: int = 1


@dataclass
class TurnScore:
    turn_index: int
    score: float
    evidence: str = ""


@dataclass
class PillarEvaluation:
    pillar_id: int
    pillar_name: str
    pillar_version: int
    score: float
    rationale: str = ""
    turn_scores: list[TurnScore] = field(default_factory=list)


class AIProvider(Protocol):
    name: str

    async def transcribe(
        self,
        audio_path: Path,
        *,
        language: str | None = None,
    ) -> TranscriptionResult: ...

    async def evaluate_pillar(
        self,
        *,
        pillar: PillarDef,
        turns: list[Turn],
        metadata: dict[str, Any],
    ) -> PillarEvaluation: ...
