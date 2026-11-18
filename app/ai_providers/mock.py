from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .base import PillarDef, PillarEvaluation, TranscriptionResult, Turn, TurnScore


class MockAIProvider:
    """Deterministic STT + pillar evaluation for local development."""

    name = "mock"

    async def transcribe(
        self,
        audio_path: Path,
        *,
        language: str | None = None,
    ) -> TranscriptionResult:
        scripts = {
            "cobranca": [
                "Olá, minha mensalidade foi cobrada duas vezes. Preciso desse dinheiro.",
                "Olá! Sou a Ana. Entendo sua preocupação. Vou verificar a cobrança com você.",
                "São duas cobranças de R$ 129,90 no mesmo dia.",
                "Encontrei a duplicidade. Vou solicitar o estorno de R$ 129,90, sem custo.",
                "Quando o valor volta para minha conta?",
                "O prazo é de até cinco dias úteis. Você receberá a confirmação por e-mail hoje.",
                "Certo. Posso acompanhar pelo protocolo?",
                "Sim, o protocolo é 45821. Vou acompanhar o estorno. Posso ajudar em mais alguma coisa?",
            ],
            "suporte": [
                "Meu sistema não abre e tenho clientes esperando há vinte minutos.",
                "Já tentou reiniciar? Geralmente resolve.",
                "Duas vezes. Continuo vendo a mensagem de erro 503.",
                "Certo, desculpe por repetir a orientação. Identifiquei uma instabilidade no serviço.",
                "Existe alguma alternativa para eu continuar trabalhando?",
                "Você pode usar o acesso de contingência. Vou enviar as instruções e acompanhar o teste.",
                "Consegui acessar! E o sistema principal?",
                "A equipe técnica está atuando, ainda sem prazo confirmado. Atualizarei este ticket em trinta minutos.",
            ],
            "cancelamento": [
                "Quero cancelar. Pedi ajuda três vezes e ninguém resolveu.",
                "Mas nosso plano tem muitos benefícios. Quer conhecer uma oferta?",
                "Não quero oferta. Preciso cancelar hoje.",
                "Entendo. Desculpe por insistir. Vou seguir com o cancelamento como você pediu.",
                "Vai ter alguma cobrança depois disso?",
                "Não haverá nova mensalidade. Vou confirmar o encerramento por e-mail ainda hoje.",
                "Tudo bem, vou aguardar a confirmação.",
                "Cancelamento registrado no protocolo 45823. Lamento a experiência e agradeço seu retorno.",
            ],
        }
        key = next((key for key in scripts if key in audio_path.stem), "cobranca")
        script = [("cliente" if i % 2 == 0 else "operador", text) for i, text in enumerate(scripts[key])]
        turns: list[Turn] = []
        cursor = 0.0
        for index, (speaker, text) in enumerate(script):
            duration = 4.0 + (index % 3)
            turns.append(
                Turn(
                    turn_index=index,
                    speaker=speaker,
                    text=text,
                    t_start=cursor,
                    t_end=cursor + duration,
                )
            )
            cursor += duration
        return TranscriptionResult(turns=turns, language=language or "pt", raw={"provider": self.name})

    async def evaluate_pillar(
        self,
        *,
        pillar: PillarDef,
        turns: list[Turn],
        metadata: dict[str, Any],
    ) -> PillarEvaluation:
        seed = f"{pillar.name}:{pillar.prompt}:{metadata.get('ticket_id')}:{len(turns)}"
        base = int(hashlib.sha1(seed.encode("utf-8")).hexdigest()[:8], 16)
        aggregate = 55 + (base % 40)
        turn_scores: list[TurnScore] = []
        for turn in turns:
            local = 50 + ((base + turn.turn_index * 17 + len(turn.text)) % 45)
            if turn.speaker == "operador":
                local = min(100, local + 5)
            evidence = "Evidência ilustrativa (simulação): " + turn.text[:180]
            turn_scores.append(
                TurnScore(
                    turn_index=turn.turn_index,
                    score=float(local),
                    evidence=evidence,
                )
            )
        if turn_scores:
            aggregate = round(sum(item.score for item in turn_scores) / len(turn_scores), 1)
        rationale = (
            f"Avaliação mock do pilar '{pillar.name}' com base em {len(turns)} turnos "
            f"e peso {pillar.weight}."
        )
        return PillarEvaluation(
            pillar_id=pillar.id,
            pillar_name=pillar.name,
            pillar_version=pillar.version,
            score=float(aggregate),
            rationale=rationale,
            turn_scores=turn_scores,
        )
