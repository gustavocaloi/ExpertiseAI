from __future__ import annotations
import sqlite3
from datetime import datetime
from typing import Optional
import re

from .config import DB_PATH


def _now() -> str:
    return datetime.utcnow().isoformat() + "Z"


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS companies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                slug TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
            )
            """
        )
        company_columns = {row["name"] for row in cur.execute("PRAGMA table_info(companies)").fetchall()}
        if "description" not in company_columns:
            cur.execute("ALTER TABLE companies ADD COLUMN description TEXT NOT NULL DEFAULT ''")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS user_company_roles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                company_id INTEGER NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('admin', 'editor', 'revisor')),
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE,
                UNIQUE(user_id, company_id, role)
            )
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_ucr_user ON user_company_roles (user_id)
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_ucr_company ON user_company_roles (company_id)
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS taxonomies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER NOT NULL,
                kind TEXT NOT NULL CHECK(kind IN ('area', 'categoria')),
                name TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE,
                UNIQUE(company_id, kind, name)
            )
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_tax_company_kind ON taxonomies (company_id, kind)
            """
        )
        conn.commit()
    finally:
        conn.close()


def _taxonomy_normalize_name(name: str) -> str:
    text = (name or '').strip().lower()
    text = re.sub(r"[^a-z0-9_.-]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text or "categoria"


def create_company(name: str, slug: str, description: str = "") -> int:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO companies (name, description, slug, created_at) VALUES (?, ?, ?, ?)",
            (name, description or "", slug, _now()),
        )
        conn.commit()
        return int(cursor.lastrowid)
    finally:
        conn.close()


def ensure_company(company_id: int, company_name: str, company_slug: str, company_description: str = "") -> None:
    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT id, description FROM companies WHERE id = ?",
            (company_id,),
        ).fetchone()
        if existing:
            if company_description and (existing["description"] or "") != company_description:
                conn.execute(
                    "UPDATE companies SET description = ? WHERE id = ?",
                    (company_description, company_id),
                )
                conn.commit()
            return

        cleaned_slug = _taxonomy_normalize_name(company_slug)
        if not cleaned_slug:
            cleaned_slug = f"empresa-{company_id}"

        current_slug = cleaned_slug
        while True:
            try:
                conn.execute(
                    "INSERT INTO companies (id, name, description, slug, created_at) VALUES (?, ?, ?, ?, ?)",
                    (company_id, company_name, company_description or "", current_slug, _now()),
                )
                conn.commit()
                return
            except Exception as exc:
                message = str(exc).lower()
                if "companies.slug" in message:
                    current_slug = f"{cleaned_slug}-{_now()}".replace(":", "-")
                    continue
                raise
    finally:
        conn.close()


def get_company(company_id: int) -> Optional[sqlite3.Row]:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM companies WHERE id = ?",
            (company_id,),
        ).fetchone()
        return row
    finally:
        conn.close()


def get_first_company_id() -> Optional[int]:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id FROM companies ORDER BY id ASC LIMIT 1",
        ).fetchone()
        return int(row["id"]) if row else None
    finally:
        conn.close()


def create_user(full_name: str, email: str, password_hash: str) -> int:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO users (full_name, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
            (full_name, email, password_hash, _now()),
        )
        conn.commit()
        return int(cursor.lastrowid)
    finally:
        conn.close()


def get_user_by_email(email: str) -> Optional[sqlite3.Row]:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM users WHERE email = ?",
            (email,),
        ).fetchone()
        return row
    finally:
        conn.close()


def assign_role_to_user(user_id: int, company_id: int, role: str) -> None:
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO user_company_roles
            (user_id, company_id, role, is_active, created_at)
            VALUES (?, ?, ?, 1, ?)
            """,
            (user_id, company_id, role, _now()),
        )
        conn.commit()
    finally:
        conn.close()


def get_user_role_in_company(user_id: int, company_id: int) -> Optional[str]:
    conn = get_connection()
    try:
        row = conn.execute(
            """
            SELECT role FROM user_company_roles
            WHERE user_id = ? AND company_id = ? AND is_active = 1
            LIMIT 1
            """,
            (user_id, company_id),
        ).fetchone()
        return row["role"] if row else None
    finally:
        conn.close()


def list_users_in_company(company_id: int) -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT
              u.id,
              u.full_name,
              u.email,
              r.role,
              r.is_active
            FROM users u
            JOIN user_company_roles r ON r.user_id = u.id
            WHERE r.company_id = ?
            ORDER BY u.full_name
            """,
            (company_id,),
        ).fetchall()
        return [
            {"id": row["id"], "full_name": row["full_name"], "email": row["email"], "role": row["role"], "active": bool(row["is_active"])}
            for row in rows
        ]
    finally:
        conn.close()


def list_taxonomies(company_id: int, kind: str) -> list[str]:
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT name
            FROM taxonomies
            WHERE company_id = ? AND kind = ? AND is_active = 1
            ORDER BY name
            """,
            (company_id, kind),
        ).fetchall()
        return [row["name"] for row in rows]
    finally:
        conn.close()


def create_taxonomy(company_id: int, kind: str, name: str) -> str:
    cleaned = _taxonomy_normalize_name(name)
    if not cleaned:
        raise ValueError("Nome inválido")
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO taxonomies
            (company_id, kind, name, is_active, created_at)
            VALUES (?, ?, ?, 1, ?)
            """,
            (company_id, kind, cleaned, _now()),
        )
        conn.commit()
        return cleaned
    finally:
        conn.close()


def delete_taxonomy(company_id: int, kind: str, name: str) -> None:
    cleaned = _taxonomy_normalize_name(name)
    conn = get_connection()
    try:
        conn.execute(
            """
            DELETE FROM taxonomies
            WHERE company_id = ? AND kind = ? AND name = ?
            """,
            (company_id, kind, cleaned),
        )
        conn.commit()
    finally:
        conn.close()


def taxonomy_exists(company_id: int, kind: str, name: str) -> bool:
    cleaned = _taxonomy_normalize_name(name)
    conn = get_connection()
    try:
        row = conn.execute(
            """
            SELECT 1 FROM taxonomies
            WHERE company_id = ? AND kind = ? AND is_active = 1 AND name = ?
            LIMIT 1
            """,
            (company_id, kind, cleaned),
        ).fetchone()
        return bool(row)
    finally:
        conn.close()


def ensure_default_admin(
    company_name: str,
    company_description: str,
    company_slug: str,
    admin_name: str,
    admin_email: str,
    admin_password_hash: str,
) -> None:
    conn = get_connection()
    try:
        total = conn.execute("SELECT COUNT(*) AS total FROM companies").fetchone()["total"]
        if total > 0:
            return

        cur = conn.cursor()
        cur.execute(
            "INSERT INTO companies (name, description, slug, created_at) VALUES (?, ?, ?, ?)",
            (company_name, company_description or "", company_slug, _now()),
        )
        company_id = int(cur.lastrowid)

        cur.execute(
            "INSERT INTO users (full_name, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
            (admin_name, admin_email, admin_password_hash, _now()),
        )
        admin_user_id = int(cur.lastrowid)

        cur.execute(
            """
            INSERT INTO user_company_roles
            (user_id, company_id, role, is_active, created_at)
            VALUES (?, ?, 'admin', 1, ?)
            """,
            (admin_user_id, company_id, _now()),
        )
        conn.commit()
    finally:
        conn.close()
