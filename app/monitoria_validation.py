"""Validation at the provider boundary; no network or provider credentials needed."""
from __future__ import annotations

import math
from numbers import Real

from .ai_providers.base import PillarDef, PillarEvaluation, TranscriptionResult


def _number(value, label, minimum=0, maximum=None):
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
        raise ValueError(f"Resposta inválida do provedor: {label} deve ser um número finito")
    if value < minimum or (maximum is not None and value > maximum):
        raise ValueError(f"Resposta inválida do provedor: {label} fora do intervalo permitido")


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Resposta incompleta do provedor: {label} é obrigatório")


def validate_transcription(result: TranscriptionResult) -> None:
    if not result.turns:
        raise ValueError("Resposta incompleta do provedor: transcrição vazia")
    previous_index = -1
    previous_start = -1
    for turn in result.turns:
        if type(turn.turn_index) is not int or turn.turn_index <= previous_index:
            raise ValueError("Resposta inválida do provedor: índices de falas devem ser únicos e ordenados")
        if turn.speaker not in {"cliente", "operador"}:
            raise ValueError("Resposta inválida do provedor: falante desconhecido")
        _text(turn.text, "texto da fala")
        _number(turn.t_start, "início da fala")
        _number(turn.t_end, "fim da fala")
        if turn.t_end <= turn.t_start or turn.t_start < previous_start:
            raise ValueError("Resposta inválida do provedor: timestamps inconsistentes")
        previous_index, previous_start = turn.turn_index, turn.t_start


def validate_evaluation(result: PillarEvaluation, pillar: PillarDef, turn_indices: set[int]) -> None:
    if (type(result.pillar_id) is not int or type(result.pillar_version) is not int
        or (result.pillar_id, result.pillar_name, result.pillar_version) != (pillar.id, pillar.name, pillar.version)):
        raise ValueError("Resposta inválida do provedor: pilar ou versão incorretos")
    _number(result.score, "nota do pilar", maximum=100)
    _text(result.rationale, "justificativa do pilar")
    seen = set()
    for item in result.turn_scores:
        if type(item.turn_index) is not int or item.turn_index not in turn_indices or item.turn_index in seen:
            raise ValueError("Resposta inválida do provedor: referência de fala desconhecida ou duplicada")
        _number(item.score, "nota da interação", maximum=100)
        _text(item.evidence, "evidência da interação")
        seen.add(item.turn_index)
    if seen != turn_indices:
        raise ValueError("Resposta incompleta do provedor: faltam avaliações por interação")
