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
                parent_area TEXT,
                FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE,
                UNIQUE(company_id, kind, name)
            )
            """
        )
        tax_columns = {row["name"] for row in cur.execute("PRAGMA table_info(taxonomies)").fetchall()}
        if "parent_area" not in tax_columns:
            cur.execute("ALTER TABLE taxonomies ADD COLUMN parent_area TEXT")

        _ensure_taxonomy_parent_area_default(conn)
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_tax_company_kind ON taxonomies (company_id, kind)
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_tax_company_kind_parent_area
            ON taxonomies (company_id, kind, parent_area)
            """
        )
        if _needs_taxonomy_migration(conn):
            _migrate_taxonomies_schema(conn)
        conn.commit()
    finally:
        conn.close()


def _ensure_taxonomy_parent_area_default(conn: sqlite3.Connection) -> None:
    columns = conn.execute("PRAGMA table_info(taxonomies)").fetchall()
    has_parent_area = any(row[1] == "parent_area" for row in columns)
    if not has_parent_area:
        return
    conn.execute("UPDATE taxonomies SET parent_area = '' WHERE parent_area IS NULL")


def _needs_taxonomy_migration(conn: sqlite3.Connection) -> bool:
    try:
        indexes = conn.execute("PRAGMA index_list(taxonomies)").fetchall()
    except sqlite3.DatabaseError:
        return False

    for index in indexes:
        index_name = index[1]
        is_unique = bool(index[2])
        if not is_unique:
            continue
        index_columns = conn.execute(f"PRAGMA index_info({index_name})").fetchall()
        col_names = [row[2] for row in index_columns]
        if col_names == ["company_id", "kind", "name"]:
            return True
        if col_names == ["company_id", "kind", "name", "parent_area"]:
            return False

    return False


def _migrate_taxonomies_schema(conn: sqlite3.Connection) -> None:
    conn.execute("ALTER TABLE taxonomies RENAME TO taxonomies_old")
    conn.execute(
        """
        CREATE TABLE taxonomies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER NOT NULL,
            kind TEXT NOT NULL CHECK(kind IN ('area', 'categoria')),
            name TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            parent_area TEXT NOT NULL DEFAULT '',
            FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE,
            UNIQUE(company_id, kind, name, parent_area)
        )
        """
    )
    conn.execute(
        """
        INSERT INTO taxonomies (company_id, kind, name, is_active, created_at, parent_area)
        SELECT
            company_id,
            kind,
            name,
            is_active,
            created_at,
            CASE
              WHEN kind = 'categoria' THEN COALESCE(parent_area, '')
              ELSE ''
            END AS parent_area
        FROM taxonomies_old
        """
    )
    conn.execute("DROP TABLE taxonomies_old")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tax_company_kind ON taxonomies (company_id, kind)")
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_tax_company_kind_parent_area
        ON taxonomies (company_id, kind, parent_area)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_tax_company_kind_name_parent_area_uq
        ON taxonomies (company_id, kind, name, parent_area)
        """
    )


def _taxonomy_normalize_name(name: str) -> str:
    text = (name or '').strip().lower()
    text = re.sub(r"[^a-z0-9_.-]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text


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


def list_taxonomies(company_id: int, kind: str) -> list[str] | list[dict]:
    conn = get_connection()
    try:
        if kind == "categoria":
            rows = conn.execute(
                """
                SELECT name, parent_area
                FROM taxonomies
                WHERE company_id = ? AND kind = ? AND is_active = 1
                ORDER BY COALESCE(parent_area, ''), name
                """,
                (company_id, kind),
            ).fetchall()
            return [{"name": row["name"], "area": row["parent_area"] or ""} for row in rows]
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


def create_taxonomy(company_id: int, kind: str, name: str, parent_area: Optional[str] = None) -> str:
    cleaned = _taxonomy_normalize_name(name)
    if not cleaned:
        raise ValueError("Nome inválido")
    cleaned_parent_area = _taxonomy_normalize_name(parent_area) if kind == "categoria" else ""
    if kind == "categoria" and not cleaned_parent_area:
        raise ValueError("A categoria precisa de uma área vinculada.")
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO taxonomies
            (company_id, kind, name, is_active, created_at, parent_area)
            VALUES (?, ?, ?, 1, ?, ?)
            """,
            (company_id, kind, cleaned, _now(), cleaned_parent_area),
        )
        conn.commit()
        return cleaned
    finally:
        conn.close()


def delete_taxonomy(company_id: int, kind: str, name: str, area: Optional[str] = None) -> None:
    cleaned = _taxonomy_normalize_name(name)
    cleaned_parent_area = _taxonomy_normalize_name(area) if kind == "categoria" else ""
    conn = get_connection()
    try:
        affected_rows = 0
        if kind == "categoria" and cleaned_parent_area:
            cursor = conn.execute(
                """
                DELETE FROM taxonomies
                WHERE company_id = ? AND kind = ? AND name = ? AND COALESCE(parent_area, '') = ?
                """,
                (company_id, kind, cleaned, cleaned_parent_area),
            )
            affected_rows = cursor.rowcount
        else:
            cursor = conn.execute(
                """
                DELETE FROM taxonomies
                WHERE company_id = ? AND kind = ? AND name = ?
                """,
                (company_id, kind, cleaned),
            )
            affected_rows = cursor.rowcount
        conn.commit()
        if not affected_rows:
            if kind == "categoria" and cleaned_parent_area:
                raise ValueError("Categoria não encontrada para a área informada.")
            raise ValueError(f"{kind} não encontrada.")
        if affected_rows > 1 and kind == "categoria" and cleaned_parent_area:
            raise ValueError("Dados inconsistentes no cadastro de categorias.")
        if affected_rows > 1 and kind == "categoria" and not cleaned_parent_area:
            raise ValueError("A categoria informada está vinculada a mais de uma área. Informe a área.")
        return
    finally:
        conn.close()


def taxonomy_exists(company_id: int, kind: str, name: str, area: Optional[str] = None) -> bool:
    cleaned = _taxonomy_normalize_name(name)
    conn = get_connection()
    try:
        if kind == "categoria" and area:
            row = conn.execute(
                """
                SELECT 1 FROM taxonomies
                WHERE company_id = ? AND kind = ? AND is_active = 1
                  AND name = ? AND COALESCE(parent_area, '') = ?
                LIMIT 1
                """,
                (company_id, kind, cleaned, _taxonomy_normalize_name(area)),
            ).fetchone()
            if row:
                return True
            row = conn.execute(
                """
                SELECT 1 FROM taxonomies
                WHERE company_id = ? AND kind = ? AND is_active = 1 AND name = ? AND parent_area IS NULL
                LIMIT 1
                """,
                (company_id, kind, cleaned),
            ).fetchone()
            if row:
                return True

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
