from __future__ import annotations

import errno
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Union

from fastapi import UploadFile

from . import db
from .config import KB_ROOT, DOCLING_ENABLED


_VERSION_FILE_RE = re.compile(r"^v(.+)\\.md$")
_IO_MAX_RETRIES = 3
_IO_RETRY_DELAY_SECONDS = 0.05


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
        return json.load(f)


def _write_meta(meta_file: Path, payload: Dict[str, Any]) -> None:
    meta_file.parent.mkdir(parents=True, exist_ok=True)
    with meta_file.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


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
        output[key.strip()] = value.strip()
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
                "slug": slug,
                "title": _safe_str(first_metadata.get("title")) or _safe_str(first_version.get("title")) or slug,
                "empresa_id": company_id,
                "area": area,
                "categoria": categoria,
                "tags": merged_tags,
                "created_at": created_at,
                "updated_at": updated_at,
                "published_version": published_version,
                "versions": [
                    {
                        "version": item["version"],
                        "file": item["file"],
                        "author": item["author"],
                        "created_at": item["created_at"],
                        "published": item["published"],
                        "published_at": item.get("published_at"),
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
            db.create_taxonomy(company_id, "categoria", categoria)
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
    is_published: bool = False,
    base_version: Optional[str] = None,
) -> Dict[str, Any]:
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
            "slug": slug_n,
            "title": title,
            "empresa_id": company_id,
            "area": area_n,
            "categoria": categoria_n,
            "tags": list(tags),
            "created_at": _now(),
            "updated_at": _now(),
            "published_version": "",
            "versions": [],
        }
    else:
        meta = _read_meta(company_id, area_n, categoria_n, slug_n)
        if title:
            meta["title"] = title
        meta["updated_at"] = _now()
        meta["tags"] = list(tags) if tags else meta.get("tags", [])

    if base_version is not None:
        version = _extract_next_patch_version(meta, base_version)
    else:
        version = _extract_next_version(meta)
    version_meta = {
        "version": _version_display(version),
        "file": f"v{version}.md",
        "author": author_email,
        "created_at": _now(),
        "published": bool(is_published),
        "published_at": _now() if is_published else None,
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
        "empresa_id": company_id,
        "area": area_n,
        "categoria": categoria_n,
        "slug": slug_n,
        "version": _version_display(version),
        "published_version": meta.get("published_version", ""),
        "path": str(path),
    }


async def import_file_to_markdown(
    company_id: int,
    area: Optional[str],
    categoria: Optional[str],
    slug: Optional[str],
    file: UploadFile,
    author_email: str,
    tags: Iterable[str] = (),
    title: Optional[str] = None,
) -> Dict[str, Any]:
    ext = Path(file.filename or "").suffix.lower()
    raw = await file.read()
    if not raw:
        raise ValueError("Arquivo vazio")

    converted = ""
    if ext in {".txt", ".md"}:
        converted = raw.decode("utf-8", errors="ignore")
    elif ext in {".pdf", ".docx"} and DOCLING_ENABLED:
        converted = await _convert_to_markdown_with_docling(raw, file.filename or "documento")
    else:
        raise ValueError("Formato inválido. Use PDF, DOCX, MD ou TXT.")

    doc_title = title or Path(file.filename or "documento").stem
    return create_or_update_text_document(
        company_id=company_id,
        area=area,
        categoria=categoria,
        slug=slug,
        title=doc_title,
        content=converted,
        author_email=author_email,
        tags=tags,
        is_published=False,
    )


async def _convert_to_markdown_with_docling(raw: bytes, filename: str) -> str:
    temp_dir = Path(KB_ROOT) / "_tmp_uploads"
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_file = temp_dir / filename
    with temp_file.open("wb") as f:
        f.write(raw)

    try:
        from docling.document_converter import DocumentConverter
    except Exception as e:  # pragma: no cover
        raise ValueError(
            "Integração com docling não disponível. Instale a dependência docling."
        ) from e

    converter = DocumentConverter()
    result = converter.convert(str(temp_file))

    document = getattr(result, "document", None)
    if document is None:
        raise ValueError("Falha ao converter arquivo com docling.")

    if hasattr(document, "export_to_markdown"):
        return document.export_to_markdown()
    if hasattr(document, "to_markdown"):
        return document.to_markdown()
    raise ValueError("Conversor docling sem método conhecido de exportação.")


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

    for v in meta["versions"]:
        if _version_matches(v["version"], version):
            v["published"] = True
            v["published_at"] = _now()
        else:
            v["published"] = False
            v["published_at"] = None

    meta["published_version"] = version
    _write_meta(_meta_path(company_id, area_n, categoria_n, slug_n), meta)

    return {"empresa_id": company_id, "slug": slug_n, "version": version}


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
) -> list[Dict[str, Any]]:
    root = Path(KB_ROOT) / str(company_id)
    if not root.exists():
        return []

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
        if busca:
            term = busca.lower()
            if term not in str(meta.get("title", "")).lower() and term not in str(meta.get("slug", "")).lower():
                continue

        published_version = str(meta.get("published_version", "") or "")
        if not published_version:
            continue

        published_content = ""
        if include_content:
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
            "empresa_id": company_id,
            "slug": meta.get("slug"),
            "titulo": meta.get("title"),
            "area": meta.get("area"),
            "categoria": meta.get("categoria"),
            "tags": meta.get("tags", []),
            "published_version": published_version,
            "created_at": meta.get("created_at"),
            "updated_at": meta.get("updated_at"),
        }
        if include_content:
            item["content"] = published_content

        out.append(item)

    out = sorted(out, key=lambda item: item["updated_at"] or "", reverse=True)
    return out[offset : offset + limit]


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
        "empresa_id": company_id,
        "area": area_n,
        "categoria": categoria_n,
        "slug": slug_n,
        "titulo": meta.get("title", slug_n),
        "tags": meta.get("tags", []),
        "versao": selected_version,
        "publicado": bool(selected_entry.get("published")),
        "updated_at": meta.get("updated_at"),
        "content": body,
    }
