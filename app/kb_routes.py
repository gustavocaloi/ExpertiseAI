from __future__ import annotations

import logging
import asyncio
import json
from pathlib import Path
from datetime import datetime
from typing import Any, Optional, Union
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import UploadFile, File, Form
from pydantic import BaseModel, Field

from . import db, services
from .config import ACCESS_CONTROL_ENABLED, DATA_DIR
from .security import TokenData, require_company_access, require_role


router = APIRouter()
_UPLOAD_JOBS: dict[str, dict[str, Any]] = {}
_ACTIVE_UPLOAD_JOBS: set[str] = set()
_UPLOAD_JOBS_DIR = Path(DATA_DIR) / "_upload_jobs"
_UPLOAD_JOB_STALE_SECONDS = 7200
logger = logging.getLogger(__name__)


class DocumentCreatePayload(BaseModel):
    area: Optional[str] = None
    categoria: Optional[str] = None
    slug: Optional[str] = None
    title: str = Field(..., min_length=1, max_length=256)
    content: str
    tags: list[str] = []
    ai_prompt: Optional[str] = None
    data_validade: Optional[str] = None
    base_version: Union[str, None] = None
    publicar: bool = False


class PublishPayload(BaseModel):
    version: str


class TaxonomyPayload(BaseModel):
    name: str


class CategoryPayload(BaseModel):
    name: str
    area: str


def _is_scoped_access_allowed(company_id: int, user: TokenData) -> None:
    if not ACCESS_CONTROL_ENABLED:
        return
    if user.company_id != company_id:
        raise HTTPException(status_code=403, detail="Token fora do contexto da empresa")


def _author_email(user: TokenData) -> str:
    return "anônimo" if not ACCESS_CONTROL_ENABLED else (user.email or "anônimo")


def _upload_job_path(job_id: str) -> Path:
    return _UPLOAD_JOBS_DIR / f"{job_id}.json"


def _persist_upload_job(job_id: str, payload: dict[str, Any]) -> None:
    try:
        _UPLOAD_JOBS_DIR.mkdir(parents=True, exist_ok=True)
        with _upload_job_path(job_id).open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
    except Exception:
        logger.exception("Falha ao persistir estado do job %s", job_id)


def _mark_upload_job_failed(job_id: str, payload: dict[str, Any], error_message: str) -> dict[str, Any]:
    payload.update({
        "status": "failed",
        "updated_at": datetime.utcnow().isoformat() + "Z",
        "error": error_message,
    })
    _UPLOAD_JOBS[job_id] = payload
    _persist_upload_job(job_id, payload)
    return payload


def _load_upload_job(job_id: str) -> Optional[dict[str, Any]]:
    cached = _UPLOAD_JOBS.get(job_id)
    if cached is not None:
        return cached
    path = _upload_job_path(job_id)
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            payload = json.load(f)
        created_at_raw = payload.get("created_at")
        if created_at_raw and payload.get("status") == "processing":
            try:
                created_at = datetime.fromisoformat(str(created_at_raw).replace("Z", "+00:00"))
            except ValueError:
                created_at = None
            if created_at is not None:
                elapsed = (datetime.utcnow() - created_at.replace(tzinfo=None)).total_seconds()
                if elapsed > _UPLOAD_JOB_STALE_SECONDS:
                    payload = _mark_upload_job_failed(
                        job_id,
                        payload,
                        "Processamento excedeu o limite de tempo e foi encerrado. Reenvie o arquivo.",
                    )
        _UPLOAD_JOBS[job_id] = payload
        return payload
    except Exception:
        logger.exception("Falha ao carregar estado do job %s", job_id)
        return None


def _load_company_upload_jobs(company_id: int, status_filter: Optional[str] = None) -> list[dict[str, Any]]:
    if not _UPLOAD_JOBS_DIR.exists():
        return []

    jobs: list[dict[str, Any]] = []
    for path in sorted(_UPLOAD_JOBS_DIR.glob("*.json"), reverse=True):
        payload = _load_upload_job(path.stem)
        if not isinstance(payload, dict):
            continue

        if payload.get("empresa_id") != company_id:
            continue
        if status_filter and payload.get("status") != status_filter:
            continue

        jobs.append({
            "job_id": payload.get("job_id") or path.stem,
            "status": payload.get("status", ""),
            "document_uuid": payload.get("document_uuid"),
            "empresa_id": payload.get("empresa_id"),
            "slug": payload.get("slug"),
            "area": payload.get("area") or "sem-area",
            "categoria": payload.get("categoria") or "sem-categoria",
            "title": payload.get("title") or payload.get("file_name"),
            "file_name": payload.get("file_name"),
            "created_at": payload.get("created_at", ""),
            "updated_at": payload.get("updated_at", ""),
            "error": payload.get("error"),
            "documento": payload.get("documento"),
        })
    return jobs


def _touch_upload_job(job_id: str, updates: dict[str, Any]) -> None:
    if not job_id:
        return
    if job_id not in _UPLOAD_JOBS:
        cached = _load_upload_job(job_id)
        if cached is None:
            return
    job = _UPLOAD_JOBS.get(job_id)
    if not isinstance(job, dict):
        return
    job.update(updates)
    _UPLOAD_JOBS[job_id] = job
    _persist_upload_job(job_id, job)


def cleanup_zombie_upload_jobs() -> int:
    if not _UPLOAD_JOBS_DIR.exists():
        return 0

    cleaned = 0
    for path in _UPLOAD_JOBS_DIR.glob("*.json"):
        job_id = path.stem
        payload = _load_upload_job(job_id)
        if not isinstance(payload, dict):
            continue
        if payload.get("status") != "processing":
            continue
        if job_id in _ACTIVE_UPLOAD_JOBS:
            continue
        _mark_upload_job_failed(
            job_id,
            payload,
            "Processamento interrompido antes da conclusão. Envie o arquivo novamente.",
        )
        cleaned += 1
        logger.warning("Job de upload marcado como zumbi/falha: %s", job_id)
    return cleaned


def _delete_matching_upload_jobs(
    company_id: int,
    area: str,
    categoria: str,
    slug: str,
) -> int:
    normalized_area = services._sanitize(area or services.DEFAULT_AREA)
    normalized_categoria = services._sanitize(categoria or services.DEFAULT_CATEGORIA)
    normalized_slug = services._sanitize(slug or services.DEFAULT_SLUG)
    removed = 0
    for path in list(_UPLOAD_JOBS_DIR.glob("*.json")) if _UPLOAD_JOBS_DIR.exists() else []:
        payload = _load_upload_job(path.stem)
        if not isinstance(payload, dict):
            continue
        if payload.get("empresa_id") != company_id:
            continue
        if services._sanitize(str(payload.get("area") or services.DEFAULT_AREA)) != normalized_area:
            continue
        if services._sanitize(str(payload.get("categoria") or services.DEFAULT_CATEGORIA)) != normalized_categoria:
            continue
        if services._sanitize(str(payload.get("slug") or services.DEFAULT_SLUG)) != normalized_slug:
            continue
        try:
            path.unlink(missing_ok=True)
        except Exception:
            logger.exception("Falha ao excluir job persistido %s", path.stem)
            continue
        _UPLOAD_JOBS.pop(path.stem, None)
        _ACTIVE_UPLOAD_JOBS.discard(path.stem)
        removed += 1
    return removed


def _assert_company_taxonomies(
    company_id: int,
    area: Optional[str],
    categoria: Optional[str],
) -> None:
    area_normalized = services._sanitize(area or "")
    categoria_normalized = services._sanitize(categoria or "")
    fallback_area = services.DEFAULT_AREA
    fallback_categoria = services.DEFAULT_CATEGORIA
    if area_normalized and area_normalized not in {fallback_area, ""} and not db.taxonomy_exists(company_id, "area", area_normalized):
        raise HTTPException(status_code=400, detail="Área não cadastrada para esta empresa.")
    if categoria_normalized and categoria_normalized not in {fallback_categoria, ""}:
        if not db.taxonomy_exists(company_id, "categoria", categoria_normalized, area=area_normalized):
            raise HTTPException(status_code=400, detail="Categoria não cadastrada para esta área.")


@router.get("/empresas/{company_id}/documentos", tags=["documentos"])
def list_documents(
    company_id: int,
    area: Optional[str] = None,
    categoria: Optional[str] = None,
    tag: Optional[str] = None,
    busca: Optional[str] = None,
    limit: int = Query(default=10, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    sort: str = Query(default="created_desc"),
    include_content: bool = Query(default=False),
    user: TokenData = Depends(require_company_access),
):
    _is_scoped_access_allowed(company_id, user)
    payload = services.read_published_documents(
        company_id=company_id,
        area=area,
        categoria=categoria,
        tag=tag,
        busca=busca,
        limit=limit,
        offset=offset,
        include_content=include_content,
        sort_by=sort,
        return_total=True,
    )
    if isinstance(payload, dict):
        return {
            "empresa_id": company_id,
            "total": payload.get("total", 0),
            "limit": limit,
            "offset": offset,
            "documentos": payload.get("items", []),
        }
    return {
        "empresa_id": company_id,
        "total": len(payload),
        "limit": limit,
        "offset": offset,
        "documentos": payload,
    }


@router.get("/empresas/{company_id}/documentos/publicados", tags=["documentos"])
def list_published_documents(
    company_id: int,
    area: Optional[str] = None,
    categoria: Optional[str] = None,
    tag: Optional[str] = None,
    busca: Optional[str] = None,
    limit: int = Query(default=10, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    sort: str = Query(default="created_desc"),
    include_content: bool = Query(default=False),
    user: TokenData = Depends(require_company_access),
):
    _is_scoped_access_allowed(company_id, user)
    payload = services.read_published_documents(
        company_id=company_id,
        area=area,
        categoria=categoria,
        tag=tag,
        busca=busca,
        limit=limit,
        offset=offset,
        include_content=include_content,
        sort_by=sort,
        return_total=True,
    )
    if isinstance(payload, dict):
        return {
            "empresa_id": company_id,
            "total": payload.get("total", 0),
            "limit": limit,
            "offset": offset,
            "documentos": payload.get("items", []),
        }
    return {
        "empresa_id": company_id,
        "total": len(payload),
        "limit": limit,
        "offset": offset,
        "documentos": payload,
    }


@router.post("/empresas/{company_id}/documentos", tags=["documentos"])
def create_document(
    company_id: int,
    payload: DocumentCreatePayload,
    user: TokenData = Depends(require_role("admin", "editor")),
):
    _is_scoped_access_allowed(company_id, user)
    try:
        _assert_company_taxonomies(company_id, payload.area, payload.categoria)
        doc = services.create_or_update_text_document(
            company_id=company_id,
            area=payload.area,
            categoria=payload.categoria,
            slug=payload.slug,
            title=payload.title,
            content=payload.content,
            author_email=_author_email(user),
            tags=payload.tags,
            ai_prompt=payload.ai_prompt,
            data_validade=payload.data_validade,
            is_published=payload.publicar,
            base_version=payload.base_version,
        )
        document_payload = {**doc}
        if document_payload.get("title") is not None and document_payload.get("titulo") is None:
            document_payload["titulo"] = document_payload.get("title")
        return {"documento": document_payload}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/empresas/{company_id}/documentos/{area}/{categoria}/{slug}", tags=["documentos"])
def delete_document(
    company_id: int,
    area: str,
    categoria: str,
    slug: str,
    user: TokenData = Depends(require_role("admin")),
):
    _is_scoped_access_allowed(company_id, user)
    deleted_jobs = _delete_matching_upload_jobs(company_id, area, categoria, slug)
    deleted_document = None
    try:
        deleted_document = services.delete_document(company_id, area, categoria, slug)
    except FileNotFoundError:
        deleted_document = None
    if not deleted_document and not deleted_jobs:
        raise HTTPException(status_code=404, detail="Documento não encontrado")
    logger.info(
        "Exclusão solicitada: empresa=%s area=%s categoria=%s slug=%s jobs_removidos=%s documento_removido=%s",
        company_id,
        area,
        categoria,
        slug,
        deleted_jobs,
        bool(deleted_document),
    )
    return {
        "message": "Documento excluído com sucesso.",
        "empresa_id": company_id,
        "area": services._sanitize(area),
        "categoria": services._sanitize(categoria),
        "slug": services._sanitize(slug),
        "removed_jobs": deleted_jobs,
        "removed_document": bool(deleted_document),
    }


@router.get("/empresas/{company_id}/areas", tags=["areas"])
def list_company_areas(
    company_id: int,
    user: TokenData = Depends(require_company_access),
):
    _is_scoped_access_allowed(company_id, user)
    try:
        items = db.list_taxonomies(company_id, "area")
        return {"empresa_id": company_id, "items": items}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/empresas/{company_id}/areas", tags=["areas"])
def create_company_area(
    company_id: int,
    payload: TaxonomyPayload,
    user: TokenData = Depends(require_role("admin", "editor")),
):
    _is_scoped_access_allowed(company_id, user)
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Nome da área é obrigatório.")
    try:
        created = db.create_taxonomy(company_id, "area", name)
        return {"area": created}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/empresas/{company_id}/areas", tags=["areas"])
def delete_company_area(
    company_id: int,
    name: str = Query(..., min_length=1),
    user: TokenData = Depends(require_role("admin", "editor")),
):
    _is_scoped_access_allowed(company_id, user)
    try:
        db.delete_taxonomy(company_id, "area", name)
        return {"status": "removida"}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/empresas/{company_id}/categorias", tags=["categorias"])
def list_company_categories(
    company_id: int,
    user: TokenData = Depends(require_company_access),
):
    _is_scoped_access_allowed(company_id, user)
    try:
        items = db.list_taxonomies(company_id, "categoria")
        return {"empresa_id": company_id, "items": items}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/empresas/{company_id}/categorias", tags=["categorias"])
def create_company_category(
    company_id: int,
    payload: CategoryPayload,
    user: TokenData = Depends(require_role("admin", "editor")),
):
    _is_scoped_access_allowed(company_id, user)
    name = payload.name.strip()
    area = payload.area.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Nome da categoria é obrigatório.")
    if not area:
        raise HTTPException(status_code=400, detail="Área é obrigatória para cadastrar categoria.")
    try:
        created = db.create_taxonomy(company_id, "categoria", name, parent_area=area)
        return {"categoria": created}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/empresas/{company_id}/categorias", tags=["categorias"])
def delete_company_category(
    company_id: int,
    name: str = Query(..., min_length=1),
    area: Optional[str] = Query(default=None),
    user: TokenData = Depends(require_role("admin", "editor")),
):
    _is_scoped_access_allowed(company_id, user)
    try:
        if area is not None:
            db.delete_taxonomy(company_id, "categoria", name, area=area)
        else:
            db.delete_taxonomy(company_id, "categoria", name)
        return {"status": "removida"}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/empresas/{company_id}/documentos/upload", tags=["upload"])
async def upload_document(
    company_id: int,
    area: Optional[str] = Form(default=None),
    categoria: Optional[str] = Form(default=None),
    slug: Optional[str] = Form(default=None),
    base_version: Optional[str] = Form(default=None),
    publicar: bool = Form(default=False),
    title: str = Form(None),
    ai_prompt: Optional[str] = Form(default=None),
    data_validade: Optional[str] = Form(default=None),
    tags: str = Form(""),
    file: UploadFile = File(...),
    user: TokenData = Depends(require_role("admin", "editor")),
):
    _is_scoped_access_allowed(company_id, user)
    try:
        _assert_company_taxonomies(company_id, area, categoria)
        tag_list = [item.strip() for item in tags.split(",") if item.strip()] if tags else []
        file_name = file.filename or "documento"
        upload_dir = Path(services.KB_ROOT) / "_tmp_uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        upload_path = upload_dir / f"{uuid4().hex}-{file_name}"
        with upload_path.open("wb") as f:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                f.write(chunk)
        if upload_path.stat().st_size == 0:
            upload_path.unlink(missing_ok=True)
            raise ValueError("Arquivo vazio")
        job_id = uuid4().hex

        _UPLOAD_JOBS[job_id] = {
            "job_id": job_id,
            "status": "processing",
            "empresa_id": company_id,
            "slug": slug,
            "area": area,
            "categoria": categoria,
            "title": title,
            "file_name": file_name,
            "data_validade": data_validade,
            "publicar": publicar,
            "created_at": datetime.utcnow().isoformat() + "Z",
            "updated_at": datetime.utcnow().isoformat() + "Z",
        }
        _persist_upload_job(job_id, _UPLOAD_JOBS[job_id])

        async def run_job() -> None:
            _ACTIVE_UPLOAD_JOBS.add(job_id)
            try:
                logger.info("Iniciando processamento assíncrono do upload %s (%s)", job_id, file_name)
                result = await services.import_file_to_markdown_path(
                    company_id=company_id,
                    area=area,
                    categoria=categoria,
                    slug=slug,
                    base_version=base_version,
                    file_path=upload_path,
                    filename=file_name,
                    author_email=_author_email(user),
                    tags=tag_list,
                    title=title,
                    ai_prompt=ai_prompt,
                    data_validade=data_validade,
                )
                documento_payload = {**result}
                if documento_payload.get("title") is not None and documento_payload.get("titulo") is None:
                    documento_payload["titulo"] = documento_payload.get("title")
                if publicar and documento_payload.get("version"):
                    published_result = services.set_published_version(
                        company_id=company_id,
                        area=documento_payload.get("area") or area or services.DEFAULT_AREA,
                        categoria=documento_payload.get("categoria") or categoria or services.DEFAULT_CATEGORIA,
                        slug=documento_payload.get("slug") or slug or services.DEFAULT_SLUG,
                        version=str(documento_payload["version"]),
                    )
                    documento_payload["published_version"] = published_result.get("version", documento_payload.get("published_version", ""))
                _UPLOAD_JOBS[job_id].update({
                    "status": "done",
                    "document_uuid": documento_payload.get("document_uuid"),
                    "updated_at": datetime.utcnow().isoformat() + "Z",
                    "documento": documento_payload,
                })
                logger.info("Upload concluído com sucesso: %s", job_id)
                _touch_upload_job(job_id, _UPLOAD_JOBS[job_id])
            except Exception as exc:  # pragma: no cover - depende de runtime de conversão
                logger.exception("Falha no processamento assíncrono do upload %s", job_id)
                _UPLOAD_JOBS[job_id].update({
                    "status": "failed",
                    "updated_at": datetime.utcnow().isoformat() + "Z",
                    "error": str(exc),
                })
                logger.info("Upload marcado como failed: %s", job_id)
                _touch_upload_job(job_id, _UPLOAD_JOBS[job_id])
            finally:
                _ACTIVE_UPLOAD_JOBS.discard(job_id)
                upload_path.unlink(missing_ok=True)
                logger.info("Finalizando processamento assíncrono do upload %s", job_id)

        asyncio.create_task(run_job())
        return {"job_id": job_id, "status": "processing"}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/empresas/{company_id}/documentos/upload/{job_id}", tags=["upload"])
def upload_document_status(
    company_id: int,
    job_id: str,
    user: TokenData = Depends(require_role("admin", "editor")),
):
    _is_scoped_access_allowed(company_id, user)
    job = _load_upload_job(job_id)
    if not job or job.get("empresa_id") != company_id:
        raise HTTPException(status_code=410, detail="Processamento não encontrado ou reiniciado. Envie o arquivo novamente.")
    return job


@router.get("/empresas/{company_id}/documentos/processando", tags=["upload"])
def list_processing_uploads(
    company_id: int,
    status: Optional[str] = Query(default=None),
    user: TokenData = Depends(require_role("admin", "editor")),
):
    _is_scoped_access_allowed(company_id, user)
    return {
        "documentos": [
            job
            for job in _load_company_upload_jobs(company_id, status_filter=status)
            if job.get("status") in {"processing", "failed", "done"}
        ],
    }


@router.put("/empresas/{company_id}/documentos/{area}/{categoria}/{slug}/publicar", tags=["documentos"])
def publish_document_version(
    company_id: int,
    area: str,
    categoria: str,
    slug: str,
    payload: PublishPayload,
    user: TokenData = Depends(require_role("admin", "revisor")),
):
    _is_scoped_access_allowed(company_id, user)
    try:
        result = services.set_published_version(company_id, area, categoria, slug, payload.version)
        return {"documento": result, "status": "publicada"}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/empresas/{company_id}/documentos/{area}/{categoria}/{slug}", tags=["documentos"])
def list_document_versions(
    company_id: int,
    area: str,
    categoria: str,
    slug: str,
    include_content: bool = Query(default=False),
    version: Optional[str] = Query(default=None),
    user: TokenData = Depends(require_company_access),
):
    _is_scoped_access_allowed(company_id, user)
    try:
        meta = services.list_versions(company_id, area, categoria, slug)
        if meta.get("title") is not None and meta.get("titulo") is None:
            meta = {**meta, "titulo": meta.get("title")}
        response = {"documento": meta}
        if include_content:
            content_payload = services.read_published_document_content(
                company_id=company_id,
                area=area,
                categoria=categoria,
                slug=slug,
                version=version,
            )
            response["documento"] = {
                **meta,
                "content": content_payload.get("content", ""),
                "conteudo_versao": content_payload.get("versao"),
                "conteudo_publicado": bool(content_payload.get("publicado")),
                # manter compatibilidade temporária durante migração
                "content_version": content_payload.get("versao"),
                "content_published": bool(content_payload.get("publicado")),
            }
        return response
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Documento não encontrado")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/empresas/{company_id}/documentos/{area}/{categoria}/{slug}/conteudo", tags=["documentos"])
def get_published_document_content(
    company_id: int,
    area: str,
    categoria: str,
    slug: str,
    version: Optional[str] = Query(None),
    user: TokenData = Depends(require_company_access),
):
    _is_scoped_access_allowed(company_id, user)
    try:
        return services.read_published_document_content(
            company_id=company_id,
            area=area,
            categoria=categoria,
            slug=slug,
            version=version,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except OSError as exc:
        raise HTTPException(status_code=503, detail=f"Recurso temporariamente indisponível: {str(exc)}")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
