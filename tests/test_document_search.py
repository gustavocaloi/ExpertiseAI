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


def test_listing_uses_existing_index_without_rebuild(isolated_store, monkeypatch):
    company_id = 1
    created = _create_doc(company_id, title="Manual", content="procedimento", slug="manual")

    def fail_rebuild(*_args, **_kwargs):
        raise AssertionError("a listagem nao deve reconstruir o indice")

    monkeypatch.setattr(services, "_rebuild_documents_index", fail_rebuild)
    monkeypatch.setattr(services, "_count_document_meta_files_cached", fail_rebuild)
    page = services.read_published_documents(
        company_id=company_id,
        include_content=False,
        return_total=True,
    )
    assert page["total"] == 1
    assert page["items"][0]["document_uuid"] == created["document_uuid"]


def test_listing_returns_empty_when_index_is_missing(isolated_store, monkeypatch):
    company_id = 1
    (services._company_root(company_id)).mkdir(parents=True, exist_ok=True)

    def fail_rebuild(*_args, **_kwargs):
        raise AssertionError("listagem sem indice nao deve varrer o disco")

    monkeypatch.setattr(services, "_rebuild_documents_index", fail_rebuild)
    page = services.read_published_documents(
        company_id=company_id,
        include_content=False,
        return_total=True,
    )
    assert page["total"] == 0
    assert page["items"] == []


def test_kb_status_counts_new_storage_when_legacy_dirs_remain(isolated_store):
    services._KB_MAINTENANCE_STATUS.clear()
    company_id = 1
    _create_doc(company_id, title="Manual", content="procedimento", slug="manual")
    leftover = services._company_root(company_id) / "area-antiga"
    leftover.mkdir()
    assert services._company_has_legacy_document_dirs(company_id) is True
    status = services.get_kb_maintenance_status(company_id)
    assert status["meta_count"] == 1
    assert status["indexed_count"] == 1
    assert status["index_ready"] is True


def test_kb_status_skips_disk_walk_while_rebuild_is_running(isolated_store, monkeypatch):
    services._set_kb_maintenance_status(
        1,
        running=True,
        phase="migrating_documents",
        processed=3,
        total=10,
        indexed=3,
    )

    def fail_disk_walk(*_args, **_kwargs):
        raise AssertionError("kb-status não deve varrer o disco durante a manutenção")

    monkeypatch.setattr(services, "_read_documents_index", fail_disk_walk)
    monkeypatch.setattr(services, "_count_document_meta_files_cached", fail_disk_walk)
    status = services.get_kb_maintenance_status(1)
    assert status["running"] is True
    assert status["total"] == 10
    assert status["processed"] == 3
    assert status["index_ready"] is False
    services._KB_MAINTENANCE_STATUS.clear()
