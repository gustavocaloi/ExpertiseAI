from __future__ import annotations

from pathlib import Path
from typing import Optional

import pytest

from app import config, db, services


@pytest.fixture()
def isolated_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    data_dir = tmp_path / "data"
    kb_root = data_dir / "kb_store"
    db_path = data_dir / "system.sqlite3"
    data_dir.mkdir(parents=True, exist_ok=True)
    kb_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(config, "DATA_DIR", data_dir)
    monkeypatch.setattr(config, "KB_ROOT", kb_root)
    monkeypatch.setattr(config, "DB_PATH", db_path)
    monkeypatch.setattr(db, "DB_PATH", db_path)
    monkeypatch.setattr(services, "KB_ROOT", kb_root)

    db.init_db()
    yield {"data_dir": data_dir, "kb_root": kb_root, "db_path": db_path}


def _create_doc(
    company_id: int,
    *,
    title: str,
    content: str,
    area: str = "geral",
    categoria: str = "ops",
    slug: Optional[str] = None,
    published: bool = True,
    tags: list[str] | None = None,
) -> dict:
    return services.create_or_update_text_document(
        company_id=company_id,
        area=area,
        categoria=categoria,
        slug=slug,
        document_uuid=None,
        title=title,
        content=content,
        author_email="editor@example.com",
        tags=tags or [],
        is_published=published,
        pending_approval=not published,
    )


def test_listing_paginates_without_loading_all_content(isolated_store):
    company_id = 1
    for index in range(25):
        _create_doc(
            company_id,
            title=f"Documento {index:03d}",
            content=f"Corpo longo do documento {index} " + ("x" * 2000),
            slug=f"documento-{index:03d}",
        )

    page = services.read_published_documents(
        company_id=company_id,
        limit=10,
        offset=10,
        include_content=False,
        return_total=True,
    )
    assert page["total"] == 25
    assert len(page["items"]) == 10
    assert all("content" not in item for item in page["items"])

    index_path = services._documents_index_path(company_id)
    index_text = index_path.read_text(encoding="utf-8")
    assert "schema_version" in index_text
    assert "xxxxx" not in index_text


def test_search_finds_document_by_body_via_fts(isolated_store):
    company_id = 1
    _create_doc(
        company_id,
        title="Procedimento A",
        content="Texto comum sem termo especial",
        slug="proc-a",
    )
    target = _create_doc(
        company_id,
        title="Procedimento B",
        content="Manual de onboarding com palavra-unica-xyz123",
        slug="proc-b",
    )

    result = services.read_published_documents(
        company_id=company_id,
        busca="palavra-unica-xyz123",
        include_content=False,
        return_total=True,
    )
    assert result["total"] == 1
    assert result["items"][0]["document_uuid"] == target["document_uuid"]
    assert db.count_company_document_search(company_id) >= 2


def test_allowed_areas_filter_hides_other_areas(isolated_store):
    company_id = 1
    _create_doc(
        company_id,
        title="Doc RH",
        content="Politica de ferias",
        area="rh",
        slug="doc-rh",
    )
    _create_doc(
        company_id,
        title="Doc TI",
        content="Politica de acesso",
        area="ti",
        slug="doc-ti",
    )

    result = services.read_published_documents(
        company_id=company_id,
        allowed_areas={"rh"},
        include_content=False,
        return_total=True,
    )
    assert result["total"] == 1
    assert result["items"][0]["area"] == "rh"

    denied = services.read_published_documents(
        company_id=company_id,
        area="ti",
        allowed_areas={"rh"},
        include_content=False,
        return_total=True,
    )
    assert denied["total"] == 0


def test_delete_removes_fts_entry(isolated_store):
    company_id = 1
    created = _create_doc(
        company_id,
        title="Temporario",
        content="conteudo removivel",
        slug="temporario",
    )
    assert created["document_uuid"] in db.search_document_uuids(company_id, "removivel")

    services.delete_document(company_id, "geral", "ops", "temporario")
    assert created["document_uuid"] not in db.search_document_uuids(company_id, "removivel")
