from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import db, services
from . import kb_routes, routers
from .config import (
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


async def _upload_jobs_cleanup_loop() -> None:
    while True:
        kb_routes.cleanup_zombie_upload_jobs()
        await asyncio.sleep(30)


def create_app() -> FastAPI:
    _configure_logging()
    openapi_servers = [{"url": API_BASE_URL, "description": "Servidor configurado"}] if API_BASE_URL else None
    app = FastAPI(
        title="Expertise.AI",
        version="0.1.0",
        servers=openapi_servers,
    )
    static_dir = Path(__file__).resolve().parent / "static"
    static_dir.mkdir(parents=True, exist_ok=True)

    db.init_db()
    DOCLING_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if BOOTSTRAP_DEFAULT_ADMIN:
        db.ensure_default_admin(
            company_name=DEFAULT_COMPANY_NAME,
            company_description=DEFAULT_COMPANY_DESCRIPTION,
            company_slug=DEFAULT_COMPANY_SLUG,
            admin_name=DEFAULT_ADMIN_NAME,
            admin_email=DEFAULT_ADMIN_EMAIL,
            admin_password_hash=hash_password(DEFAULT_ADMIN_PASSWORD),
        )

    if REBUILD_KB_ON_START:
        services.rebuild_documents_from_markdown_files(force=False)
    else:
        services.migrate_documents_storage_layout()

    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    app.include_router(routers.router, prefix="/api/v1")
    app.include_router(kb_routes.router, prefix="/api/v1")

    @app.on_event("startup")
    async def startup_cleanup_upload_jobs() -> None:
        await services.ensure_docling_models_ready_async()
        kb_routes.cleanup_zombie_upload_jobs()
        app.state.upload_jobs_cleanup_task = asyncio.create_task(_upload_jobs_cleanup_loop())

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
