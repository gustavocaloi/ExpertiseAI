from __future__ import annotations

import errno
import json
import asyncio
import os
import logging
import re
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Union
from uuid import uuid4

from fastapi import UploadFile

from . import db
from .config import (
    KB_ROOT,
    DOCLING_BUNDLED_CACHE_DIR,
    DOCLING_CACHE_DIR,
    DOCLING_ENABLED,
    DOCLING_MAX_FILE_SIZE_MB,
    DOCLING_MAX_PAGES,
    DOCLING_OCR_ENABLED,
    DOCLING_PREFETCH_MODELS,
    DOCLING_PDF_PAGE_BATCH_SIZE,
    DOCLING_TABLE_STRUCTURE_ENABLED,
    DOCLING_THREADS,
    DOCLING_TIMEOUT_SECONDS,
)


_VERSION_FILE_RE = re.compile(r"^v(.+)\\.md$")
_IO_MAX_RETRIES = 3
_IO_RETRY_DELAY_SECONDS = 0.05
_DOCLING_TIMEOUT_SECONDS = DOCLING_TIMEOUT_SECONDS
_DOCLING_MAX_PAGES = DOCLING_MAX_PAGES
_DOCLING_MAX_FILE_SIZE_BYTES = max(1, DOCLING_MAX_FILE_SIZE_MB) * 1024 * 1024
_DOCLING_PDF_PAGE_BATCH_SIZE = max(1, DOCLING_PDF_PAGE_BATCH_SIZE)
_DOCLING_THREADS = max(1, DOCLING_THREADS)
_DOCLING_WORKER_PATH = Path(__file__).resolve().parent / "docling_worker.py"
_DOCUMENT_TITLE_MAX_CHARS = 256
logger = logging.getLogger(__name__)
_HF_CACHE_DIR = DOCLING_CACHE_DIR / "huggingface"
_BUNDLED_HF_CACHE_DIR = DOCLING_BUNDLED_CACHE_DIR / "huggingface"


def _prepare_docling_cache() -> None:
    DOCLING_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _HF_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    os.environ["HF_HOME"] = str(_HF_CACHE_DIR)
    os.environ["HUGGINGFACE_HUB_CACHE"] = str(_HF_CACHE_DIR)
    os.environ.pop("TRANSFORMERS_CACHE", None)
    os.environ["DOCLING_CACHE_DIR"] = str(DOCLING_CACHE_DIR)
    os.environ["XDG_CACHE_HOME"] = str(DOCLING_CACHE_DIR)
    os.environ["OMP_NUM_THREADS"] = str(_DOCLING_THREADS)
    os.environ["MKL_NUM_THREADS"] = str(_DOCLING_THREADS)
    logger.info("Docling cache configurado: hf=%s cache=%s", _HF_CACHE_DIR, DOCLING_CACHE_DIR)


def _runtime_docling_cache_has_files() -> bool:
    return _HF_CACHE_DIR.exists() and any(_HF_CACHE_DIR.iterdir())


def _bundled_docling_cache_has_files() -> bool:
    return _BUNDLED_HF_CACHE_DIR.exists() and any(_BUNDLED_HF_CACHE_DIR.iterdir())


def _restore_docling_cache_from_bundle() -> bool:
    if _runtime_docling_cache_has_files() or not _bundled_docling_cache_has_files():
        return False
    logger.info(
        "Restaurando cache empacotado do docling de %s para %s",
        DOCLING_BUNDLED_CACHE_DIR,
        DOCLING_CACHE_DIR,
    )
    shutil.copytree(DOCLING_BUNDLED_CACHE_DIR, DOCLING_CACHE_DIR, dirs_exist_ok=True)
    return True


def _sanitize(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9_.-]+", "-", value)
    value = value.strip("-")
    return value or "sem-nome"


def _now() -> str:
    return datetime.utcnow().isoformat() + "Z"


DEFAULT_AREA = "sem-area"
DEFAULT_CATEGORIA = "sem-categoria"
DEFAULT_SLUG = "documento"
DOCUMENT_STORAGE_VERSION = 2
DOCUMENTS_DIRNAME = "_documents"
DOCUMENTS_INDEX_FILENAME = "_documents.index.json"
_MIGRATED_COMPANIES: set[int] = set()


def _company_root(company_id: int) -> Path:
    return Path(KB_ROOT) / str(company_id)


def _documents_root(company_id: int) -> Path:
    return _company_root(company_id) / DOCUMENTS_DIRNAME


def _documents_index_path(company_id: int) -> Path:
    return _company_root(company_id) / DOCUMENTS_INDEX_FILENAME


def _legacy_doc_dir(company_id: int, area: str, categoria: str, slug: str) -> Path:
    return Path(KB_ROOT) / str(company_id) / _sanitize(area) / _sanitize(categoria) / _sanitize(slug)


def _doc_dir(company_id: int, area: str, categoria: str, slug: str, document_uuid: Optional[str] = None) -> Path:
    if document_uuid:
        return _documents_root(company_id) / str(document_uuid).strip()
    return _legacy_doc_dir(company_id, area, categoria, slug)


def _meta_path(company_id: int, area: str, categoria: str, slug: str, document_uuid: Optional[str] = None) -> Path:
    return _doc_dir(company_id, area, categoria, slug, document_uuid=document_uuid) / "document.meta.json"


def _version_path(
    company_id: int,
    area: str,
    categoria: str,
    slug: str,
    version: str,
    document_uuid: Optional[str] = None,
) -> Path:
    return _doc_dir(company_id, area, categoria, slug, document_uuid=document_uuid) / f"v{version}.md"


def _is_new_storage_meta_path(company_id: int, meta_file: Path) -> bool:
    try:
        relative = meta_file.relative_to(_company_root(company_id))
    except ValueError:
        return False
    parts = relative.parts
    return len(parts) >= 3 and parts[0] == DOCUMENTS_DIRNAME and parts[-1] == "document.meta.json"


def _load_meta_file(meta_file: Path) -> Dict[str, Any]:
    raw = _read_text_with_retry(meta_file, encoding="utf-8")
    if raw is None:
        raise OSError(errno.EWOULDBLOCK, "Resource temporarily unavailable")
    payload = json.loads(raw)
    changed = False
    document_uuid = str(payload.get("document_uuid") or "").strip()
    if not document_uuid:
        payload["document_uuid"] = str(uuid4())
        changed = True
    if int(payload.get("storage_version") or 0) != DOCUMENT_STORAGE_VERSION:
        payload["storage_version"] = DOCUMENT_STORAGE_VERSION
        changed = True
    versions = payload.get("versions", [])
    if isinstance(versions, list):
        for entry in versions:
            if not isinstance(entry, dict):
                continue
            version_uuid = str(entry.get("version_uuid") or "").strip()
            if not version_uuid:
                entry["version_uuid"] = str(uuid4())
                changed = True
    if changed:
        _write_meta(meta_file, payload)
    return payload


def _read_meta_by_path(company_id: int, meta_file: Path, migrate: bool = True) -> Dict[str, Any]:
    payload = _load_meta_file(meta_file)
    if migrate:
        meta_file = _migrate_document_to_company_storage(company_id, meta_file, payload)
        payload = _load_meta_file(meta_file)
    return payload


def _iter_document_meta_files(company_id: int) -> Iterable[Path]:
    started_at = time.perf_counter()
    root = _company_root(company_id)
    if not root.exists():
        logger.info("Empresa %s: raiz da base inexistente em %s.", company_id, root)
        return []
    seen: set[Path] = set()
    items: list[Path] = []
    for meta_file in root.rglob("document.meta.json"):
        if not meta_file.is_file():
            continue
        if meta_file in seen:
            continue
        seen.add(meta_file)
        items.append(meta_file)
    logger.info(
        "Empresa %s: encontrados %s arquivos document.meta.json em %.2fs.",
        company_id,
        len(items),
        time.perf_counter() - started_at,
    )
    return items


def _find_meta_file_by_document_uuid(company_id: int, document_uuid: str) -> Optional[Path]:
    document_uuid_value = str(document_uuid or "").strip()
    if not document_uuid_value:
        return None
    candidate = _meta_path(company_id, "", "", "", document_uuid=document_uuid_value)
    if candidate.exists():
        return candidate
    for item in _read_documents_index(company_id):
        if str(item.get("document_uuid") or "").strip() == document_uuid_value:
            indexed_candidate = _meta_path(company_id, "", "", "", document_uuid=document_uuid_value)
            if indexed_candidate.exists():
                return indexed_candidate
    for meta_file in _iter_document_meta_files(company_id):
        try:
            payload = _load_meta_file(meta_file)
        except Exception:
            continue
        if str(payload.get("document_uuid") or "").strip() == document_uuid_value:
            return meta_file
    return None


def _find_meta_file_by_identity(
    company_id: int,
    area: Optional[str],
    categoria: Optional[str],
    slug: Optional[str],
) -> Optional[Path]:
    area_n = _sanitize(area or DEFAULT_AREA)
    categoria_n = _sanitize(categoria or DEFAULT_CATEGORIA)
    slug_n = _sanitize(slug or DEFAULT_SLUG)
    legacy_meta = _meta_path(company_id, area_n, categoria_n, slug_n)
    if legacy_meta.exists():
        return legacy_meta
    for item in _read_documents_index(company_id):
        if _sanitize(item.get("area") or DEFAULT_AREA) != area_n:
            continue
        if _sanitize(item.get("categoria") or DEFAULT_CATEGORIA) != categoria_n:
            continue
        if _sanitize(item.get("slug") or DEFAULT_SLUG) != slug_n:
            continue
        document_uuid = str(item.get("document_uuid") or "").strip()
        if document_uuid:
            candidate = _meta_path(company_id, "", "", "", document_uuid=document_uuid)
            if candidate.exists():
                return candidate
    for meta_file in _iter_document_meta_files(company_id):
        try:
            payload = _load_meta_file(meta_file)
        except Exception:
            continue
        if _sanitize(payload.get("area") or DEFAULT_AREA) != area_n:
            continue
        if _sanitize(payload.get("categoria") or DEFAULT_CATEGORIA) != categoria_n:
            continue
        if _sanitize(payload.get("slug") or DEFAULT_SLUG) != slug_n:
            continue
        return meta_file
    return None


def _find_document_meta_file(
    company_id: int,
    area: Optional[str] = None,
    categoria: Optional[str] = None,
    slug: Optional[str] = None,
    document_uuid: Optional[str] = None,
) -> Optional[Path]:
    if document_uuid:
        by_uuid = _find_meta_file_by_document_uuid(company_id, document_uuid)
        if by_uuid is not None:
            return by_uuid
    return _find_meta_file_by_identity(company_id, area, categoria, slug)


def _assert_unique_document_identity(
    company_id: int,
    area: str,
    categoria: str,
    slug: str,
    *,
    ignore_document_uuid: Optional[str] = None,
) -> None:
    normalized_area = _sanitize(area or DEFAULT_AREA)
    normalized_categoria = _sanitize(categoria or DEFAULT_CATEGORIA)
    normalized_slug = _sanitize(slug or DEFAULT_SLUG)
    matched = _find_meta_file_by_identity(company_id, normalized_area, normalized_categoria, normalized_slug)
    if matched is None:
        return
    payload = _read_meta_by_path(company_id, matched)
    if ignore_document_uuid and str(payload.get("document_uuid")) == str(ignore_document_uuid):
        return
    raise ValueError("Já existe um documento com a mesma empresa, área, categoria e slug.")


def _migrate_document_to_company_storage(company_id: int, meta_file: Path, payload: Optional[Dict[str, Any]] = None) -> Path:
    if _is_new_storage_meta_path(company_id, meta_file):
        return meta_file

    data = payload or _load_meta_file(meta_file)
    document_uuid = str(data.get("document_uuid") or "").strip()
    if not document_uuid:
        document_uuid = str(uuid4())
        data["document_uuid"] = document_uuid

    source_dir = meta_file.parent
    target_dir = _doc_dir(company_id, "", "", "", document_uuid=document_uuid)
    target_meta = target_dir / "document.meta.json"
    if source_dir == target_dir:
        _write_meta(target_meta, data)
        return target_meta

    target_dir.parent.mkdir(parents=True, exist_ok=True)
    if not target_dir.exists():
        shutil.move(str(source_dir), str(target_dir))
        _write_meta(target_meta, data)
        return target_meta

    for child in source_dir.iterdir():
        destination = target_dir / child.name
        if destination.exists():
            if child.is_dir():
                shutil.copytree(child, destination, dirs_exist_ok=True)
                shutil.rmtree(child, ignore_errors=True)
            else:
                if child.name == "document.meta.json":
                    child.unlink(missing_ok=True)
                    continue
                source_bytes = child.read_bytes()
                destination_bytes = destination.read_bytes()
                if source_bytes != destination_bytes:
                    raise ValueError(
                        f"Conflito ao migrar documento {document_uuid}: arquivo {child.name} já existe com conteúdo diferente."
                    )
                child.unlink(missing_ok=True)
        else:
            shutil.move(str(child), str(destination))

    shutil.rmtree(source_dir, ignore_errors=True)
    _write_meta(target_meta, data)
    return target_meta


def _cleanup_empty_legacy_directories(company_id: int) -> int:
    company_root = _company_root(company_id)
    if not company_root.exists():
        return 0

    removed = 0
    candidate_dirs = sorted(
        [
            path
            for path in company_root.rglob("*")
            if path.is_dir() and DOCUMENTS_DIRNAME not in path.parts
        ],
        key=lambda path: len(path.parts),
        reverse=True,
    )
    for directory in candidate_dirs:
        if directory == company_root:
            continue
        try:
            next(directory.iterdir())
            continue
        except StopIteration:
            directory.rmdir()
            removed += 1
        except FileNotFoundError:
            continue
        except OSError:
            continue
    return removed


def _read_meta(company_id: int, area: str, categoria: str, slug: str) -> Dict[str, Any]:
    meta_file = _find_document_meta_file(company_id, area=area, categoria=categoria, slug=slug)
    if meta_file is None or not meta_file.exists():
        raise FileNotFoundError("Documento não encontrado")
    return _read_meta_by_path(company_id, meta_file)


def _write_meta(meta_file: Path, payload: Dict[str, Any]) -> None:
    meta_file.parent.mkdir(parents=True, exist_ok=True)
    with meta_file.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    try:
        company_id = int(payload.get("empresa_id"))
    except (TypeError, ValueError):
        company_id = None
    if company_id is not None:
        _upsert_documents_index_entry(company_id, payload)


def _meta_to_index_entry(meta: Dict[str, Any]) -> Dict[str, Any]:
    published_version = str(meta.get("published_version", "") or "")
    pending_version = _resolve_pending_approval_version(meta)
    versions = [
        entry
        for entry in meta.get("versions", [])
        if isinstance(entry, dict) and entry.get("version") is not None
    ]
    selected_version = published_version
    if not selected_version and versions:
        versions = sorted(versions, key=lambda item: _version_key(item["version"]))
        selected_version = str(versions[-1]["version"])
    version_uuid = next(
        (
            entry.get("version_uuid")
            for entry in versions
            if _version_matches(entry.get("version"), selected_version)
        ),
        None,
    )
    return {
        "document_uuid": meta.get("document_uuid"),
        "empresa_id": meta.get("empresa_id"),
        "slug": meta.get("slug"),
        "titulo": meta.get("title"),
        "area": meta.get("area"),
        "categoria": meta.get("categoria"),
        "tags": meta.get("tags", []),
        "ai_prompt": meta.get("ai_prompt", ""),
        "data_validade": meta.get("data_validade", ""),
        "attachments": _public_attachments(meta),
        "version": selected_version,
        "published_version_uuid": version_uuid,
        "published_version": published_version,
        "pending_approval": bool(pending_version),
        "pending_approval_version": pending_version,
        "satellite_document_id": meta.get("document_uuid"),
        "satellite_version_id": version_uuid,
        "created_at": meta.get("created_at"),
        "updated_at": meta.get("updated_at"),
        "searchable_text": _searchable_text_from_meta(meta),
    }


def _read_documents_index(company_id: int) -> list[Dict[str, Any]]:
    path = _documents_index_path(company_id)
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception:
        return []
    if not isinstance(payload, dict):
        return []
    items = payload.get("items")
    return items if isinstance(items, list) else []


def _resolve_pending_approval_version(meta: Dict[str, Any]) -> str:
    versions = [
        entry
        for entry in meta.get("versions", [])
        if isinstance(entry, dict) and entry.get("version") is not None
    ]
    if not versions:
        return ""

    explicit_pending = [
        str(entry.get("version"))
        for entry in versions
        if bool(entry.get("pending_approval"))
    ]
    if explicit_pending:
        return max(explicit_pending, key=_version_key)

    versions_sorted = sorted(versions, key=lambda item: _version_key(item["version"]))
    published_version = str(meta.get("published_version") or "").strip()
    if not published_version:
        latest = versions_sorted[-1]
        return "" if bool(latest.get("published")) else str(latest.get("version"))

    unpublished_after_published = [
        str(entry.get("version"))
        for entry in versions_sorted
        if not bool(entry.get("published")) and _version_key(str(entry.get("version"))) > _version_key(published_version)
    ]
    if unpublished_after_published:
        return max(unpublished_after_published, key=_version_key)
    return ""


def _with_pending_approval_state(meta: Dict[str, Any]) -> Dict[str, Any]:
    pending_version = _resolve_pending_approval_version(meta)
    normalized = dict(meta)
    versions: list[Dict[str, Any]] = []
    for entry in meta.get("versions", []):
        if not isinstance(entry, dict):
            continue
        item = dict(entry)
        item["pending_approval"] = bool(item.get("pending_approval")) or (
            bool(pending_version) and _version_matches(item.get("version"), pending_version)
        )
        versions.append(item)
    normalized["versions"] = versions
    normalized["pending_approval"] = bool(pending_version)
    normalized["pending_approval_version"] = pending_version
    return normalized


def _write_documents_index(company_id: int, items: list[Dict[str, Any]]) -> None:
    path = _documents_index_path(company_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "company_id": company_id,
        "updated_at": _now(),
        "items": items,
    }
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def _rebuild_documents_index(company_id: int) -> list[Dict[str, Any]]:
    started_at = time.perf_counter()
    items: list[Dict[str, Any]] = []
    errors = 0
    meta_files = list(_iter_document_meta_files(company_id))
    total = len(meta_files)
    logger.info("Empresa %s: rebuild do indice iniciado. metas=%s", company_id, total)
    for index, meta_file in enumerate(meta_files, start=1):
        try:
            meta = _read_meta_by_path(company_id, meta_file)
        except Exception:
            errors += 1
            logger.exception(
                "Empresa %s: falha ao indexar metadata %s/%s em %s",
                company_id,
                index,
                total,
                meta_file,
            )
            continue
        items.append(_meta_to_index_entry(meta))
        if index % 100 == 0:
            logger.info(
                "Empresa %s: rebuild do indice em progresso. processados=%s/%s indexados=%s erros=%s",
                company_id,
                index,
                total,
                len(items),
                errors,
            )
    _write_documents_index(company_id, items)
    logger.info(
        "Empresa %s: rebuild do indice concluido em %.2fs. indexados=%s erros=%s",
        company_id,
        time.perf_counter() - started_at,
        len(items),
        errors,
    )
    return items


def _ensure_documents_index(company_id: int) -> list[Dict[str, Any]]:
    items = _read_documents_index(company_id)
    if items and all(isinstance(item, dict) and "searchable_text" in item for item in items):
        return items
    return _rebuild_documents_index(company_id)


def _upsert_documents_index_entry(company_id: int, meta: Dict[str, Any]) -> None:
    document_uuid = str(meta.get("document_uuid") or "").strip()
    if not document_uuid:
        return
    items = _read_documents_index(company_id)
    if not items:
        _rebuild_documents_index(company_id)
        items = _read_documents_index(company_id)
    entry = _meta_to_index_entry(meta)
    replaced = False
    for index, current in enumerate(items):
        if str(current.get("document_uuid") or "").strip() == document_uuid:
            items[index] = entry
            replaced = True
            break
    if not replaced:
        items.append(entry)
    _write_documents_index(company_id, items)


def _remove_documents_index_entry(company_id: int, document_uuid: Optional[str]) -> None:
    document_uuid_value = str(document_uuid or "").strip()
    if not document_uuid_value:
        return
    items = _read_documents_index(company_id)
    if not items:
        return
    filtered = [
        item
        for item in items
        if str(item.get("document_uuid") or "").strip() != document_uuid_value
    ]
    if len(filtered) != len(items):
        _write_documents_index(company_id, filtered)


def _docling_worker_env() -> dict[str, str]:
    env = os.environ.copy()
    env["HF_HOME"] = str(_HF_CACHE_DIR)
    env["HUGGINGFACE_HUB_CACHE"] = str(_HF_CACHE_DIR)
    env.pop("TRANSFORMERS_CACHE", None)
    env["DOCLING_CACHE_DIR"] = str(DOCLING_CACHE_DIR)
    env["XDG_CACHE_HOME"] = str(DOCLING_CACHE_DIR)
    env["OMP_NUM_THREADS"] = str(_DOCLING_THREADS)
    env["MKL_NUM_THREADS"] = str(_DOCLING_THREADS)
    env["EXPAI_DOCLING_MAX_PAGES"] = str(_DOCLING_MAX_PAGES)
    env["EXPAI_DOCLING_MAX_FILE_SIZE_BYTES"] = str(_DOCLING_MAX_FILE_SIZE_BYTES)
    env["EXPAI_DOCLING_PDF_PAGE_BATCH_SIZE"] = str(_DOCLING_PDF_PAGE_BATCH_SIZE)
    env["EXPAI_DOCLING_TIMEOUT_SECONDS"] = str(_DOCLING_TIMEOUT_SECONDS)
    env["EXPAI_DOCLING_OCR_ENABLED"] = "true" if DOCLING_OCR_ENABLED else "false"
    env["EXPAI_DOCLING_TABLE_STRUCTURE_ENABLED"] = "true" if DOCLING_TABLE_STRUCTURE_ENABLED else "false"
    return env


def _clear_docling_runtime_cache() -> None:
    if DOCLING_CACHE_DIR.exists():
        shutil.rmtree(DOCLING_CACHE_DIR, ignore_errors=True)
    DOCLING_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _HF_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _should_retry_docling_artifacts(stderr_text: str, stdout_text: str) -> bool:
    message = f"{stderr_text}\n{stdout_text}".lower()
    return (
        "missing safe tensors file" in message
        or "downloading detection model" in message
        or "downloading recognition model" in message
        or "appropriate snapshot folder" in message
    )


def _is_missing_hf_snapshot_error(stderr_text: str, stdout_text: str) -> bool:
    message = f"{stderr_text}\n{stdout_text}".lower()
    return "appropriate snapshot folder" in message


def _missing_hf_snapshot_message() -> str:
    return (
        "Falha ao carregar os modelos locais do Docling/Hugging Face. "
        "Este container foi iniciado sem acesso aos snapshots necessários para PDF. "
        "Rebuild a imagem com internet para empacotar os modelos ou execute o primeiro start "
        "com conectividade para popular o cache em "
        f"{DOCLING_CACHE_DIR}."
    )


def ensure_docling_models_ready(force: bool = False) -> None:
    if not DOCLING_ENABLED:
        return

    if force:
        _clear_docling_runtime_cache()
    _prepare_docling_cache()
    _restore_docling_cache_from_bundle()


async def ensure_docling_models_ready_async() -> None:
    if not DOCLING_ENABLED or not DOCLING_PREFETCH_MODELS:
        return
    await asyncio.to_thread(ensure_docling_models_ready)
    if _runtime_docling_cache_has_files():
        logger.info("Cache do docling pronto em %s.", DOCLING_CACHE_DIR)
        return
    logger.warning(
        "Nenhum modelo local do docling foi encontrado em %s e não há bundle em %s. "
        "O primeiro processamento de PDF exigirá acesso à internet.",
        DOCLING_CACHE_DIR,
        DOCLING_BUNDLED_CACHE_DIR,
    )


def _normalize_taxonomy(value: Optional[str], fallback: str) -> str:
    text = (value or "").strip()
    return _sanitize(text) if text else _sanitize(fallback)


def _normalize_slug(value: Optional[str], fallback: str) -> str:
    text = (value or "").strip()
    return _sanitize(text) if text else _sanitize(fallback)


def _parse_version_string(value: Any) -> tuple[int, int]:
    text = str(value).strip()
    if not text:
        raise ValueError("versão vazia")
    if not re.match(r"^\d+(\.\d+)?$", text):
        raise ValueError(f"formato de versão inválido: {value}")
    if "." in text:
        major_text, minor_text = text.split(".", 1)
        return int(major_text), int(minor_text)
    return int(text), 0


def _version_key(value: Any) -> tuple[int, int]:
    try:
        return _parse_version_string(value)
    except ValueError:
        return (0, 0)


def _version_display(version: Union[str, int]) -> str:
    return str(int(version)) if isinstance(version, int) else str(version).strip()


def _extract_next_version(meta: Dict[str, Any]) -> str:
    versions = [_version_key(v.get("version")) for v in meta.get("versions", []) if isinstance(v, dict) and v.get("version") is not None]
    if not versions:
        return "1"
    max_major = max(v[0] for v in versions)
    return str(max_major + 1)


def _extract_next_patch_version(meta: Dict[str, Any], base_version: Union[str, int]) -> str:
    base_major, _ = _parse_version_string(base_version)
    same_major = [
        _parse_version_string(v["version"])[1]
        for v in meta.get("versions", [])
        if isinstance(v, dict)
        and "version" in v
        and _parse_version_string(v["version"])[0] == base_major
    ]
    max_minor = max(same_major) if same_major else 0
    return f"{base_major}.{max_minor + 1}"


def _safe_parse_frontmatter(markdown: str) -> Dict[str, str]:
    lines = markdown.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}

    output: Dict[str, str] = {}
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            break
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        value_raw = value.strip()
        if ((value_raw.startswith("\"") and value_raw.endswith("\"")) or
                (value_raw.startswith("'") and value_raw.endswith("'"))):
            value_raw = value_raw[1:-1]
        output[key.strip()] = value_raw
    return output


def _safe_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _safe_tags(value: Any) -> list[str]:
    if isinstance(value, list):
        raw_values = [str(v) for v in value]
    else:
        text = str(value).strip()
        if not text:
            return []
        if text.startswith("[") and text.endswith("]"):
            text = text[1:-1]
        raw_values = text.split(",")
    tags: list[str] = []
    for item in raw_values:
        clean = str(item).strip().strip("\"\'")
        if clean and clean not in tags:
            tags.append(clean)
    return tags


def _normalize_tag_filter(value: Optional[str]) -> str:
    return str(value or "").strip().lower()


def _validate_document_title(title: str) -> None:
    if len((title or "").strip()) > _DOCUMENT_TITLE_MAX_CHARS:
        raise ValueError(f"O título deve ter no máximo {_DOCUMENT_TITLE_MAX_CHARS} caracteres.")


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _read_text_with_retry(
    path: Path,
    encoding: str = "utf-8",
    errors: str = "strict",
) -> Optional[str]:
    for _ in range(_IO_MAX_RETRIES):
        try:
            return path.read_text(encoding=encoding, errors=errors)
        except OSError as exc:
            if exc.errno in {errno.EDEADLK, errno.EWOULDBLOCK}:
                time.sleep(_IO_RETRY_DELAY_SECONDS)
                continue
            raise
    return None


def _strip_frontmatter(markdown: str) -> str:
    lines = markdown.splitlines()
    if not lines or lines[0].strip() != "---":
        return markdown
    closing = None
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            closing = index
            break
    if closing is None:
        return markdown
    return "\n".join(lines[closing + 1 :]).lstrip("\n")


def _searchable_text_from_meta(meta: Dict[str, Any]) -> str:
    parts = [
        str(meta.get("title") or ""),
        str(meta.get("slug") or ""),
        str(meta.get("area") or ""),
        str(meta.get("categoria") or ""),
        " ".join(_safe_tags(meta.get("tags", []))),
    ]
    selected_version = str(meta.get("published_version") or "").strip()
    if not selected_version:
        versions = [
            entry
            for entry in meta.get("versions", [])
            if isinstance(entry, dict) and entry.get("version") is not None
        ]
        if versions:
            versions = sorted(versions, key=lambda item: _version_key(item["version"]))
            selected_version = str(versions[-1]["version"])
    if selected_version:
        version_path = _version_path(
            int(meta.get("empresa_id")),
            str(meta.get("area") or ""),
            str(meta.get("categoria") or ""),
            str(meta.get("slug") or ""),
            selected_version,
            document_uuid=str(meta.get("document_uuid") or ""),
        )
        content = _read_text_with_retry(version_path, encoding="utf-8", errors="ignore") if version_path.exists() else ""
        if content:
            parts.append(_strip_frontmatter(content))
    return " ".join(part for part in parts if part).lower()


def rebuild_documents_from_markdown_files(force: bool = False) -> Dict[str, int]:
    root = Path(KB_ROOT)
    if not root.exists():
        return {
            "scanned": 0,
            "created": 0,
            "updated": 0,
            "skipped": 0,
            "errors": 0,
            "companies_created": 0,
            "companies_seen": 0,
            "taxonomies_created": 0,
            "migrated": 0,
        }

    migrated = migrate_documents_storage_layout()

    companies_seen: set[int] = set()
    summary = {
        "scanned": 0,
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "errors": 0,
        "companies_created": 0,
        "companies_seen": 0,
        "taxonomies_created": 0,
        "migrated": migrated,
    }

    for version_file in root.rglob("v*.md"):
        if "_tmp_uploads" in version_file.parts:
            continue
        meta_seed: Dict[str, Any] = {}
        if DOCUMENTS_DIRNAME in version_file.parts:
            if len(version_file.relative_to(root).parts) < 4:
                continue
            company_id_str = version_file.relative_to(root).parts[0]
            if not company_id_str.isdigit():
                continue
            company_id = int(company_id_str)
            doc_dir = version_file.parent
            meta_path = doc_dir / "document.meta.json"
            if not meta_path.exists():
                continue
            meta_seed = _load_meta_file(meta_path)
            area = _sanitize(meta_seed.get("area") or DEFAULT_AREA)
            categoria = _sanitize(meta_seed.get("categoria") or DEFAULT_CATEGORIA)
            slug = _sanitize(meta_seed.get("slug") or DEFAULT_SLUG)
        else:
            relative = version_file.relative_to(root)
            if len(relative.parts) < 5:
                continue

            company_id_str, area, categoria, slug = relative.parts[:4]
            if not company_id_str.isdigit():
                continue

            company_id = int(company_id_str)
            doc_dir = version_file.parent
            meta_path = doc_dir / "document.meta.json"

        if not version_file.is_file():
            continue

        match = _VERSION_FILE_RE.match(version_file.name)
        if not match:
            continue

        if meta_path.exists() and not force:
            summary["skipped"] += 1
            continue

        try:
            versions: list[Dict[str, Any]] = []
            for file in sorted(doc_dir.glob("v*.md")):
                file_match = _VERSION_FILE_RE.match(file.name)
                if not file_match:
                    continue

                version_value = file_match.group(1)
                content = _read_text_with_retry(file, encoding="utf-8", errors="ignore")
                if content is None:
                    raise OSError(errno.EWOULDBLOCK, "Resource temporarily unavailable")
                metadata = _safe_parse_frontmatter(content)
                version = _version_display(metadata.get("version") or version_value)
                created_at = _safe_str(metadata.get("created_at")) or _now()
                updated_at = _safe_str(metadata.get("updated_at")) or created_at
                published = _safe_bool(metadata.get("published"))
                published_at = _safe_str(metadata.get("published_at")) if published else ""

                versions.append(
                    {
                        "version": version,
                        "file": file.name,
                        "author": _safe_str(metadata.get("author")) or "anônimo",
                        "created_at": created_at,
                        "updated_at": updated_at,
                        "published": published,
                        "published_at": published_at,
                        "tags": metadata.get("tags", ""),
                        "ai_prompt": metadata.get("ai_prompt", ""),
                    }
                )

            if not versions:
                summary["skipped"] += 1
                continue

            versions = sorted(versions, key=lambda item: _version_key(item["version"]))
            first_version = versions[0]
            latest_version = versions[-1]

            published_entries = [item for item in versions if item.get("published")]
            if published_entries:
                selected = max(published_entries, key=lambda item: _version_key(item["version"]))
                published_version = str(selected["version"])
            else:
                published_version = str(latest_version["version"])

            created_times = [item["created_at"] for item in versions if item.get("created_at")]
            updated_times = [item["updated_at"] for item in versions if item.get("updated_at")]
            created_at = min(created_times) if created_times else _now()
            updated_at = max(updated_times) if updated_times else _now()

            merged_tags: list[str] = []
            for item in versions:
                for tag in _safe_tags(item.get("tags", "")):
                    if tag not in merged_tags:
                        merged_tags.append(tag)

            for version in versions:
                if _version_matches(version["version"], published_version):
                    version["published"] = True
                    version["published_at"] = version.get("published_at") or _now()
                    break

            first_metadata = _safe_parse_frontmatter(
                first_version["file"] and (_read_text_with_retry(
                    doc_dir / first_version["file"],
                    encoding="utf-8",
                    errors="ignore",
                ) or "")
            )
            data_validade = _safe_str(first_metadata.get("data_validade"))

            meta = {
                "document_uuid": str(meta_seed.get("document_uuid")) if meta_seed.get("document_uuid") else str(uuid4()),
                "storage_version": DOCUMENT_STORAGE_VERSION,
                "slug": slug,
                "title": _safe_str(first_metadata.get("title")) or _safe_str(first_version.get("title")) or slug,
                "empresa_id": company_id,
                "area": area,
                "categoria": categoria,
                "tags": merged_tags,
                "ai_prompt": first_metadata.get("ai_prompt", ""),
                "data_validade": data_validade,
                "created_at": created_at,
                "updated_at": updated_at,
                "published_version": published_version,
                "versions": [
                    {
                        "version": item["version"],
                        "version_uuid": str(uuid4()),
                        "file": item["file"],
                        "author": item["author"],
                        "created_at": item["created_at"],
                        "published": item["published"],
                        "published_at": item.get("published_at"),
                        "ai_prompt": item.get("ai_prompt", ""),
                    }
                    for item in versions
                ],
            }

            was_missing = not meta_path.exists()
            target_meta_path = _migrate_document_to_company_storage(company_id, meta_path, meta)
            _write_meta(target_meta_path, meta)
            summary["scanned"] += 1
            if was_missing:
                summary["created"] += 1
            else:
                summary["updated"] += 1

            if company_id not in companies_seen:
                if db.get_company(company_id) is None:
                    db.ensure_company(company_id, company_name=f"Empresa {company_id}", company_slug=f"empresa-{company_id}")
                    summary["companies_created"] += 1
                companies_seen.add(company_id)
                summary["companies_seen"] += 1

            db.create_taxonomy(company_id, "area", area)
            summary["taxonomies_created"] += 1
            db.create_taxonomy(company_id, "categoria", categoria, parent_area=area)
            summary["taxonomies_created"] += 1
        except Exception:
            summary["errors"] += 1

    return summary


def migrate_documents_storage_layout(company_id: Optional[int] = None) -> int:
    started_at = time.perf_counter()
    root = Path(KB_ROOT)
    if not root.exists():
        logger.info("Migração de documentos ignorada: KB_ROOT inexistente em %s.", root)
        return 0

    logger.info("Migração de documentos iniciada. root=%s company_id=%s", root, company_id or "todas")
    migrated = 0
    company_ids: list[int] = []
    if company_id is not None:
        company_ids = [company_id]
    else:
        for child in root.iterdir():
            if child.is_dir() and child.name.isdigit():
                company_ids.append(int(child.name))

    logger.info("Migração de documentos: empresas encontradas=%s", company_ids)
    for current_company_id in company_ids:
        if company_id is not None and current_company_id in _MIGRATED_COMPANIES:
            logger.info("Empresa %s: migração ignorada porque já foi executada neste processo.", current_company_id)
            continue
        company_t0 = time.perf_counter()
        meta_files = list(_iter_document_meta_files(current_company_id))
        logger.info("Empresa %s: migração iniciada. metas=%s", current_company_id, len(meta_files))
        company_migrated = 0
        company_errors = 0
        for index, meta_file in enumerate(meta_files, start=1):
            if _is_new_storage_meta_path(current_company_id, meta_file):
                _read_meta_by_path(current_company_id, meta_file, migrate=False)
                if index % 100 == 0:
                    logger.info(
                        "Empresa %s: validação de metas novas em progresso. processados=%s/%s",
                        current_company_id,
                        index,
                        len(meta_files),
                    )
                continue
            try:
                payload = _load_meta_file(meta_file)
                _migrate_document_to_company_storage(current_company_id, meta_file, payload)
                migrated += 1
                company_migrated += 1
            except Exception:
                company_errors += 1
                logger.exception(
                    "Falha ao migrar documento legado para o novo layout. empresa=%s meta=%s",
                    current_company_id,
                    meta_file,
                )
        _cleanup_empty_legacy_directories(current_company_id)
        _rebuild_documents_index(current_company_id)
        _MIGRATED_COMPANIES.add(current_company_id)
        logger.info(
            "Empresa %s: migração concluida em %.2fs. migrados=%s erros=%s",
            current_company_id,
            time.perf_counter() - company_t0,
            company_migrated,
            company_errors,
        )
    logger.info("Migração de documentos concluida em %.2fs. total_migrados=%s", time.perf_counter() - started_at, migrated)
    return migrated


def _version_matches(a: Any, b: Any) -> bool:
    try:
        return _version_key(a) == _version_key(b)
    except ValueError:
        return str(a) == str(b)


def _sanitize_filename(name: str) -> str:
    candidate = Path(name or "").name.strip()
    if not candidate:
        return "anexo"
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", candidate).strip("-")
    return safe or "anexo"


def _attachment_dir(
    company_id: int,
    area: str,
    categoria: str,
    slug: str,
    document_uuid: Optional[str] = None,
) -> Path:
    return _doc_dir(company_id, area, categoria, slug, document_uuid=document_uuid) / "attachments"


def _public_attachments(meta: Dict[str, Any]) -> list[Dict[str, Any]]:
    attachments = meta.get("attachments") or []
    out: list[Dict[str, Any]] = []
    for item in attachments:
        if not isinstance(item, dict):
            continue
        out.append({
            "id": item.get("id"),
            "file_name": item.get("file_name"),
            "content_type": item.get("content_type"),
            "size_bytes": item.get("size_bytes"),
            "uploaded_at": item.get("uploaded_at"),
        })
    return out


def _frontmatter(markdown: str, metadata: Dict[str, Any]) -> str:
    fm_lines = [
        "---",
        f"title: {metadata['title']}",
        f"slug: {metadata['slug']}",
        f"empresa_id: {metadata['empresa_id']}",
        f"area: {metadata['area']}",
        f"categoria: {metadata['categoria']}",
        f"version: {metadata['version']}",
        f"author: {metadata['author']}",
        f"published: {str(metadata['published']).lower()}",
        f"published_at: {metadata['published_at']}",
        f"approved_by: {metadata.get('approved_by') or ''}",
        f"pending_approval: {str(metadata.get('pending_approval', False)).lower()}",
        f"pending_approval_at: {metadata.get('pending_approval_at') or ''}",
        f"created_at: {metadata['created_at']}",
        f"updated_at: {metadata['updated_at']}",
        f"data_validade: {metadata.get('data_validade') or ''}",
        f"tags: [{', '.join(metadata.get('tags', []))}]",
        f"ai_prompt: {json.dumps(metadata.get('ai_prompt') or '')}",
        "---",
        "",
    ]
    return "\n".join(fm_lines) + markdown.strip() + "\n"


def create_or_update_text_document(
    company_id: int,
    area: Optional[str],
    categoria: Optional[str],
    slug: Optional[str],
    document_uuid: Optional[str],
    title: str,
    content: str,
    author_email: str,
    tags: Iterable[str] = (),
    ai_prompt: Optional[str] = None,
    data_validade: Optional[str] = None,
    is_published: bool = False,
    pending_approval: bool = False,
    base_version: Optional[str] = None,
) -> Dict[str, Any]:
    _validate_document_title(title)
    area_n = _normalize_taxonomy(area, DEFAULT_AREA)
    categoria_n = _normalize_taxonomy(categoria, DEFAULT_CATEGORIA)
    if (slug is None or not str(slug).strip()) and title:
        slug_value = title
    else:
        slug_value = slug
    slug_n = _normalize_slug(slug_value, DEFAULT_SLUG)
    existing_meta_path = _find_document_meta_file(
        company_id,
        area=area_n,
        categoria=categoria_n,
        slug=slug_n,
        document_uuid=document_uuid,
    )

    data_validade_value = (data_validade or "").strip()
    if existing_meta_path is None:
        _assert_unique_document_identity(company_id, area_n, categoria_n, slug_n)
        document_uuid_value = str(document_uuid or uuid4())
        meta = {
            "document_uuid": document_uuid_value,
            "storage_version": DOCUMENT_STORAGE_VERSION,
            "slug": slug_n,
            "title": title,
            "empresa_id": company_id,
            "area": area_n,
            "categoria": categoria_n,
            "tags": list(tags),
            "ai_prompt": ai_prompt or "",
            "data_validade": data_validade_value,
            "created_at": _now(),
            "updated_at": _now(),
            "published_version": "",
            "versions": [],
            "attachments": [],
        }
    else:
        meta = _read_meta_by_path(company_id, existing_meta_path)
        document_uuid_value = str(meta.get("document_uuid"))
        _assert_unique_document_identity(
            company_id,
            area_n,
            categoria_n,
            slug_n,
            ignore_document_uuid=document_uuid_value,
        )
        meta["area"] = area_n
        meta["categoria"] = categoria_n
        meta["slug"] = slug_n
        if title:
            meta["title"] = title
        if ai_prompt is not None:
            meta["ai_prompt"] = ai_prompt
        if data_validade is not None:
            meta["data_validade"] = data_validade_value
        meta["updated_at"] = _now()
        meta["tags"] = list(tags) if tags else meta.get("tags", [])
        if meta.get("attachments") is None:
            meta["attachments"] = []

    if base_version is not None:
        base_version_value = str(base_version).strip()
        if base_version_value:
            version = _extract_next_patch_version(meta, base_version_value)
        else:
            version = _extract_next_version(meta)
    else:
        version = _extract_next_version(meta)
    version_meta = {
        "version": _version_display(version),
        "version_uuid": str(uuid4()),
        "file": f"v{version}.md",
        "author": author_email,
        "created_at": _now(),
        "published": bool(is_published),
        "published_at": _now() if is_published else None,
        "approved_by": author_email if is_published else None,
        "pending_approval": bool(pending_approval and not is_published),
        "pending_approval_at": _now() if pending_approval and not is_published else None,
        "ai_prompt": ai_prompt or "",
    }

    current_data_validade = meta.get("data_validade", "")
    # se for publicada, publica imediatamente e despublica as outras
    if is_published:
        for v in meta["versions"]:
            v["published"] = False
            v["published_at"] = None
            v["approved_by"] = None
            v["pending_approval"] = False
            v["pending_approval_at"] = None
        meta["published_version"] = version
    elif pending_approval:
        for v in meta["versions"]:
            v["pending_approval"] = False
            v["pending_approval_at"] = None

    path = _version_path(company_id, area_n, categoria_n, slug_n, version, document_uuid=document_uuid_value)
    doc_payload = _frontmatter(
        content,
        {
            "title": title,
            "slug": slug_n,
            "empresa_id": company_id,
            "area": area_n,
            "categoria": categoria_n,
            "version": _version_display(version),
            "author": author_email,
            "published": is_published,
            "published_at": _now() if is_published else "",
            "approved_by": author_email if is_published else "",
            "pending_approval": bool(pending_approval and not is_published),
            "pending_approval_at": _now() if pending_approval and not is_published else "",
            "created_at": _now(),
            "updated_at": _now(),
            "data_validade": current_data_validade,
            "tags": list(tags),
            "ai_prompt": ai_prompt or "",
        },
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        f.write(doc_payload)

    meta["versions"] = meta.get("versions", [])
    meta["versions"].append(version_meta)
    if is_published:
        meta["published_version"] = version
    _write_meta(_meta_path(company_id, area_n, categoria_n, slug_n, document_uuid=document_uuid_value), meta)

    return {
        "document_uuid": meta.get("document_uuid"),
        "empresa_id": company_id,
        "area": area_n,
        "categoria": categoria_n,
        "slug": slug_n,
        "ai_prompt": meta.get("ai_prompt", ""),
        "data_validade": meta.get("data_validade", ""),
        "version_uuid": version_meta.get("version_uuid"),
        "version": _version_display(version),
        "published_version": meta.get("published_version", ""),
        "path": str(path),
        "title": meta.get("title"),
    }


def attach_document_file(
    company_id: int,
    area: str,
    categoria: str,
    slug: str,
    source_path: Path,
    original_name: str,
    content_type: Optional[str] = None,
) -> Dict[str, Any]:
    if not source_path.exists():
        raise FileNotFoundError("Arquivo de origem não encontrado.")
    meta = _read_meta(company_id, _sanitize(area), _sanitize(categoria), _sanitize(slug))
    safe_name = _sanitize_filename(original_name)
    stored_name = f"{uuid4().hex}-{safe_name}"
    dest_dir = _attachment_dir(
        company_id,
        area,
        categoria,
        slug,
        document_uuid=str(meta.get("document_uuid")),
    )
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / stored_name
    shutil.copy2(source_path, dest_path)
    size_bytes = dest_path.stat().st_size if dest_path.exists() else 0

    attachments = meta.get("attachments") or []
    entry = {
        "id": uuid4().hex,
        "file_name": original_name,
        "stored_name": stored_name,
        "content_type": content_type or "",
        "size_bytes": size_bytes,
        "uploaded_at": _now(),
    }
    attachments.append(entry)
    meta["attachments"] = attachments
    _write_meta(
        _meta_path(
            company_id,
            _sanitize(area),
            _sanitize(categoria),
            _sanitize(slug),
            document_uuid=str(meta.get("document_uuid")),
        ),
        meta,
    )
    return entry


def get_document_attachment(
    company_id: int,
    area: str,
    categoria: str,
    slug: str,
    attachment_id: Optional[str] = None,
) -> Dict[str, Any]:
    meta = _read_meta(company_id, _sanitize(area), _sanitize(categoria), _sanitize(slug))
    attachments = meta.get("attachments") or []
    if not attachments:
        raise FileNotFoundError("Documento sem anexo")

    selected = None
    if attachment_id:
        for item in attachments:
            if isinstance(item, dict) and str(item.get("id")) == str(attachment_id):
                selected = item
                break
    if selected is None:
        selected = attachments[-1] if isinstance(attachments[-1], dict) else None
    if not selected:
        raise FileNotFoundError("Anexo inválido")

    stored_name = str(selected.get("stored_name") or "").strip()
    if not stored_name:
        raise FileNotFoundError("Anexo inválido")
    path = _attachment_dir(
        company_id,
        _sanitize(area),
        _sanitize(categoria),
        _sanitize(slug),
        document_uuid=str(meta.get("document_uuid")),
    ) / stored_name
    if not path.exists():
        raise FileNotFoundError("Arquivo do anexo não encontrado")
    return {
        "path": path,
        "file_name": selected.get("file_name") or stored_name,
        "content_type": selected.get("content_type") or "",
        "id": selected.get("id"),
    }


def delete_document(
    company_id: int,
    area: str,
    categoria: str,
    slug: str,
) -> dict[str, Any]:
    area_n = _sanitize(area)
    categoria_n = _sanitize(categoria)
    slug_n = _sanitize(slug)
    meta = _read_meta(company_id, area_n, categoria_n, slug_n)
    doc_dir = _doc_dir(company_id, area_n, categoria_n, slug_n, document_uuid=str(meta.get("document_uuid")))
    if not doc_dir.exists():
        raise FileNotFoundError("Documento não encontrado")
    shutil.rmtree(doc_dir)
    _remove_documents_index_entry(company_id, meta.get("document_uuid"))
    logger.info(
        "Documento removido: empresa=%s area=%s categoria=%s slug=%s",
        company_id,
        area_n,
        categoria_n,
        slug_n,
    )
    return {
        "empresa_id": company_id,
        "area": area_n,
        "categoria": categoria_n,
        "slug": slug_n,
        "document_uuid": meta.get("document_uuid"),
    }


async def import_file_to_markdown(
    company_id: int,
    area: Optional[str],
    categoria: Optional[str],
    slug: Optional[str],
    document_uuid: Optional[str],
    base_version: Optional[str],
    file: UploadFile,
    author_email: str,
    tags: Iterable[str] = (),
    title: Optional[str] = None,
    ai_prompt: Optional[str] = None,
    data_validade: Optional[str] = None,
    pending_approval: bool = False,
) -> Dict[str, Any]:
    raw = await file.read()
    return await import_file_to_markdown_bytes(
        company_id=company_id,
        area=area,
        categoria=categoria,
        slug=slug,
        document_uuid=document_uuid,
        base_version=base_version,
        raw=raw,
        filename=file.filename or "documento",
        author_email=author_email,
        tags=tags,
        title=title,
        ai_prompt=ai_prompt,
        data_validade=data_validade,
        pending_approval=pending_approval,
    )


async def import_file_to_markdown_path(
    company_id: int,
    area: Optional[str],
    categoria: Optional[str],
    slug: Optional[str],
    document_uuid: Optional[str],
    base_version: Optional[str],
    file_path: str | Path,
    filename: str,
    author_email: str,
    tags: Iterable[str] = (),
    title: Optional[str] = None,
    ai_prompt: Optional[str] = None,
    data_validade: Optional[str] = None,
    content_type: Optional[str] = None,
    pending_approval: bool = False,
) -> Dict[str, Any]:
    normalized_path = Path(file_path)
    if not normalized_path.exists():
        raise ValueError("Arquivo de upload não encontrado.")

    ext = Path(filename or "").suffix.lower()
    if ext in {".txt", ".md"}:
        converted = normalized_path.read_text(encoding="utf-8", errors="ignore")
    elif ext in {".pdf", ".docx"} and DOCLING_ENABLED:
        converted = await _convert_to_markdown_with_docling_file(str(normalized_path), filename or "documento")
    else:
        raise ValueError("Formato inválido. Use PDF, DOCX, MD ou TXT.")

    doc_title = title or Path(filename or "documento").stem
    doc_payload = create_or_update_text_document(
        company_id=company_id,
        area=area,
        categoria=categoria,
        slug=slug,
        document_uuid=document_uuid,
        title=doc_title,
        content=converted,
        author_email=author_email,
        tags=tags,
        ai_prompt=ai_prompt,
        data_validade=data_validade,
        base_version=base_version,
        is_published=False,
        pending_approval=pending_approval,
    )
    if ext in {".pdf", ".docx"}:
        try:
            attach_document_file(
                company_id=company_id,
                area=doc_payload.get("area") or (area or DEFAULT_AREA),
                categoria=doc_payload.get("categoria") or (categoria or DEFAULT_CATEGORIA),
                slug=doc_payload.get("slug") or (slug or DEFAULT_SLUG),
                source_path=normalized_path,
                original_name=filename or "documento",
                content_type=content_type,
            )
        except Exception:
            logger.exception("Falha ao salvar anexo do documento %s/%s/%s", company_id, area, slug)
    return doc_payload


async def import_file_to_markdown_bytes(
    company_id: int,
    area: Optional[str],
    categoria: Optional[str],
    slug: Optional[str],
    document_uuid: Optional[str],
    base_version: Optional[str],
    raw: bytes,
    filename: str,
    author_email: str,
    tags: Iterable[str] = (),
    title: Optional[str] = None,
    ai_prompt: Optional[str] = None,
    data_validade: Optional[str] = None,
    pending_approval: bool = False,
) -> Dict[str, Any]:
    ext = Path(filename or "").suffix.lower()
    if not raw:
        raise ValueError("Arquivo vazio")

    converted = ""
    if ext in {".txt", ".md"}:
        converted = raw.decode("utf-8", errors="ignore")
    elif ext in {".pdf", ".docx"} and DOCLING_ENABLED:
        converted = await _convert_to_markdown_with_docling(raw, filename or "documento")
    else:
        raise ValueError("Formato inválido. Use PDF, DOCX, MD ou TXT.")

    doc_title = title or Path(filename or "documento").stem
    return create_or_update_text_document(
        company_id=company_id,
        area=area,
        categoria=categoria,
        slug=slug,
        document_uuid=document_uuid,
        title=doc_title,
        content=converted,
        author_email=author_email,
        tags=tags,
        ai_prompt=ai_prompt,
        data_validade=data_validade,
        base_version=base_version,
        is_published=False,
        pending_approval=pending_approval,
    )


async def _run_docling_worker(file_path: str, filename: str) -> str:
    await asyncio.to_thread(ensure_docling_models_ready)
    return await _run_docling_worker_once(file_path, filename, allow_retry=True)


async def _run_docling_worker_once(file_path: str, filename: str, allow_retry: bool) -> str:
    _prepare_docling_cache()
    temp_dir = Path(KB_ROOT) / "_tmp_uploads"
    temp_dir.mkdir(parents=True, exist_ok=True)
    result_path = temp_dir / f"{uuid4().hex}-docling-result.json"
    file_size_bytes = Path(file_path).stat().st_size if Path(file_path).exists() else -1
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        str(_DOCLING_WORKER_PATH),
        file_path,
        str(result_path),
        filename,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=_docling_worker_env(),
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=_DOCLING_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError as exc:
        process.kill()
        await process.communicate()
        raise TimeoutError(f"Conversão do documento excedeu {_DOCLING_TIMEOUT_SECONDS} segundos.") from exc

    stderr_text = stderr.decode("utf-8", errors="ignore").strip()
    stdout_text = stdout.decode("utf-8", errors="ignore").strip()
    if process.returncode != 0:
        if allow_retry and _should_retry_docling_artifacts(stderr_text, stdout_text):
            logger.warning("Cache do docling inconsistente para %s. Limpando todo o cache e tentando novamente uma vez.", filename)
            await asyncio.to_thread(ensure_docling_models_ready, True)
            return await _run_docling_worker_once(file_path, filename, allow_retry=False)
        logger.error(
            "Falha no subprocesso docling para %s (returncode=%s size=%s). stdout=%r stderr=%r",
            filename,
            process.returncode,
            file_size_bytes,
            stdout_text,
            stderr_text,
        )
        error_message = stderr_text or stdout_text
        if not error_message:
            error_message = (
                f"Falha ao converter arquivo com docling (returncode={process.returncode}, "
                f"size={file_size_bytes}, sem stdout/stderr)."
            )
        if _is_missing_hf_snapshot_error(stderr_text, stdout_text):
            raise ValueError(_missing_hf_snapshot_message())
        raise ValueError(error_message)

    try:
        with result_path.open("r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception as exc:
        logger.exception("Falha ao ler resultado do worker docling para %s", filename)
        raise ValueError("Docling não retornou um resultado válido.") from exc
    finally:
        result_path.unlink(missing_ok=True)

    converted = str(payload.get("markdown") or "")
    if not converted.strip():
        raise ValueError("Docling retornou conteúdo vazio.")
    return converted


async def _convert_to_markdown_with_docling(raw: bytes, filename: str) -> str:
    temp_dir = Path(KB_ROOT) / "_tmp_uploads"
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_path = temp_dir / f"{uuid4().hex}-{filename or 'documento'}"
    try:
        with temp_path.open("wb") as f:
            f.write(raw)
        return await _run_docling_worker(str(temp_path), filename or "documento")
    finally:
        temp_path.unlink(missing_ok=True)


async def _convert_to_markdown_with_docling_file(file_path: str, filename: str) -> str:
    logger.info("Iniciando conversão docling em subprocesso para arquivo: %s", filename)
    return await _run_docling_worker(file_path, filename)


def set_published_version(
    company_id: int,
    area: str,
    categoria: str,
    slug: str,
    version: str,
    approver_email: Optional[str] = None,
) -> Dict[str, Any]:
    area_n = _sanitize(area)
    categoria_n = _sanitize(categoria)
    slug_n = _sanitize(slug)
    meta = _read_meta(company_id, area_n, categoria_n, slug_n)
    if not str(version).strip():
        raise ValueError("Versão inválida para publicação")
    versions = [v["version"] for v in meta.get("versions", [])]
    if not any(_version_matches(item, version) for item in versions):
        raise ValueError("Versão não encontrada para este documento.")

    published_version_uuid = None
    for v in meta["versions"]:
        if _version_matches(v["version"], version):
            v["published"] = True
            v["published_at"] = _now()
            v["approved_by"] = approver_email or v.get("approved_by") or v.get("author")
            v["pending_approval"] = False
            v["pending_approval_at"] = None
            published_version_uuid = v.get("version_uuid")
        else:
            v["published"] = False
            v["published_at"] = None
            v["approved_by"] = None
            v["pending_approval"] = False
            v["pending_approval_at"] = None

    meta["published_version"] = version
    _write_meta(
        _meta_path(company_id, area_n, categoria_n, slug_n, document_uuid=str(meta.get("document_uuid"))),
        meta,
    )

    return {
        "document_uuid": meta.get("document_uuid"),
        "empresa_id": company_id,
        "slug": slug_n,
        "version_uuid": published_version_uuid,
        "version": version,
    }


def list_versions(company_id: int, area: str, categoria: str, slug: str) -> Dict[str, Any]:
    area_n = _sanitize(area)
    categoria_n = _sanitize(categoria)
    slug_n = _sanitize(slug)
    meta = _read_meta(company_id, area_n, categoria_n, slug_n)
    return _with_pending_approval_state(meta)


def read_published_documents(
    company_id: int,
    area: Optional[str] = None,
    categoria: Optional[str] = None,
    tag: Optional[str] = None,
    busca: Optional[str] = None,
    data_validade_de: Optional[str] = None,
    data_validade_ate: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    include_content: bool = True,
    include_unpublished: bool = False,
    sort_by: str = "created_desc",
    return_total: bool = False,
    allowed_areas: Optional[set[str]] = None,
) -> Dict[str, Any] | list[Dict[str, Any]]:
    migrate_documents_storage_layout(company_id)
    root = _company_root(company_id)
    if not root.exists():
        if return_total:
            return {"total": 0, "items": []}
        return []
    term = (busca or "").strip().lower() if busca else ""
    should_load_content = include_content or bool(term)
    area_filter = _sanitize(area) if area else None
    categoria_filter = _sanitize(categoria) if categoria else None
    tag_filter = _normalize_tag_filter(tag)
    data_validade_de_filter = (data_validade_de or "").strip()
    data_validade_ate_filter = (data_validade_ate or "").strip()
    index_items = _ensure_documents_index(company_id)
    out: list[Dict[str, Any]] = []
    for item in index_items:
        published_version = str(item.get("published_version", "") or "")
        selected_version = str(item.get("version", "") or "")
        if not published_version and not include_unpublished:
            continue
        if allowed_areas is not None and str(item.get("area") or "") not in allowed_areas:
            continue
        if area_filter and item.get("area") != area_filter:
            continue
        if categoria_filter and item.get("categoria") != categoria_filter:
            continue
        if tag_filter and tag_filter not in [_normalize_tag_filter(entry) for entry in (item.get("tags") or [])]:
            continue
        item_data_validade = str(item.get("data_validade") or "").strip()
        if item_data_validade and data_validade_de_filter and item_data_validade < data_validade_de_filter:
            continue
        if item_data_validade and data_validade_ate_filter and item_data_validade > data_validade_ate_filter:
            continue

        metadata_matches = True
        if term:
            metadata_matches = term in str(item.get("searchable_text", "")).lower()

        published_content = ""
        if term and not metadata_matches:
            continue
        elif include_content:
            try:
                published_content = read_published_document_content(
                    company_id=company_id,
                    area=item.get("area", ""),
                    categoria=item.get("categoria", ""),
                    slug=item.get("slug", ""),
                    version=selected_version,
                ).get("content", "")
            except (FileNotFoundError, ValueError, OSError):
                published_content = ""

        payload_item = dict(item)
        if include_content:
            payload_item["content"] = published_content
        out.append(payload_item)

    def _validade_key(value: Any, missing_as_max: bool) -> datetime:
        raw = str(value or "").strip()
        if not raw:
            return datetime.max if missing_as_max else datetime.min
        try:
            return datetime.fromisoformat(raw)
        except ValueError:
            return datetime.max if missing_as_max else datetime.min

    sort_option = (sort_by or "").strip()
    if sort_option == "created_asc":
        out = sorted(out, key=lambda item: item["updated_at"] or "")
    elif sort_option == "validade_asc":
        out = sorted(out, key=lambda item: _validade_key(item.get("data_validade"), True))
    elif sort_option == "validade_desc":
        out = sorted(out, key=lambda item: _validade_key(item.get("data_validade"), False), reverse=True)
    elif sort_option == "area_asc":
        out = sorted(out, key=lambda item: (item["area"] or "", item["categoria"] or "", item["updated_at"] or ""), reverse=False)
    elif sort_option == "categoria_asc":
        out = sorted(out, key=lambda item: (item["categoria"] or "", item["area"] or "", item["updated_at"] or ""), reverse=False)
    else:
        out = sorted(out, key=lambda item: item["updated_at"] or "", reverse=True)

    total = len(out)
    pending_total = sum(1 for item in out if bool(item.get("pending_approval")))
    documents = out[offset : offset + limit]
    if return_total:
        return {"total": total, "pending_total": pending_total, "items": documents}
    return documents


def read_published_document_content(
    company_id: int,
    area: str,
    categoria: str,
    slug: str,
    version: Optional[str] = None,
) -> Dict[str, Any]:
    area_n = _sanitize(area)
    categoria_n = _sanitize(categoria)
    slug_n = _sanitize(slug)
    meta = _with_pending_approval_state(_read_meta(company_id, area_n, categoria_n, slug_n))

    if version is not None:
        selected_version = _version_display(version)
        _parse_version_string(selected_version)
    else:
        selected_version = str(meta.get("published_version", "") or "")
        if not selected_version:
            raise FileNotFoundError("Documento ainda não possui versão publicada")

    selected_entry = None
    for entry in meta.get("versions", []):
        if _version_matches(entry.get("version"), selected_version):
            selected_entry = entry
            break
    if selected_entry is None:
        raise FileNotFoundError("Versão não encontrada no histórico do documento")

    version_path = _version_path(
        company_id,
        area_n,
        categoria_n,
        slug_n,
        selected_version,
        document_uuid=str(meta.get("document_uuid")),
    )
    if not version_path.exists():
        raise FileNotFoundError("Arquivo da versão não encontrado")

    full_content = _read_text_with_retry(version_path, encoding="utf-8", errors="strict")
    if full_content is None:
        raise OSError(errno.EWOULDBLOCK, "Resource temporarily unavailable")

    # retorna apenas o corpo do markdown (sem front matter) para visualização
    lines = full_content.splitlines()
    body = full_content
    if lines and lines[0].strip() == "---":
        closing = None
        for index, line in enumerate(lines[1:], start=1):
            if line.strip() == "---":
                closing = index
                break
        if closing is not None:
            body = "\n".join(lines[closing + 1 :]).lstrip("\n")

    return {
        "document_uuid": meta.get("document_uuid"),
        "empresa_id": company_id,
        "area": area_n,
        "categoria": categoria_n,
        "slug": slug_n,
        "version_uuid": selected_entry.get("version_uuid"),
        "titulo": meta.get("title", slug_n),
        "tags": meta.get("tags", []),
        "ai_prompt": selected_entry.get("ai_prompt") or meta.get("ai_prompt", ""),
        "data_validade": meta.get("data_validade", ""),
        "attachments": _public_attachments(meta),
        "versao": selected_version,
        "publicado": bool(selected_entry.get("published")),
        "pending_approval": bool(selected_entry.get("pending_approval")),
        "updated_at": meta.get("updated_at"),
        "content": body,
    }
