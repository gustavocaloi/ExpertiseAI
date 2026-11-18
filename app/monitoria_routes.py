from __future__ import annotations

import logging
import hashlib
import json
import uuid
import tempfile
from pathlib import Path
from typing import Optional

from fastapi.responses import FileResponse

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .config import ACCESS_CONTROL_ENABLED, DATA_DIR
from .security import TokenData, get_monitoria_scope, require_company_access, require_monitoria_role, assert_module_access
from . import config
from .monitoria_runtime import require_processing, upload_provider, runtime_status
from . import db
from . import monitoria_db as mdb
from . import monitoria_services

logger = logging.getLogger(__name__)

router = APIRouter(tags=["monitoria"])

_TMP_UPLOADS = Path(DATA_DIR) / "_tmp_monitoria_uploads"
_TMP_UPLOADS.mkdir(parents=True, exist_ok=True)


class CentralCreate(BaseModel):
    name: str = Field(min_length=1)


class CentralUpdate(BaseModel):
    name: Optional[str] = None
    is_active: Optional[bool] = None


class TeamCreate(BaseModel):
    name: str = Field(min_length=1)
    central_id: int


class TeamUpdate(BaseModel):
    name: Optional[str] = None
    is_active: Optional[bool] = None


class MembershipCreate(BaseModel):
    user_id: int
    role: str
    central_id: Optional[int] = None
    team_id: Optional[int] = None


class PillarCreate(BaseModel):
    name: str = Field(min_length=1)
    description: str = ""
    prompt: str = ""
    weight: float = Field(default=1.0, gt=0, le=100, allow_inf_nan=False)


class PillarUpdate(BaseModel):
    description: Optional[str] = None
    prompt: Optional[str] = None
    weight: Optional[float] = Field(default=None, gt=0, le=100, allow_inf_nan=False)
    is_active: Optional[bool] = None
    bump_version: bool = False


class AiSettingsUpdate(BaseModel):
    provider: Optional[str] = None
    transcription_model: Optional[str] = None
    evaluation_model: Optional[str] = None
    language: Optional[str] = None
    temperature: Optional[float] = None
    is_enabled: Optional[bool] = None


def require_monitoria_admin(auth=Depends(require_monitoria_role("monitoria_admin"))):
    if not auth[1].is_full_access:
        raise HTTPException(status_code=403, detail="Configuração exige administrador da empresa")
    return auth


def _visible_org(company_id, scope):
    if scope.is_full_access:
        return None, None
    clause, params = mdb._scope_sql_clause(scope)
    conn = db.get_connection()
    try:
        rows = conn.execute(f"SELECT DISTINCT central_id, team_id FROM monitoria_conversations c WHERE c.company_id = ? AND {clause}", [company_id, *params]).fetchall()
    finally:
        conn.close()
    teams = {r["team_id"] for r in rows} | scope.team_ids
    centrals = {r["central_id"] for r in rows} | scope.central_ids
    for team_id in scope.team_ids:
        team = mdb.get_team(company_id, team_id)
        if team:
            centrals.add(team["central_id"])
    return centrals, teams


def _assert_metadata(company_id, scope, central_id, team_id, operador_user_id, analista_user_id, area="", categoria=""):
    if central_id is not None or team_id is not None:
        raise HTTPException(status_code=422, detail="Use area e categoria do cadastro existente; central/equipe não são aceitas em novos envios")
    areas = db.list_taxonomies(company_id, "area")
    categories = db.list_taxonomies(company_id, "categoria")
    if area and area not in areas:
        raise HTTPException(status_code=422, detail="Área não pertence ao cadastro ativo da empresa")
    if categoria and not any(c['name'] == categoria and c['area'] == area for c in categories):
        raise HTTPException(status_code=422, detail="Categoria não pertence à área da empresa")
    for user_id in (operador_user_id, analista_user_id):
        if user_id is not None and not db.get_user_roles_in_company(user_id, company_id):
            raise HTTPException(status_code=422, detail="Usuário sem vínculo ativo com a empresa")
    if not scope.can_access_conversation({"company_id": company_id, "area": area, "categoria": categoria,
        "operador_user_id": operador_user_id, "analista_user_id": analista_user_id}):
        raise HTTPException(status_code=403, detail="Upload fora do seu escopo de áreas")
    return None


def _require_processing(company_id, *, demo=False):
    settings = mdb.get_ai_settings(company_id)
    try:
        require_processing(settings) if demo else upload_provider(settings)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def _assert_company(company_id: int, user: TokenData) -> None:
    if ACCESS_CONTROL_ENABLED and user.company_id != company_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Token fora do contexto da empresa")


@router.get("/empresas/{company_id}/monitoria/escopo")
def get_escopo(
    company_id: int,
    user: TokenData = Depends(require_company_access),
):
    _assert_company(company_id, user)
    assert_module_access(company_id, user, "monitoria")
    scope = get_monitoria_scope(company_id, user)
    return {
        "runtime": runtime_status(mdb.get_ai_settings(company_id)),
        "user_id": scope.user_id,
        "company_id": scope.company_id,
        "is_full_access": scope.is_full_access,
        "roles": scope.roles,
        "area_mode": scope.area_mode or "all",
        "allowed_areas": sorted(scope.allowed_areas),
        "central_ids": sorted(scope.central_ids),
        "team_ids": sorted(scope.team_ids),
        "operator_only": scope.operator_only,
        "assigned_analyst_only": scope.assigned_analyst_only,
    }


@router.get("/empresas/{company_id}/monitoria/centrais")
def list_centrals(
    company_id: int,
    auth=Depends(require_monitoria_role(
        "monitoria_admin", "monitoria_supervisor", "monitoria_analista", "monitoria_operador"
    )),
):
    centrals, _ = _visible_org(company_id, auth[1])
    return {"items": [c for c in mdb.list_centrals(company_id) if centrals is None or c["id"] in centrals]}


@router.post("/empresas/{company_id}/monitoria/centrais", status_code=status.HTTP_201_CREATED)
def create_central(
    company_id: int,
    payload: CentralCreate,
    auth=Depends(require_monitoria_admin),
):
    raise HTTPException(status_code=410, detail="Use Gestão de Acessos e as áreas/categorias existentes")


@router.patch("/empresas/{company_id}/monitoria/centrais/{central_id}")
def update_central(
    company_id: int,
    central_id: int,
    payload: CentralUpdate,
    auth=Depends(require_monitoria_admin),
):
    raise HTTPException(status_code=410, detail="Use Gestão de Acessos e as áreas/categorias existentes")


@router.get("/empresas/{company_id}/monitoria/equipes")
def list_teams(
    company_id: int,
    central_id: Optional[int] = None,
    auth=Depends(require_monitoria_role(
        "monitoria_admin", "monitoria_supervisor", "monitoria_analista", "monitoria_operador"
    )),
):
    _, teams = _visible_org(company_id, auth[1])
    return {"items": [t for t in mdb.list_teams(company_id, central_id=central_id)
                      if teams is None or t["id"] in teams or t["central_id"] in auth[1].central_ids]}


@router.post("/empresas/{company_id}/monitoria/equipes", status_code=status.HTTP_201_CREATED)
def create_team(
    company_id: int,
    payload: TeamCreate,
    auth=Depends(require_monitoria_admin),
):
    raise HTTPException(status_code=410, detail="Use Gestão de Acessos e as áreas/categorias existentes")


@router.patch("/empresas/{company_id}/monitoria/equipes/{team_id}")
def update_team(
    company_id: int,
    team_id: int,
    payload: TeamUpdate,
    auth=Depends(require_monitoria_admin),
):
    raise HTTPException(status_code=410, detail="Use Gestão de Acessos e as áreas/categorias existentes")


@router.get("/empresas/{company_id}/monitoria/memberships")
def list_memberships(
    company_id: int,
    user_id: Optional[int] = None,
    auth=Depends(require_monitoria_admin),
):
    return {"items": mdb.list_memberships(company_id, user_id=user_id)}


@router.post("/empresas/{company_id}/monitoria/memberships", status_code=status.HTTP_201_CREATED)
def create_membership(
    company_id: int,
    payload: MembershipCreate,
    auth=Depends(require_monitoria_admin),
):
    raise HTTPException(status_code=410, detail="Use Gestão de Acessos e as áreas/categorias existentes")


@router.delete("/empresas/{company_id}/monitoria/memberships/{membership_id}")
def deactivate_membership(
    company_id: int,
    membership_id: int,
    auth=Depends(require_monitoria_admin),
):
    updated = mdb.deactivate_membership(company_id, membership_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Membership não encontrado")
    return updated


@router.get("/empresas/{company_id}/monitoria/pilares")
def list_pillars(
    company_id: int,
    active_only: bool = True,
    auth=Depends(require_monitoria_role(
        "monitoria_admin", "monitoria_supervisor", "monitoria_analista", "monitoria_operador"
    )),
):
    return {"items": mdb.list_pillars(company_id, active_only=active_only)}


@router.post("/empresas/{company_id}/monitoria/pilares", status_code=status.HTTP_201_CREATED)
def create_pillar(
    company_id: int,
    payload: PillarCreate,
    auth=Depends(require_monitoria_admin),
):
    try:
        return mdb.create_pillar(
            company_id,
            payload.name,
            description=payload.description,
            prompt=payload.prompt,
            weight=payload.weight,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/empresas/{company_id}/monitoria/pilares/{pillar_id}")
def update_pillar(
    company_id: int,
    pillar_id: int,
    payload: PillarUpdate,
    auth=Depends(require_monitoria_admin),
):
    updated = mdb.update_pillar(
        company_id,
        pillar_id,
        description=payload.description,
        prompt=payload.prompt,
        weight=payload.weight,
        is_active=payload.is_active,
        bump_version=payload.bump_version,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Pilar não encontrado")
    return updated


@router.get("/empresas/{company_id}/monitoria/ai-settings")
def get_ai_settings(
    company_id: int,
    auth=Depends(require_monitoria_admin),
):
    settings = mdb.get_ai_settings(company_id)
    return {**settings, "runtime": runtime_status(settings)}


@router.put("/empresas/{company_id}/monitoria/ai-settings")
def put_ai_settings(
    company_id: int,
    payload: AiSettingsUpdate,
    auth=Depends(require_monitoria_admin),
):
    if payload.provider is not None:
        if payload.provider not in {"mock", "openai", "anthropic", "claude", "groq"}:
            raise HTTPException(status_code=422, detail="Provedor desconhecido")
        if payload.provider != "mock" and not config.MONITORIA_REAL_AI_ENABLED:
            raise HTTPException(status_code=422, detail="IA real desativada pela flag do servidor; apenas mock pode ser selecionado")
    settings = mdb.upsert_ai_settings(
        company_id,
        provider=payload.provider,
        transcription_model=payload.transcription_model,
        evaluation_model=payload.evaluation_model,
        language=payload.language,
        temperature=payload.temperature,
        is_enabled=payload.is_enabled,
    )
    return {**settings, "runtime": runtime_status(settings)}


@router.post("/empresas/{company_id}/monitoria/conversas/exemplo", status_code=201)
async def create_example_conversation(company_id: int, auth=Depends(require_monitoria_admin)):
    _require_processing(company_id, demo=True)
    return await monitoria_services.create_demo_conversation(company_id, operador_user_id=auth[0].user_id or None)


@router.post("/empresas/{company_id}/monitoria/demo", status_code=201)
async def create_demo_dataset(company_id: int, auth=Depends(require_monitoria_admin)):
    _require_processing(company_id, demo=True)
    items = []
    for scenario in range(len(monitoria_services.DEMO_SCENARIOS)):
        items.append(await monitoria_services.create_demo_conversation(company_id,
            operador_user_id=auth[0].user_id or None, scenario=scenario))
    return {"items": items, "is_mock": True}


@router.post("/empresas/{company_id}/monitoria/conversas/upload", status_code=status.HTTP_202_ACCEPTED)
async def upload_conversation(
    company_id: int,
    file: UploadFile = File(...),
    ticket_id: str = Form(""),
    cliente: str = Form(""),
    tipo: str = Form(""),
    area: str = Form(""),
    categoria: str = Form(""),
    central_id: Optional[int] = Form(None),
    team_id: Optional[int] = Form(None),
    operador_user_id: Optional[int] = Form(None),
    analista_user_id: Optional[int] = Form(None),
    auth=Depends(require_monitoria_role(
        "monitoria_admin", "monitoria_supervisor", "monitoria_analista"
    )),
):
    user, scope = auth
    _require_processing(company_id)
    if not mdb.list_pillars(company_id, active_only=True):
        raise HTTPException(status_code=409, detail="Configuração pendente: cadastre ou ative pelo menos um pilar antes da análise")
    if scope.assigned_analyst_only and analista_user_id is None:
        analista_user_id = user.user_id
    central_id = _assert_metadata(company_id, scope, central_id, team_id, operador_user_id, analista_user_id, area, categoria)
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".wav", ".mp3", ".ogg", ".m4a", ".flac", ".webm", ".aac"}:
        raise HTTPException(status_code=415, detail="Envie áudio WAV, MP3, OGG, M4A, FLAC, WEBM ou AAC")
    _TMP_UPLOADS.mkdir(parents=True, exist_ok=True)
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, dir=_TMP_UPLOADS, suffix=suffix) as tmp:
            tmp_path = Path(tmp.name)
            size = 0
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > 25 * 1024 * 1024:
                    raise HTTPException(status_code=413, detail="Limite de áudio: 25 MB")
                tmp.write(chunk)
        if not size:
            raise HTTPException(status_code=422, detail="Arquivo vazio")
        return await monitoria_services.create_conversation_from_upload(
            company_id, tmp_audio_path=tmp_path, audio_filename=file.filename,
            ticket_id=ticket_id, cliente=cliente, tipo=tipo, area=area, categoria=categoria, central_id=central_id, team_id=team_id,
            operador_user_id=operador_user_id, analista_user_id=analista_user_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    finally:
        await file.close()
        if tmp_path:
            tmp_path.unlink(missing_ok=True)


@router.get("/empresas/{company_id}/monitoria/jobs")
def list_jobs(
    company_id: int,
    status_filter: Optional[str] = Query(None, alias="status"),
    auth=Depends(require_monitoria_role(
        "monitoria_admin", "monitoria_supervisor", "monitoria_analista"
    )),
):
    scope_sql, scope_params = mdb._scope_sql_clause(auth[1])
    conn = db.get_connection()
    try:
        rows = conn.execute(f"""SELECT j.* FROM monitoria_jobs j
            JOIN monitoria_conversations c ON c.conversation_uuid = j.conversation_uuid AND c.company_id = j.company_id
            WHERE c.company_id = ? AND {scope_sql} AND (? IS NULL OR j.status = ?)
            ORDER BY j.created_at DESC, j.id DESC LIMIT 50""", [company_id, *scope_params, status_filter, status_filter]).fetchall()
        return {"items": [dict(row) for row in rows]}
    finally:
        conn.close()


@router.get("/empresas/{company_id}/monitoria/jobs/{job_id}")
def get_job(
    company_id: int,
    job_id: str,
    auth=Depends(require_monitoria_role(
        "monitoria_admin", "monitoria_supervisor", "monitoria_analista", "monitoria_operador"
    )),
):
    job = mdb.get_job(company_id, job_id)
    conversation = mdb.get_conversation_by_uuid(company_id, job["conversation_uuid"]) if job else None
    if not job or not conversation or not auth[1].can_access_conversation(conversation):
        raise HTTPException(status_code=404, detail="Job não encontrado")
    return job


@router.get("/empresas/{company_id}/monitoria/conversas")
def list_conversations(
    company_id: int,
    area: Optional[str] = None,
    categoria: Optional[str] = None,
    central_id: Optional[int] = None,
    team_id: Optional[int] = None,
    cliente: Optional[str] = None,
    operador_user_id: Optional[int] = None,
    analista_user_id: Optional[int] = None,
    tipo: Optional[str] = None,
    pillar_id: Optional[int] = None,
    pillar_family_id: Optional[int] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    created_from: Optional[str] = None,
    created_to: Optional[str] = None,
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    auth=Depends(require_monitoria_role(
        "monitoria_admin", "monitoria_supervisor", "monitoria_analista", "monitoria_operador"
    )),
):
    _user, scope = auth
    return mdb.list_conversations(
        company_id,
        scope,
        central_id=central_id,
        team_id=team_id,
        area=area, categoria=categoria,
        cliente=cliente,
        operador_user_id=operador_user_id,
        analista_user_id=analista_user_id,
        tipo=tipo,
        pillar_id=pillar_id,
        pillar_family_id=pillar_family_id,
        status=status_filter,
        created_from=created_from,
        created_to=created_to,
        limit=limit,
        offset=offset,
    )


@router.get("/empresas/{company_id}/monitoria/conversas/{conversation_uuid}")
def get_conversation(
    company_id: int,
    conversation_uuid: str,
    auth=Depends(require_monitoria_role(
        "monitoria_admin", "monitoria_supervisor", "monitoria_analista", "monitoria_operador"
    )),
):
    _user, scope = auth
    conversation = mdb.get_conversation_by_uuid(company_id, conversation_uuid)
    if not conversation or not scope.can_access_conversation(conversation):
        raise HTTPException(status_code=404, detail="Conversa não encontrada")
    return mdb.conversation_detail_payload(conversation)


@router.get("/empresas/{company_id}/monitoria/conversas/{conversation_uuid}/audio")
def get_conversation_audio(company_id: int, conversation_uuid: str,
    auth=Depends(require_monitoria_role("monitoria_admin", "monitoria_supervisor", "monitoria_analista", "monitoria_operador"))):
    conversation = mdb.get_conversation_by_uuid(company_id, conversation_uuid)
    if not conversation or not auth[1].can_access_conversation(conversation):
        raise HTTPException(status_code=404, detail="Conversa não encontrada")
    path = Path(conversation["audio_path"]).resolve()
    root = Path(monitoria_services.MONITORIA_ROOT).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise HTTPException(status_code=404, detail="Áudio não encontrado")
    return FileResponse(path, filename=conversation["audio_filename"], content_disposition_type="inline")


MAX_BATCH_FILES = 20
MAX_BATCH_FILE_BYTES = 25 * 1024 * 1024
MAX_BATCH_TOTAL_BYTES = 200 * 1024 * 1024
BATCH_EXTENSIONS = {'.wav', '.mp3', '.ogg', '.m4a', '.flac', '.webm', '.aac'}


class BatchItemMetadata(BaseModel):
    model_config = ConfigDict(extra='forbid')
    area: str = Field(default="", max_length=200)
    categoria: str = Field(default="", max_length=200)
    ticket_id: str = Field(default='', max_length=200)
    cliente: str = Field(default='', max_length=200)
    tipo: str = Field(default='', max_length=100)
    central_id: Optional[int] = Field(default=None, gt=0)
    team_id: Optional[int] = Field(default=None, gt=0)
    operador_user_id: Optional[int] = Field(default=None, gt=0)
    analista_user_id: Optional[int] = Field(default=None, gt=0)


@router.post('/empresas/{company_id}/monitoria/conversas/upload-lote', status_code=202)
async def upload_batch(
    company_id: int,
    files: list[UploadFile] = File(...),
    metadata: str = Form(...),
    request_id: Optional[uuid.UUID] = Form(None),
    auth=Depends(require_monitoria_role('monitoria_admin', 'monitoria_supervisor', 'monitoria_analista')),
):
    user, scope = auth
    staged = []
    try:
        _require_processing(company_id)
        if not mdb.list_pillars(company_id, active_only=True):
            raise HTTPException(status_code=409, detail='Configuração pendente: cadastre ou ative pelo menos um pilar antes da análise')
        if not 1 <= len(files) <= MAX_BATCH_FILES:
            raise HTTPException(status_code=413, detail='Selecione de 1 a 20 arquivos por lote')
        if len(metadata.encode('utf-8')) > 64 * 1024:
            raise HTTPException(status_code=413, detail='Metadados do lote excedem o limite de 64 KB')
        try:
            raw_metadata = json.loads(metadata)
        except (ValueError, TypeError) as exc:
            raise HTTPException(status_code=422, detail='metadata deve ser uma lista JSON na mesma ordem dos arquivos') from exc
        if not isinstance(raw_metadata, list) or len(raw_metadata) != len(files):
            raise HTTPException(status_code=422, detail='Envie um objeto de metadados para cada arquivo, na mesma ordem')
        if sum(file.size or 0 for file in files) > MAX_BATCH_TOTAL_BYTES:
            raise HTTPException(status_code=413, detail='Limite total do lote: 200 MB')
        _TMP_UPLOADS.mkdir(parents=True, exist_ok=True)
        items, fingerprints, total = [], [], 0
        for index, (file, raw) in enumerate(zip(files, raw_metadata)):
            filename = Path(file.filename or f'audio-{index + 1}').name
            item = {'index': index, 'filename': filename, 'metadata': {}, 'error_message': ''}
            try:
                values = BatchItemMetadata.model_validate(raw).model_dump()
                if scope.assigned_analyst_only and values['analista_user_id'] is None:
                    values['analista_user_id'] = user.user_id
                values['central_id'] = _assert_metadata(company_id, scope, values['central_id'], values['team_id'],
                    values['operador_user_id'], values['analista_user_id'], values['area'], values['categoria'])
                item['metadata'] = values
            except ValidationError:
                item['error_message'] = 'Metadados inválidos: confira campos, IDs e limites de texto'
            except HTTPException as exc:
                item['error_message'] = str(exc.detail)
            if Path(filename).suffix.lower() not in BATCH_EXTENSIONS:
                item['error_message'] = 'Formato não aceito: use WAV, MP3, OGG, M4A, FLAC, WEBM ou AAC'
            digest, size = hashlib.sha256(), 0
            with tempfile.NamedTemporaryFile(delete=False, dir=_TMP_UPLOADS, suffix=Path(filename).suffix[:10]) as tmp:
                path = Path(tmp.name)
                staged.append(path)
                while chunk := await file.read(1024 * 1024):
                    size += len(chunk)
                    total += len(chunk)
                    if total > MAX_BATCH_TOTAL_BYTES:
                        raise HTTPException(status_code=413, detail='Limite total do lote: 200 MB')
                    digest.update(chunk)
                    if size <= MAX_BATCH_FILE_BYTES and not item['error_message']:
                        tmp.write(chunk)
            if size > MAX_BATCH_FILE_BYTES:
                item['error_message'] = 'Limite por áudio: 25 MB'
            elif not size:
                item['error_message'] = 'Arquivo vazio'
            item['tmp_path'] = path
            items.append(item)
            fingerprints.append({'filename': filename, 'sha256': digest.hexdigest(), 'metadata': raw})
        fingerprint = hashlib.sha256(json.dumps(fingerprints, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        try:
            batch_id = await monitoria_services.create_batch_from_uploads(company_id, user.user_id or 0,
                str(request_id or uuid.uuid4()), fingerprint, items)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        result = mdb.batch_payload(company_id, batch_id, scope)
        if result is None:
            raise HTTPException(status_code=404, detail='Lote não encontrado no seu escopo atual')
        return result
    finally:
        for file in files:
            await file.close()
        for path in staged:
            path.unlink(missing_ok=True)


@router.get('/empresas/{company_id}/monitoria/lotes')
def list_batches(company_id: int, limit: int = Query(20, ge=1, le=50),
    auth=Depends(require_monitoria_role('monitoria_admin', 'monitoria_supervisor', 'monitoria_analista'))):
    return {'items': mdb.list_batches(company_id, auth[1], limit)}


@router.get('/empresas/{company_id}/monitoria/lotes/{batch_id}')
def get_batch(company_id: int, batch_id: str,
    auth=Depends(require_monitoria_role('monitoria_admin', 'monitoria_supervisor', 'monitoria_analista'))):
    result = mdb.batch_payload(company_id, batch_id, auth[1])
    if result is None:
        raise HTTPException(status_code=404, detail='Lote não encontrado')
    return result


@router.get("/empresas/{company_id}/monitoria/taxonomias")
def get_taxonomies(company_id: int, auth=Depends(require_monitoria_role(*mdb.MONITORIA_ROLES))):
    scope = auth[1]
    areas = db.list_taxonomies(company_id, "area")
    if not scope.is_full_access and scope.area_mode == "selected":
        areas = [a for a in areas if a in scope.allowed_areas]
    return {"areas": areas, "categorias": [c for c in db.list_taxonomies(company_id, "categoria") if c['area'] in areas]}


class ConversationTaxonomy(BaseModel):
    area: str = Field(min_length=1)
    categoria: str = ""


@router.patch("/empresas/{company_id}/monitoria/conversas/{conversation_uuid}/taxonomia")
def classify_conversation(company_id: int, conversation_uuid: str, payload: ConversationTaxonomy,
    auth=Depends(require_monitoria_admin)):
    conversation = mdb.get_conversation_by_uuid(company_id, conversation_uuid)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversa não encontrada")
    _assert_metadata(company_id, auth[1], None, None, None, None, payload.area, payload.categoria)
    updated = mdb.update_conversation(company_id, conversation_uuid, area=payload.area, categoria=payload.categoria)
    return mdb.conversation_detail_payload(updated)
