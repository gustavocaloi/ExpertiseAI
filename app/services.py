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


def _doc_dir(company_id: int, area: str, categoria: str, slug: str) -> Path:
    return Path(KB_ROOT) / str(company_id) / _sanitize(area) / _sanitize(categoria) / _sanitize(slug)


def _meta_path(company_id: int, area: str, categoria: str, slug: str) -> Path:
    return _doc_dir(company_id, area, categoria, slug) / "document.meta.json"


def _version_path(company_id: int, area: str, categoria: str, slug: str, version: str) -> Path:
    return _doc_dir(company_id, area, categoria, slug) / f"v{version}.md"


def _read_meta(company_id: int, area: str, categoria: str, slug: str) -> Dict[str, Any]:
    meta_file = _meta_path(company_id, area, categoria, slug)
    if not meta_file.exists():
        raise FileNotFoundError("Documento não encontrado")
    with meta_file.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    changed = False
    document_uuid = str(payload.get("document_uuid") or "").strip()
    if not document_uuid:
        payload["document_uuid"] = str(uuid4())
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


def _write_meta(meta_file: Path, payload: Dict[str, Any]) -> None:
    meta_file.parent.mkdir(parents=True, exist_ok=True)
    with meta_file.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


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
            if exc.errno == errno.EWOULDBLOCK:
                time.sleep(_IO_RETRY_DELAY_SECONDS)
                continue
            raise
    return None


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
        }

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
    }

    for version_file in root.rglob("v*.md"):
        if "_tmp_uploads" in version_file.parts:
            continue

        if not version_file.is_file():
            continue

        match = _VERSION_FILE_RE.match(version_file.name)
        if not match:
            continue

        relative = version_file.relative_to(root)
        if len(relative.parts) < 5:
            continue

        company_id_str, area, categoria, slug = relative.parts[:4]
        if not company_id_str.isdigit():
            continue

        company_id = int(company_id_str)
        doc_dir = version_file.parent
        meta_path = doc_dir / "document.meta.json"

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

            meta = {
                "document_uuid": str(uuid4()),
                "slug": slug,
                "title": _safe_str(first_metadata.get("title")) or _safe_str(first_version.get("title")) or slug,
                "empresa_id": company_id,
                "area": area,
                "categoria": categoria,
                "tags": merged_tags,
                "ai_prompt": first_metadata.get("ai_prompt", ""),
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
            _write_meta(meta_path, meta)
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


def _version_matches(a: Any, b: Any) -> bool:
    try:
        return _version_key(a) == _version_key(b)
    except ValueError:
        return str(a) == str(b)


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
        f"created_at: {metadata['created_at']}",
        f"updated_at: {metadata['updated_at']}",
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
    title: str,
    content: str,
    author_email: str,
    tags: Iterable[str] = (),
    ai_prompt: Optional[str] = None,
    is_published: bool = False,
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
    doc_dir = _doc_dir(company_id, area_n, categoria_n, slug_n)
    meta_path = _meta_path(company_id, area_n, categoria_n, slug_n)

    if not meta_path.exists():
        meta = {
            "document_uuid": str(uuid4()),
            "slug": slug_n,
            "title": title,
            "empresa_id": company_id,
            "area": area_n,
            "categoria": categoria_n,
            "tags": list(tags),
            "ai_prompt": ai_prompt or "",
            "created_at": _now(),
            "updated_at": _now(),
            "published_version": "",
            "versions": [],
        }
    else:
        meta = _read_meta(company_id, area_n, categoria_n, slug_n)
        if title:
            meta["title"] = title
        if ai_prompt is not None:
            meta["ai_prompt"] = ai_prompt
        meta["updated_at"] = _now()
        meta["tags"] = list(tags) if tags else meta.get("tags", [])

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
        "ai_prompt": ai_prompt or "",
    }

    # se for publicada, publica imediatamente e despublica as outras
    if is_published:
        for v in meta["versions"]:
            v["published"] = False
            v["published_at"] = None
        meta["published_version"] = version

    path = _version_path(company_id, area_n, categoria_n, slug_n, version)
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
            "created_at": _now(),
            "updated_at": _now(),
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
    _write_meta(meta_path, meta)

    return {
        "document_uuid": meta.get("document_uuid"),
        "empresa_id": company_id,
        "area": area_n,
        "categoria": categoria_n,
        "slug": slug_n,
        "ai_prompt": meta.get("ai_prompt", ""),
        "version_uuid": version_meta.get("version_uuid"),
        "version": _version_display(version),
        "published_version": meta.get("published_version", ""),
        "path": str(path),
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
    doc_dir = _doc_dir(company_id, area_n, categoria_n, slug_n)
    if not doc_dir.exists():
        raise FileNotFoundError("Documento não encontrado")
    shutil.rmtree(doc_dir)
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
    }


async def import_file_to_markdown(
    company_id: int,
    area: Optional[str],
    categoria: Optional[str],
    slug: Optional[str],
    base_version: Optional[str],
    file: UploadFile,
    author_email: str,
    tags: Iterable[str] = (),
    title: Optional[str] = None,
    ai_prompt: Optional[str] = None,
) -> Dict[str, Any]:
    raw = await file.read()
    return await import_file_to_markdown_bytes(
        company_id=company_id,
        area=area,
        categoria=categoria,
        slug=slug,
        base_version=base_version,
        raw=raw,
        filename=file.filename or "documento",
        author_email=author_email,
        tags=tags,
        title=title,
        ai_prompt=ai_prompt,
    )


async def import_file_to_markdown_path(
    company_id: int,
    area: Optional[str],
    categoria: Optional[str],
    slug: Optional[str],
    base_version: Optional[str],
    file_path: str | Path,
    filename: str,
    author_email: str,
    tags: Iterable[str] = (),
    title: Optional[str] = None,
    ai_prompt: Optional[str] = None,
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
    return create_or_update_text_document(
        company_id=company_id,
        area=area,
        categoria=categoria,
        slug=slug,
        title=doc_title,
        content=converted,
        author_email=author_email,
        tags=tags,
        ai_prompt=ai_prompt,
        base_version=base_version,
        is_published=False,
    )


async def import_file_to_markdown_bytes(
    company_id: int,
    area: Optional[str],
    categoria: Optional[str],
    slug: Optional[str],
    base_version: Optional[str],
    raw: bytes,
    filename: str,
    author_email: str,
    tags: Iterable[str] = (),
    title: Optional[str] = None,
    ai_prompt: Optional[str] = None,
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
        title=doc_title,
        content=converted,
        author_email=author_email,
        tags=tags,
        ai_prompt=ai_prompt,
        base_version=base_version,
        is_published=False,
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
            published_version_uuid = v.get("version_uuid")
        else:
            v["published"] = False
            v["published_at"] = None

    meta["published_version"] = version
    _write_meta(_meta_path(company_id, area_n, categoria_n, slug_n), meta)

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
    return meta


def read_published_documents(
    company_id: int,
    area: Optional[str] = None,
    categoria: Optional[str] = None,
    tag: Optional[str] = None,
    busca: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    include_content: bool = True,
    sort_by: str = "created_desc",
    return_total: bool = False,
) -> Dict[str, Any] | list[Dict[str, Any]]:
    root = Path(KB_ROOT) / str(company_id)
    if not root.exists():
        if return_total:
            return {"total": 0, "items": []}
        return []
    term = (busca or "").strip().lower() if busca else ""
    should_load_content = include_content or bool(term)

    out: list[Dict[str, Any]] = []
    for meta_file in root.rglob("document.meta.json"):
        meta: Optional[Dict[str, Any]] = None
        for attempt in range(3):
            try:
                with meta_file.open("r", encoding="utf-8") as f:
                    meta = json.load(f)
                break
            except (json.JSONDecodeError, OSError) as exc:
                if isinstance(exc, OSError) and exc.errno == errno.EWOULDBLOCK and attempt < 2:
                    time.sleep(0.05)
                    continue
                meta = None
                break

        if meta is None:
            continue

        if area and meta.get("area") != _sanitize(area):
            continue
        if categoria and meta.get("categoria") != _sanitize(categoria):
            continue
        if tag and tag not in meta.get("tags", []):
            continue

        published_version = str(meta.get("published_version", "") or "")
        if not published_version:
            continue

        if term:
            if (
                term not in str(meta.get("title", "")).lower()
                and term not in str(meta.get("slug", "")).lower()
                and term not in " ".join(meta.get("tags", [])).lower()
            ):
                if should_load_content:
                    try:
                        content_payload = read_published_document_content(
                            company_id=company_id,
                            area=meta.get("area", ""),
                            categoria=meta.get("categoria", ""),
                            slug=meta.get("slug", ""),
                            version=published_version,
                        )
                        if term not in str(content_payload.get("content", "")).lower():
                            continue
                    except (FileNotFoundError, ValueError, OSError):
                        continue
                else:
                    continue

        published_content = ""
        if should_load_content:
            try:
                published_content = read_published_document_content(
                    company_id=company_id,
                    area=meta.get("area", ""),
                    categoria=meta.get("categoria", ""),
                    slug=meta.get("slug", ""),
                    version=published_version,
                ).get("content", "")
            except (FileNotFoundError, ValueError, OSError):
                published_content = ""

        item = {
            "document_uuid": meta.get("document_uuid"),
            "satellite_document_id": meta.get("document_uuid"),
            "empresa_id": company_id,
            "slug": meta.get("slug"),
            "titulo": meta.get("title"),
            "area": meta.get("area"),
            "categoria": meta.get("categoria"),
            "tags": meta.get("tags", []),
            "ai_prompt": meta.get("ai_prompt", ""),
            "published_version_uuid": next(
                (
                    entry.get("version_uuid")
                    for entry in meta.get("versions", [])
                    if _version_matches(entry.get("version"), published_version)
                ),
                None,
            ),
            "published_version": published_version,
            "satellite_version_id": next(
                (
                    entry.get("version_uuid")
                    for entry in meta.get("versions", [])
                    if _version_matches(entry.get("version"), published_version)
                ),
                None,
            ),
            "created_at": meta.get("created_at"),
            "updated_at": meta.get("updated_at"),
        }
        if include_content:
            item["content"] = published_content

        out.append(item)

    sort_option = (sort_by or "").strip()
    if sort_option == "created_asc":
        out = sorted(out, key=lambda item: item["updated_at"] or "")
    elif sort_option == "area_asc":
        out = sorted(out, key=lambda item: (item["area"] or "", item["categoria"] or "", item["updated_at"] or ""), reverse=False)
    elif sort_option == "categoria_asc":
        out = sorted(out, key=lambda item: (item["categoria"] or "", item["area"] or "", item["updated_at"] or ""), reverse=False)
    else:
        out = sorted(out, key=lambda item: item["updated_at"] or "", reverse=True)

    total = len(out)
    documents = out[offset : offset + limit]
    if return_total:
        return {"total": total, "items": documents}
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
    meta = _read_meta(company_id, area_n, categoria_n, slug_n)

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

    version_path = _version_path(company_id, area_n, categoria_n, slug_n, selected_version)
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
        "versao": selected_version,
        "publicado": bool(selected_entry.get("published")),
        "updated_at": meta.get("updated_at"),
        "content": body,
    }
