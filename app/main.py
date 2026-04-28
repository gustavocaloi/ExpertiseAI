from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import db, services
from . import kb_routes, routers
from .config import (
    ACCESS_CONTROL_ENABLED,
    ALLOW_PUBLIC_COMPANY_CREATE,
    APP_ENV,
    BOOTSTRAP_DEFAULT_ADMIN,
    DOCLING_CACHE_DIR,
    DEFAULT_ADMIN_EMAIL,
    DEFAULT_ADMIN_NAME,
    DEFAULT_ADMIN_PASSWORD,
    DEFAULT_COMPANY_DESCRIPTION,
    DEFAULT_COMPANY_NAME,
    DEFAULT_COMPANY_SLUG,
    API_BASE_URL,
    LOG_LEVEL,
    REBUILD_KB_ON_START,
)
from .security import hash_password

logger = logging.getLogger(__name__)


def _configure_logging() -> None:
    level_name = LOG_LEVEL.strip().upper()
    aliases = {
        "WARN": "WARNING",
        "ERRO": "ERROR",
    }
    resolved_name = aliases.get(level_name, level_name)
    resolved_level = getattr(logging, resolved_name, logging.INFO)
    logging.basicConfig(
        level=resolved_level,
        format="%(levelname)s %(name)s: %(message)s",
        force=True,
    )
    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access", "fastapi"):
        logging.getLogger(logger_name).setLevel(resolved_level)


def _install_ordered_openapi(app: FastAPI) -> None:
    def custom_openapi() -> dict:
        if app.openapi_schema:
            return app.openapi_schema

        openapi_schema = get_openapi(
            title=app.title,
            version=app.version,
            routes=app.routes,
            servers=app.servers,
        )
        paths = openapi_schema.get("paths", {})
        v1_published_path = "/api/v1/empresas/{company_id}/documentos/publicados"
        v2_published_path = "/api/v2/empresas/{company_id}/documentos/publicados"
        if v1_published_path in paths and v2_published_path in paths:
            ordered_paths = {}
            for path, path_schema in paths.items():
                ordered_paths[path] = path_schema
                if path == v1_published_path:
                    ordered_paths[v2_published_path] = paths[v2_published_path]
            openapi_schema["paths"] = ordered_paths

        app.openapi_schema = openapi_schema
        return app.openapi_schema

    app.openapi = custom_openapi


async def _upload_jobs_cleanup_loop() -> None:
    while True:
        kb_routes.cleanup_zombie_upload_jobs()
        await asyncio.sleep(30)


def create_app() -> FastAPI:
    startup_t0 = time.perf_counter()
    _configure_logging()
    logger.info("Inicializando Expertise.AI app. env=%s access_control=%s", APP_ENV, ACCESS_CONTROL_ENABLED)
    if APP_ENV == "production" and not ACCESS_CONTROL_ENABLED:
        raise RuntimeError("EXPAI_ACCESS_CONTROL_ENABLED=false não é permitido quando EXPAI_APP_ENV=production.")
    if APP_ENV == "production" and ALLOW_PUBLIC_COMPANY_CREATE:
        raise RuntimeError("EXPAI_ALLOW_PUBLIC_COMPANY_CREATE=true não é permitido quando EXPAI_APP_ENV=production.")
    openapi_servers = [{"url": API_BASE_URL, "description": "Servidor configurado"}] if API_BASE_URL else None
    app = FastAPI(
        title="Expertise.AI",
        version="0.1.0",
        servers=openapi_servers,
    )
    static_dir = Path(__file__).resolve().parent / "static"
    static_dir.mkdir(parents=True, exist_ok=True)

    step_t0 = time.perf_counter()
    logger.info("Startup step: init_db iniciado.")
    db.init_db()
    logger.info("Startup step: init_db concluido em %.2fs.", time.perf_counter() - step_t0)

    step_t0 = time.perf_counter()
    logger.info("Startup step: preparando diretorio do cache Docling em %s.", DOCLING_CACHE_DIR)
    DOCLING_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("Startup step: diretorio do cache Docling pronto em %.2fs.", time.perf_counter() - step_t0)

    if BOOTSTRAP_DEFAULT_ADMIN:
        step_t0 = time.perf_counter()
        logger.info("Startup step: ensure_default_admin iniciado.")
        db.ensure_default_admin(
            company_name=DEFAULT_COMPANY_NAME,
            company_description=DEFAULT_COMPANY_DESCRIPTION,
            company_slug=DEFAULT_COMPANY_SLUG,
            admin_name=DEFAULT_ADMIN_NAME,
            admin_email=DEFAULT_ADMIN_EMAIL,
            admin_password_hash=hash_password(DEFAULT_ADMIN_PASSWORD),
        )
        logger.info("Startup step: ensure_default_admin concluido em %.2fs.", time.perf_counter() - step_t0)

    step_t0 = time.perf_counter()
    if REBUILD_KB_ON_START:
        logger.info("Startup step: rebuild_documents_from_markdown_files iniciado.")
        summary = services.rebuild_documents_from_markdown_files(force=False)
        logger.info(
            "Startup step: rebuild_documents_from_markdown_files concluido em %.2fs. resumo=%s",
            time.perf_counter() - step_t0,
            summary,
        )
    else:
        logger.info("Startup step: migrate_documents_storage_layout iniciado.")
        migrated = services.migrate_documents_storage_layout()
        logger.info(
            "Startup step: migrate_documents_storage_layout concluido em %.2fs. migrados=%s",
            time.perf_counter() - step_t0,
            migrated,
        )

    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    app.include_router(routers.router, prefix="/api/v1")
    app.include_router(kb_routes.router, prefix="/api/v1")
    app.include_router(kb_routes.router_v2, prefix="/api/v2")
    _install_ordered_openapi(app)
    logger.info("Aplicacao FastAPI criada em %.2fs.", time.perf_counter() - startup_t0)

    @app.on_event("startup")
    async def startup_cleanup_upload_jobs() -> None:
        startup_event_t0 = time.perf_counter()
        logger.info("Startup event: ensure_docling_models_ready_async iniciado.")
        await services.ensure_docling_models_ready_async()
        logger.info(
            "Startup event: ensure_docling_models_ready_async concluido em %.2fs.",
            time.perf_counter() - startup_event_t0,
        )
        cleanup_t0 = time.perf_counter()
        cleaned = kb_routes.cleanup_zombie_upload_jobs()
        logger.info("Startup event: cleanup_zombie_upload_jobs concluido em %.2fs. limpos=%s", time.perf_counter() - cleanup_t0, cleaned)
        app.state.upload_jobs_cleanup_task = asyncio.create_task(_upload_jobs_cleanup_loop())
        logger.info("Startup event completo em %.2fs.", time.perf_counter() - startup_event_t0)

    @app.on_event("shutdown")
    async def shutdown_cleanup_upload_jobs() -> None:
        task = getattr(app.state, "upload_jobs_cleanup_task", None)
        if task:
            task.cancel()

    @app.get("/health")
    def health():
        return {"status": "ok", "service": "Expertise.AI"}

    @app.get("/")
    def index():
        return FileResponse(static_dir / "index.html")

    return app


app = create_app()
