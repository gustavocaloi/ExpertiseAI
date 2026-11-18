from __future__ import annotations

import asyncio
import logging
import shutil
import uuid
import wave
from pathlib import Path
from typing import Any, Optional

from .ai_providers import PillarDef, get_ai_provider
from .monitoria_validation import validate_transcription, validate_evaluation
from .config import MONITORIA_ROOT
from . import monitoria_db as mdb
from . import config
from .monitoria_runtime import require_processing, upload_provider
from .maintenance import background_storage, storage_access, MaintenanceBusy, finish_thread

logger = logging.getLogger(__name__)

_ACTIVE_JOBS: set[str] = set()  # diagnostics only; ownership lives in SQLite
_JOB_TASKS: set[asyncio.Task] = set()
LEASE_SECONDS = 60
HEARTBEAT_SECONDS = 15
PROVIDER_TIMEOUT_SECONDS = 120


def conversation_dir(company_id: int, conversation_uuid: str) -> Path:
    path = Path(MONITORIA_ROOT) / str(company_id) / conversation_uuid
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_audio_file(
    company_id: int,
    conversation_uuid: str,
    *,
    filename: str,
    source_path: Path,
) -> Path:
    target_dir = conversation_dir(company_id, conversation_uuid)
    safe_name = Path(filename or "audio.bin").name
    target = target_dir / safe_name
    shutil.copyfile(source_path, target)
    return target


async def _renew_lease(company_id, job_id, owner, lost):
    try:
        while True:
            await asyncio.sleep(HEARTBEAT_SECONDS)
            if not await asyncio.to_thread(mdb.renew_job_lease, company_id, job_id, owner, LEASE_SECONDS):
                lost.set()
                return
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("Falha ao renovar lease de monitoria %s", job_id)
        lost.set()


@background_storage
async def process_conversation_job(company_id: int, job_id: str, conversation_uuid: str) -> None:
    owner = uuid.uuid4().hex
    if not mdb.claim_job(company_id, job_id, conversation_uuid, owner, LEASE_SECONDS):
        return  # another worker owns it, or it already has a terminal result
    _ACTIVE_JOBS.add(job_id)
    lost = asyncio.Event()
    heartbeat = asyncio.create_task(_renew_lease(company_id, job_id, owner, lost))
    try:
        conversation = mdb.get_conversation_by_uuid(company_id, conversation_uuid)
        settings = mdb.get_ai_settings(company_id)
        require_processing(settings)
        # Snapshot before the first provider await; concurrent admin edits apply to later jobs.
        pillars = mdb.list_pillars(company_id, active_only=True)
        if not pillars:
            raise ValueError("Configuração pendente: cadastre ou ative pelo menos um pilar antes da análise")
        provider_name = str(conversation.get("provider") or "mock")
        if provider_name != "mock" and not config.MONITORIA_REAL_AI_ENABLED:
            raise ValueError("IA real desativada: job real bloqueado; envie novamente para uma análise simulada")
        provider = get_ai_provider(provider_name)
        audio_path = Path(conversation.get("audio_path") or "")
        if not audio_path.is_file():
            raise ValueError("Arquivo de áudio não encontrado")
        transcription = await asyncio.wait_for(provider.transcribe(audio_path,
            language=str(settings.get("language") or "pt")), timeout=PROVIDER_TIMEOUT_SECONDS)
        validate_transcription(transcription)
        metadata = {key: conversation.get(key) for key in
                    ("ticket_id", "cliente", "tipo", "area", "categoria", "central_id", "team_id", "operador_user_id", "analista_user_id")}
        turn_indices = {turn.turn_index for turn in transcription.turns}
        pillar_scores, turn_scores = [], []
        for pillar in pillars:
            if lost.is_set():
                raise RuntimeError("Autorização de execução expirada")
            definition = PillarDef(id=pillar["id"], name=pillar["name"], description=pillar["description"],
                prompt=pillar["prompt"], weight=pillar["weight"], version=pillar["version"])
            evaluation = await asyncio.wait_for(provider.evaluate_pillar(pillar=definition,
                turns=transcription.turns, metadata=metadata), timeout=PROVIDER_TIMEOUT_SECONDS)
            validate_evaluation(evaluation, definition, turn_indices)
            pillar_scores.append({"pillar_id": definition.id, "pillar_name": definition.name,
                "pillar_version": definition.version, "prompt": definition.prompt, "description": definition.description,
                "weight": definition.weight, "score": evaluation.score, "rationale": evaluation.rationale})
            for item in evaluation.turn_scores:
                turn_scores.append({"turn_index": item.turn_index, "pillar_id": definition.id,
                    "pillar_name": definition.name, "score": item.score, "evidence": item.evidence})
        validate_transcription(transcription)
        if lost.is_set():
            raise RuntimeError("Autorização de execução expirada")
        config_snapshot = {"provider": provider.name, "language": settings.get("language") or "pt",
            "implementation": "mock-v1" if provider.name == "mock" else None,
            "real_ai_enabled": config.MONITORIA_REAL_AI_ENABLED,
            "metadata": metadata}
        if not mdb.complete_job(company_id, job_id, owner, transcription.turns, pillar_scores, turn_scores, config_snapshot):
            logger.warning("Resultado descartado: lease expirada ou substituída para job %s", job_id)
    except asyncio.CancelledError:
        mdb.fail_owned_job(company_id, job_id, owner, "Processamento interrompido pelo encerramento do worker")
        raise
    except Exception as exc:
        logger.exception("Falha no job de monitoria %s", job_id)
        message = str(exc) if isinstance(exc, ValueError) else "Falha no processamento; consulte os logs do servidor"
        mdb.fail_owned_job(company_id, job_id, owner, message)
    finally:
        heartbeat.cancel()
        await asyncio.gather(heartbeat, return_exceptions=True)
        _ACTIVE_JOBS.discard(job_id)


def start_conversation_job(company_id: int, job_id: str, conversation_uuid: str) -> None:
    task = asyncio.create_task(process_conversation_job(company_id, job_id, conversation_uuid))
    _JOB_TASKS.add(task)
    task.add_done_callback(_JOB_TASKS.discard)


DEMO_SCENARIOS = [
    ("cobranca", "DEMO-001", "Mariana Souza", "Cobrança", "Central de relacionamento", "Financeiro"),
    ("suporte", "DEMO-002", "Rafael Lima", "Suporte", "Central técnica", "Suporte N1"),
    ("cancelamento", "DEMO-003", "Camila Alves", "Cancelamento", "Central de relacionamento", "Retenção"),
]


async def create_demo_conversation(company_id: int, *, operador_user_id: Optional[int] = None, scenario: int = 0) -> dict[str, Any]:
    """Idempotent fictional dataset. Never replaces company settings or memberships."""
    require_processing(mdb.get_ai_settings(company_id))
    key, ticket, client, kind, central_name, team_name = DEMO_SCENARIOS[scenario]
    conversation_uuid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"expertise-monitoria-demo:{company_id}:{key}"))
    existing = mdb.get_conversation_by_uuid(company_id, conversation_uuid)
    if existing:
        return {"conversation_uuid": conversation_uuid, "status": existing["status"], "is_mock": True}
    areas = mdb.db.list_taxonomies(company_id, "area")
    area = areas[scenario % len(areas)] if areas else ""
    categories = [c['name'] for c in mdb.db.list_taxonomies(company_id, "categoria") if c['area'] == area]
    categoria = categories[0] if categories else ""
    if not mdb.list_pillars(company_id, active_only=True):
        for name, description, weight in [
            ("Empatia", "Reconhecer a necessidade e acolher o cliente com escuta ativa.", 1),
            ("Clareza", "Explicar a solução, os prazos e os próximos passos sem ambiguidades.", 1),
            ("Profissionalismo", "Manter respeito, responsabilidade e postura durante todo o atendimento.", 1),
            ("Resolutividade", "Encaminhar uma solução e confirmar se a demanda foi atendida.", 2),
        ]:
            mdb.create_pillar(company_id, name, description=description, prompt=description, weight=weight)
    audio = conversation_dir(company_id, conversation_uuid) / f"demo-{key}.wav"
    with wave.open(str(audio), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(b"\x00\x00" * 8000 * 40)
    mdb.create_conversation(company_id, conversation_uuid, ticket_id=ticket, cliente=client, tipo=kind,
        area=area, categoria=categoria, operador_user_id=operador_user_id,
        analista_user_id=operador_user_id, audio_path=str(audio), audio_filename=audio.name)
    job_id = str(uuid.uuid4())
    mdb.create_job(company_id, job_id, conversation_uuid)
    await process_conversation_job(company_id, job_id, conversation_uuid)
    return {"job_id": job_id, "conversation_uuid": conversation_uuid,
            "status": mdb.get_job(company_id, job_id)["status"], "is_mock": True}


async def create_conversation_from_upload(
    company_id: int,
    *,
    tmp_audio_path: Path,
    audio_filename: str,
    ticket_id: str = "",
    cliente: str = "",
    tipo: str = "",
    area: str = "",
    categoria: str = "",
    central_id: Optional[int] = None,
    team_id: Optional[int] = None,
    operador_user_id: Optional[int] = None,
    analista_user_id: Optional[int] = None,
) -> dict[str, Any]:
    settings = mdb.get_ai_settings(company_id)
    provider_name = upload_provider(settings)
    if not mdb.list_pillars(company_id, active_only=True):
        raise ValueError("Configuração pendente: cadastre ou ative pelo menos um pilar antes da análise")
    conversation_uuid = str(uuid.uuid4())
    job_id = str(uuid.uuid4())
    stored_audio = await asyncio.to_thread(
        save_audio_file,
        company_id,
        conversation_uuid,
        filename=audio_filename,
        source_path=tmp_audio_path,
    )
    conversation = mdb.create_conversation(
        company_id,
        conversation_uuid,
        ticket_id=ticket_id,
        cliente=cliente,
        tipo=tipo, area=area, categoria=categoria,
        central_id=central_id,
        team_id=team_id,
        operador_user_id=operador_user_id,
        analista_user_id=analista_user_id,
        audio_path=str(stored_audio),
        audio_filename=audio_filename,
        status="queued",
        provider=provider_name,
    )
    job = mdb.create_job(company_id, job_id, conversation_uuid, status="queued")
    start_conversation_job(company_id, job_id, conversation_uuid)
    return {
        "job_id": job["job_id"],
        "status": job["status"],
        "conversation_uuid": conversation_uuid,
        "is_mock": provider_name == "mock",
        "conversation": {key: value for key, value in conversation.items() if key != "audio_path"},
    }


def cleanup_zombie_monitoria_jobs() -> int:
    """Only expire persisted leases, never infer liveness from process-local memory."""
    return mdb.expire_job_leases()


# A small persistent queue for batches. Each API process runs at most two batch jobs.
# Queued jobs survive restarts; in-flight jobs retain the existing lease/failure semantics.
_BATCH_WORKERS = {}  # event loop -> dispatcher (also supports isolated TestClient loops)
BATCH_CONCURRENCY = 2


def start_batch_worker():
    loop = asyncio.get_running_loop()
    task = _BATCH_WORKERS.get(loop)
    if task is None or task.done():
        task = loop.create_task(batch_worker_loop())
        _BATCH_WORKERS[loop] = task
        task.add_done_callback(lambda completed: _BATCH_WORKERS.pop(loop, None)
                               if _BATCH_WORKERS.get(loop) is completed else None)
    return task


async def batch_worker_loop():
    running = {}
    try:
        while True:
            for job_id, task in list(running.items()):
                if task.done():
                    if not task.cancelled() and task.exception():
                        logger.error('Falha ao iniciar job de lote %s', job_id, exc_info=task.exception())
                    del running[job_id]
            slots = BATCH_CONCURRENCY - len(running)
            if slots > 0:
                try:
                    with storage_access():
                        pending = await finish_thread(mdb.pending_batch_jobs, slots)
                        for job in pending:
                            if job['job_id'] not in running:
                                task = asyncio.create_task(process_conversation_job(job['company_id'], job['job_id'], job['conversation_uuid']))
                                running[job['job_id']] = task
                                _JOB_TASKS.add(task)
                                task.add_done_callback(_JOB_TASKS.discard)
                except MaintenanceBusy:
                    pass
                except Exception:
                    logger.exception('Falha ao consultar fila de lotes; nova tentativa em breve')
            await asyncio.sleep(0.5)
    finally:
        for task in running.values():
            task.cancel()
        await asyncio.gather(*running.values(), return_exceptions=True)


async def create_batch_from_uploads(company_id, created_by, request_key, fingerprint, items):
    import sqlite3

    def existing_batch():
        existing = mdb.find_batch_request(company_id, created_by, request_key)
        if existing and existing['fingerprint'] != fingerprint:
            raise ValueError('Identificador de envio já utilizado com outros arquivos ou metadados')
        return existing

    if existing := existing_batch():
        start_batch_worker()
        return existing['batch_id']
    provider = upload_provider(mdb.get_ai_settings(company_id))
    if not mdb.list_pillars(company_id, active_only=True):
        raise ValueError('Configuração pendente: cadastre ou ative pelo menos um pilar antes da análise')
    batch_id = str(uuid.uuid4())
    saved = []
    try:
        for item in items:
            if item.get('error_message'):
                continue
            conversation_uuid = str(uuid.uuid4())
            # Reuse the same file storage helper as individual uploads.
            target = conversation_dir(company_id, conversation_uuid) / item['filename']
            saved.append(target)
            try:
                copying = asyncio.create_task(asyncio.to_thread(save_audio_file, company_id, conversation_uuid,
                    filename=item['filename'], source_path=item['tmp_path']))
                try:
                    stored = await asyncio.shield(copying)
                except asyncio.CancelledError:
                    await asyncio.gather(copying, return_exceptions=True)
                    raise
                item.update(conversation_uuid=conversation_uuid, job_id=str(uuid.uuid4()), audio_path=str(stored))
            except OSError:
                logger.exception('Falha ao armazenar item %s do lote', item['index'])
                item['error_message'] = 'Não foi possível armazenar este áudio. Envie o arquivo novamente.'
        try:
            mdb.persist_batch(company_id, created_by, batch_id, request_key, fingerprint, items, provider)
        except sqlite3.IntegrityError:
            if not (existing := existing_batch()):
                raise
            batch_id = existing['batch_id']
        else:
            saved = [path for path in saved if not any(item.get('audio_path') == str(path) for item in items)]
    finally:
        for path in saved:
            try:
                path.unlink(missing_ok=True)
                path.parent.rmdir()
            except OSError:
                logger.warning('Não foi possível remover arquivo temporário de lote', exc_info=True)
    start_batch_worker()
    return batch_id
