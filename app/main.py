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
    KB_STARTUP_MAINTENANCE_MODE,
    LOG_LEVEL,
    REBUILD_KB_ON_START,
)
from .mcp_server import create_mcp_component
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


def _run_kb_startup_maintenance_sync() -> None:
    step_t0 = time.perf_counter()
    if REBUILD_KB_ON_START:
        logger.info("Startup maintenance: rebuild_documents_from_markdown_files iniciado.")
        summary = services.rebuild_documents_from_markdown_files(force=False)
        logger.info(
            "Startup maintenance: rebuild_documents_from_markdown_files concluido em %.2fs. resumo=%s",
            time.perf_counter() - step_t0,
            summary,
        )
        return

    logger.info("Startup maintenance: migrate_documents_storage_layout iniciado.")
    migrated = services.migrate_documents_storage_layout()
    logger.info(
        "Startup maintenance: migrate_documents_storage_layout concluido em %.2fs. migrados=%s",
        time.perf_counter() - step_t0,
        migrated,
    )


async def _run_kb_startup_maintenance() -> None:
    try:
        await asyncio.to_thread(_run_kb_startup_maintenance_sync)
    except Exception:
        logger.exception("Startup maintenance: falha na manutencao da base de conhecimento.")


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
    mcp_component = create_mcp_component()
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

    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    app.include_router(routers.router, prefix="/api/v1")
    app.include_router(kb_routes.router, prefix="/api/v1")
    app.include_router(kb_routes.router_v2, prefix="/api/v2")
    if mcp_component is not None:
        app.mount(mcp_component.mount_path, mcp_component.app, name="mcp")
    _install_ordered_openapi(app)
    logger.info("Aplicacao FastAPI criada em %.2fs.", time.perf_counter() - startup_t0)

    @app.on_event("startup")
    async def startup_cleanup_upload_jobs() -> None:
        startup_event_t0 = time.perf_counter()
        if mcp_component is not None:
            logger.info("Startup event: session_manager MCP iniciado em %s.", mcp_component.mount_path)
            app.state.mcp_session_manager_cm = mcp_component.server.session_manager.run()
            await app.state.mcp_session_manager_cm.__aenter__()
        logger.info("Startup event: ensure_docling_models_ready_async iniciado.")
        await services.ensure_docling_models_ready_async()
        logger.info(
            "Startup event: ensure_docling_models_ready_async concluido em %.2fs.",
            time.perf_counter() - startup_event_t0,
        )
        maintenance_mode = KB_STARTUP_MAINTENANCE_MODE
        if maintenance_mode == "blocking":
            logger.info("Startup event: manutencao da KB em modo blocking.")
            await asyncio.to_thread(_run_kb_startup_maintenance_sync)
        elif maintenance_mode == "background":
            logger.info("Startup event: manutencao da KB agendada em background.")
            app.state.kb_startup_maintenance_task = asyncio.create_task(_run_kb_startup_maintenance())
        elif maintenance_mode == "disabled":
            logger.info("Startup event: manutencao da KB no boot desabilitada.")
        else:
            logger.warning(
                "Startup event: EXPAI_KB_STARTUP_MAINTENANCE_MODE=%r invalido; usando background.",
                maintenance_mode,
            )
            app.state.kb_startup_maintenance_task = asyncio.create_task(_run_kb_startup_maintenance())
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
        kb_task = getattr(app.state, "kb_startup_maintenance_task", None)
        if kb_task and not kb_task.done():
            kb_task.cancel()
        mcp_session_manager_cm = getattr(app.state, "mcp_session_manager_cm", None)
        if mcp_session_manager_cm is not None:
            await mcp_session_manager_cm.__aexit__(None, None, None)

    @app.get("/health")
    def health():
        return {"status": "ok", "service": "Expertise.AI"}

    @app.get("/mcp-status")
    def mcp_status():
        return {
            "enabled": mcp_component is not None,
            "mount_path": mcp_component.mount_path if mcp_component is not None else None,
            "transport": "streamable-http" if mcp_component is not None else None,
        }

    @app.get("/")
    def index():
        return FileResponse(static_dir / "index.html")

    return app


app = create_app()
