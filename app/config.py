from __future__ import annotations

import os
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("EXPAI_DATA_DIR", ROOT_DIR / "data"))
DB_PATH = Path(os.getenv("EXPAI_DB_PATH", DATA_DIR / "system.sqlite3"))
KB_ROOT = Path(os.getenv("EXPAI_KB_ROOT", DATA_DIR / "kb_store"))
LOG_LEVEL = os.getenv("EXPAI_LOG_LEVEL", "INFO").strip().upper()
APP_ENV = os.getenv("EXPAI_APP_ENV", "development").strip().lower()

SECRET_KEY = os.getenv("EXPAI_SECRET_KEY", "change-me")
ALGORITHM = os.getenv("EXPAI_JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("EXPAI_ACCESS_TOKEN_EXPIRE_MINUTES", "480"))
ACCESS_CONTROL_ENABLED = os.getenv("EXPAI_ACCESS_CONTROL_ENABLED", "true").lower() in {"1", "true", "yes"}
ALLOW_PUBLIC_COMPANY_CREATE = os.getenv("EXPAI_ALLOW_PUBLIC_COMPANY_CREATE", "false").lower() in {"1", "true", "yes"}
_api_base_url = os.getenv("EXPAI_API_BASE_URL", "").strip()
API_BASE_URL = _api_base_url or "http://localhost:8000"

DOCLING_ENABLED = os.getenv("EXPAI_DOCLING_ENABLED", "true").lower() in {"1", "true", "yes"}
DOCLING_CACHE_DIR = Path(os.getenv("DOCLING_CACHE_DIR", DATA_DIR / "docling_cache"))
DOCLING_BUNDLED_CACHE_DIR = Path(os.getenv("EXPAI_DOCLING_BUNDLED_CACHE_DIR", "/opt/docling-models"))
DOCLING_TIMEOUT_SECONDS = int(os.getenv("EXPAI_DOCLING_TIMEOUT_SECONDS", "600"))
DOCLING_MAX_PAGES = int(os.getenv("EXPAI_DOCLING_MAX_PAGES", "250"))
DOCLING_MAX_FILE_SIZE_MB = int(os.getenv("EXPAI_DOCLING_MAX_FILE_SIZE_MB", "50"))
DOCLING_PDF_PAGE_BATCH_SIZE = int(os.getenv("EXPAI_DOCLING_PDF_PAGE_BATCH_SIZE", "25"))
DOCLING_THREADS = int(os.getenv("EXPAI_DOCLING_THREADS", "2"))
DOCLING_OCR_ENABLED = os.getenv("EXPAI_DOCLING_OCR_ENABLED", "true").lower() in {"1", "true", "yes"}
DOCLING_TABLE_STRUCTURE_ENABLED = os.getenv("EXPAI_DOCLING_TABLE_STRUCTURE_ENABLED", "true").lower() in {"1", "true", "yes"}
DOCLING_PREFETCH_MODELS = os.getenv("EXPAI_DOCLING_PREFETCH_MODELS", "true").lower() in {"1", "true", "yes"}
REBUILD_KB_ON_START = os.getenv("EXPAI_REBUILD_KB_ON_START", "false").lower() in {"1", "true", "yes"}

BOOTSTRAP_DEFAULT_ADMIN = os.getenv("EXPAI_BOOTSTRAP_DEFAULT_ADMIN", "true").lower() in {"1", "true", "yes"}
DEFAULT_COMPANY_NAME = os.getenv("EXPAI_DEFAULT_COMPANY_NAME", "Expertise.AI")
DEFAULT_COMPANY_DESCRIPTION = os.getenv("EXPAI_DEFAULT_COMPANY_DESCRIPTION", "Base de Conhecimento por Expertise Operacional")
DEFAULT_COMPANY_SLUG = os.getenv("EXPAI_DEFAULT_COMPANY_SLUG", "expai")
DEFAULT_ADMIN_NAME = os.getenv("EXPAI_DEFAULT_ADMIN_NAME", "Administrador Expertise.AI")
DEFAULT_ADMIN_EMAIL = os.getenv("EXPAI_DEFAULT_ADMIN_EMAIL", "admin@expertise.ai.local")
DEFAULT_ADMIN_PASSWORD = os.getenv("EXPAI_DEFAULT_ADMIN_PASSWORD", "Admin@123")
SUPER_ADMIN_USER = os.getenv("EXPAI_SUPER_ADMIN_USER", "superadmin")
SUPER_ADMIN_PASSWORD = os.getenv("EXPAI_SUPER_ADMIN_PASSWORD", "Admin@123")
