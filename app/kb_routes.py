from __future__ import annotations

from typing import Optional, Union

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import UploadFile, File, Form
from pydantic import BaseModel

from . import db, services
from .config import ACCESS_CONTROL_ENABLED
from .security import TokenData, require_company_access, require_role


router = APIRouter()


class DocumentCreatePayload(BaseModel):
    area: Optional[str] = None
    categoria: Optional[str] = None
    slug: Optional[str] = None
    title: str
    content: str
    tags: list[str] = []
    base_version: Union[str, None] = None
    publicar: bool = False


class PublishPayload(BaseModel):
    version: str


class TaxonomyPayload(BaseModel):
    name: str


def _is_scoped_access_allowed(company_id: int, user: TokenData) -> None:
    if not ACCESS_CONTROL_ENABLED:
        return
    if user.company_id != company_id:
        raise HTTPException(status_code=403, detail="Token fora do contexto da empresa")


def _author_email(user: TokenData) -> str:
    return "anônimo" if not ACCESS_CONTROL_ENABLED else (user.email or "anônimo")


def _assert_company_taxonomies(
    company_id: int,
    area: Optional[str],
    categoria: Optional[str],
) -> None:
    area_normalized = (area or "").strip()
    categoria_normalized = (categoria or "").strip()
    fallback_area = services.DEFAULT_AREA
    fallback_categoria = services.DEFAULT_CATEGORIA
    if area_normalized and area_normalized not in {fallback_area, ""} and not db.taxonomy_exists(company_id, "area", area_normalized):
        raise HTTPException(status_code=400, detail="Área não cadastrada para esta empresa.")
    if categoria_normalized and categoria_normalized not in {fallback_categoria, ""} and not db.taxonomy_exists(company_id, "categoria", categoria_normalized):
        raise HTTPException(status_code=400, detail="Categoria não cadastrada para esta empresa.")


@router.get("/empresas/{company_id}/documentos/publicados")
def list_published_documents(
    company_id: int,
    area: Optional[str] = None,
    categoria: Optional[str] = None,
    tag: Optional[str] = None,
    busca: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: TokenData = Depends(require_company_access),
):
    _is_scoped_access_allowed(company_id, user)
    docs = services.read_published_documents(
        company_id=company_id,
        area=area,
        categoria=categoria,
        tag=tag,
        busca=busca,
        limit=limit,
        offset=offset,
        include_content=True,
    )
    return {"empresa_id": company_id, "total": len(docs), "limit": limit, "offset": offset, "documentos": docs}


@router.post("/empresas/{company_id}/documentos")
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
            is_published=payload.publicar,
            base_version=payload.base_version,
        )
        document_payload = {**doc}
        if document_payload.get("title") is not None and document_payload.get("titulo") is None:
            document_payload["titulo"] = document_payload.get("title")
        return {"documento": document_payload}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/empresas/{company_id}/areas")
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


@router.post("/empresas/{company_id}/areas")
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


@router.delete("/empresas/{company_id}/areas")
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


@router.get("/empresas/{company_id}/categorias")
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


@router.post("/empresas/{company_id}/categorias")
def create_company_category(
    company_id: int,
    payload: TaxonomyPayload,
    user: TokenData = Depends(require_role("admin", "editor")),
):
    _is_scoped_access_allowed(company_id, user)
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Nome da categoria é obrigatório.")
    try:
        created = db.create_taxonomy(company_id, "categoria", name)
        return {"categoria": created}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/empresas/{company_id}/categorias")
def delete_company_category(
    company_id: int,
    name: str = Query(..., min_length=1),
    user: TokenData = Depends(require_role("admin", "editor")),
):
    _is_scoped_access_allowed(company_id, user)
    try:
        db.delete_taxonomy(company_id, "categoria", name)
        return {"status": "removida"}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/empresas/{company_id}/documentos/upload")
async def upload_document(
    company_id: int,
    area: Optional[str] = Form(default=None),
    categoria: Optional[str] = Form(default=None),
    slug: Optional[str] = Form(default=None),
    base_version: Optional[str] = Form(default=None),
    title: str = Form(None),
    tags: str = Form(""),
    file: UploadFile = File(...),
    user: TokenData = Depends(require_role("admin", "editor")),
):
    _is_scoped_access_allowed(company_id, user)
    try:
        _assert_company_taxonomies(company_id, area, categoria)
        tag_list = [item.strip() for item in tags.split(",") if item.strip()] if tags else []
        result = await services.import_file_to_markdown(
            company_id=company_id,
            area=area,
            categoria=categoria,
            slug=slug,
            base_version=base_version,
            file=file,
            author_email=_author_email(user),
            tags=tag_list,
            title=title,
        )
        documento_payload = {**result}
        if documento_payload.get("title") is not None and documento_payload.get("titulo") is None:
            documento_payload["titulo"] = documento_payload.get("title")
        return {"documento": documento_payload}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.put("/empresas/{company_id}/documentos/{area}/{categoria}/{slug}/publicar")
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


@router.get("/empresas/{company_id}/documentos/{area}/{categoria}/{slug}")
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


@router.get("/empresas/{company_id}/documentos/{area}/{categoria}/{slug}/conteudo")
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
