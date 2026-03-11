from __future__ import annotations

import os
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("EXPAI_DATA_DIR", ROOT_DIR / "data"))
DB_PATH = Path(os.getenv("EXPAI_DB_PATH", DATA_DIR / "system.sqlite3"))
KB_ROOT = Path(os.getenv("EXPAI_KB_ROOT", DATA_DIR / "kb_store"))

SECRET_KEY = os.getenv("EXPAI_SECRET_KEY", "change-me")
ALGORITHM = os.getenv("EXPAI_JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("EXPAI_ACCESS_TOKEN_EXPIRE_MINUTES", "480"))
ACCESS_CONTROL_ENABLED = os.getenv("EXPAI_ACCESS_CONTROL_ENABLED", "true").lower() in {"1", "true", "yes"}

DOCLING_ENABLED = os.getenv("EXPAI_DOCLING_ENABLED", "true").lower() in {"1", "true", "yes"}

BOOTSTRAP_DEFAULT_ADMIN = os.getenv("EXPAI_BOOTSTRAP_DEFAULT_ADMIN", "true").lower() in {"1", "true", "yes"}
DEFAULT_COMPANY_NAME = os.getenv("EXPAI_DEFAULT_COMPANY_NAME", "Expertise.AI")
DEFAULT_COMPANY_SLUG = os.getenv("EXPAI_DEFAULT_COMPANY_SLUG", "expai")
DEFAULT_ADMIN_NAME = os.getenv("EXPAI_DEFAULT_ADMIN_NAME", "Administrador Expertise.AI")
DEFAULT_ADMIN_EMAIL = os.getenv("EXPAI_DEFAULT_ADMIN_EMAIL", "admin@expertise.ai.local")
DEFAULT_ADMIN_PASSWORD = os.getenv("EXPAI_DEFAULT_ADMIN_PASSWORD", "Admin@123")
SUPER_ADMIN_USER = os.getenv("EXPAI_SUPER_ADMIN_USER", "superadmin")
SUPER_ADMIN_PASSWORD = os.getenv("EXPAI_SUPER_ADMIN_PASSWORD", "Admin@123")
