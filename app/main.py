from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import db
from . import kb_routes, routers
from .config import BOOTSTRAP_DEFAULT_ADMIN, DEFAULT_ADMIN_EMAIL, DEFAULT_ADMIN_NAME, DEFAULT_ADMIN_PASSWORD, DEFAULT_COMPANY_NAME, DEFAULT_COMPANY_SLUG
from .security import hash_password


def create_app() -> FastAPI:
    app = FastAPI(title="Expertise.AI", version="0.1.0")
    static_dir = Path(__file__).resolve().parent / "static"
    static_dir.mkdir(parents=True, exist_ok=True)

    db.init_db()
    if BOOTSTRAP_DEFAULT_ADMIN:
        db.ensure_default_admin(
            company_name=DEFAULT_COMPANY_NAME,
            company_slug=DEFAULT_COMPANY_SLUG,
            admin_name=DEFAULT_ADMIN_NAME,
            admin_email=DEFAULT_ADMIN_EMAIL,
            admin_password_hash=hash_password(DEFAULT_ADMIN_PASSWORD),
        )
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    app.include_router(routers.router, prefix="/api/v1")
    app.include_router(kb_routes.router, prefix="/api/v1")

    @app.get("/health")
    def health():
        return {"status": "ok", "service": "Expertise.AI"}

    @app.get("/")
    def index():
        return FileResponse(static_dir / "index.html")

    return app


app = create_app()
