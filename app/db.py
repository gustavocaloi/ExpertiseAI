from __future__ import annotations
import sqlite3
from datetime import datetime
from typing import Optional
import re

from .config import DB_PATH, SUPER_ADMIN_USER


ROLE_NORMALIZATION = {
    "admin": "admin",
    "editor": "editor",
    "aprovador": "aprovador",
    "revisor": "aprovador",
}
ROLE_PRIORITY = {
    "aprovador": 1,
    "editor": 2,
    "admin": 3,
}


def _now() -> str:
    return datetime.utcnow().isoformat() + "Z"


def normalize_access_role(role: str) -> str:
    normalized = str(role or "").strip().lower()
    return ROLE_NORMALIZATION.get(normalized, normalized)


def resolve_effective_role(roles: list[str]) -> Optional[str]:
    normalized_roles = [normalize_access_role(role) for role in roles if normalize_access_role(role) in ROLE_PRIORITY]
    if not normalized_roles:
        return None
    return max(normalized_roles, key=lambda role: ROLE_PRIORITY.get(role, 0))


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
                require_password_change INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
            """
        )
        user_columns = {row["name"] for row in cur.execute("PRAGMA table_info(users)").fetchall()}
        if "require_password_change" not in user_columns:
            cur.execute("ALTER TABLE users ADD COLUMN require_password_change INTEGER NOT NULL DEFAULT 0")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS user_company_roles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                company_id INTEGER NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('admin', 'editor', 'aprovador')),
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
        if _needs_user_company_roles_migration(conn):
            _migrate_user_company_roles_schema(conn)
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
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS access_audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER NOT NULL,
                actor_user_id INTEGER NOT NULL,
                target_user_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                roles_snapshot TEXT NOT NULL DEFAULT '',
                note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE,
                FOREIGN KEY (actor_user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (target_user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_access_audit_company_created
            ON access_audit_log (company_id, created_at DESC)
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS user_company_scope_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                company_id INTEGER NOT NULL,
                area_scope_mode TEXT NOT NULL DEFAULT 'all' CHECK(area_scope_mode IN ('all', 'selected')),
                updated_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE,
                UNIQUE(user_id, company_id)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS user_company_area_scopes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                company_id INTEGER NOT NULL,
                area_name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE,
                UNIQUE(user_id, company_id, area_name)
            )
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_ucas_user_company
            ON user_company_area_scopes (user_id, company_id)
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS area_restriction_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE,
                UNIQUE(company_id, name)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS area_restriction_profile_areas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                profile_id INTEGER NOT NULL,
                area_name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (profile_id) REFERENCES area_restriction_profiles(id) ON DELETE CASCADE,
                UNIQUE(profile_id, area_name)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS user_area_restriction_profile_assignments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                company_id INTEGER NOT NULL,
                profile_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE,
                FOREIGN KEY (profile_id) REFERENCES area_restriction_profiles(id) ON DELETE CASCADE,
                UNIQUE(user_id, company_id, profile_id)
            )
            """
        )
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


def _needs_user_company_roles_migration(conn: sqlite3.Connection) -> bool:
    try:
        row = conn.execute(
            """
            SELECT sql
            FROM sqlite_master
            WHERE type = 'table' AND name = 'user_company_roles'
            """
        ).fetchone()
    except sqlite3.DatabaseError:
        return False
    if not row or not row[0]:
        return False
    sql = str(row[0]).lower()
    return (
        "check(role in ('admin', 'editor', 'aprovador'))" not in sql
        or "unique(user_id, company_id, role)" not in sql
    )


def _migrate_user_company_roles_schema(conn: sqlite3.Connection) -> None:
    conn.execute("ALTER TABLE user_company_roles RENAME TO user_company_roles_old")
    conn.execute(
        """
        CREATE TABLE user_company_roles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            company_id INTEGER NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('admin', 'editor', 'aprovador')),
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE,
            UNIQUE(user_id, company_id, role)
        )
        """
    )
    rows = conn.execute(
        """
        SELECT id, user_id, company_id, role, is_active, created_at
        FROM user_company_roles_old
        ORDER BY user_id, company_id, is_active DESC, created_at DESC, id DESC
        """
    ).fetchall()
    for row in rows:
        normalized_role = normalize_access_role(str(row["role"] or ""))
        if normalized_role not in ROLE_PRIORITY:
            continue
        conn.execute(
            """
            INSERT INTO user_company_roles (user_id, company_id, role, is_active, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id, company_id, role) DO UPDATE SET
              is_active = MAX(user_company_roles.is_active, excluded.is_active),
              created_at = CASE
                WHEN excluded.created_at > user_company_roles.created_at THEN excluded.created_at
                ELSE user_company_roles.created_at
              END
            """,
            (
                row["user_id"],
                row["company_id"],
                normalized_role,
                row["is_active"],
                row["created_at"],
            ),
        )
    conn.execute("DROP TABLE user_company_roles_old")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ucr_user ON user_company_roles (user_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ucr_company ON user_company_roles (company_id)")


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


def create_user(full_name: str, email: str, password_hash: str, require_password_change: bool = False) -> int:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO users (full_name, email, password_hash, require_password_change, created_at) VALUES (?, ?, ?, ?, ?)",
            (full_name, email, password_hash, 1 if require_password_change else 0, _now()),
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


def get_user_by_id(user_id: int) -> Optional[sqlite3.Row]:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        return row
    finally:
        conn.close()


def assign_role_to_user(user_id: int, company_id: int, role: str) -> None:
    normalized_role = normalize_access_role(role)
    if normalized_role not in ROLE_PRIORITY:
        raise ValueError("role inválido")
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO user_company_roles
            (user_id, company_id, role, is_active, created_at)
            VALUES (?, ?, ?, 1, ?)
            ON CONFLICT(user_id, company_id, role)
            DO UPDATE SET
              is_active = 1,
              created_at = excluded.created_at
            """,
            (user_id, company_id, normalized_role, _now()),
        )
        conn.commit()
    finally:
        conn.close()


def get_user_roles_in_company(user_id: int, company_id: int) -> list[str]:
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT role
            FROM user_company_roles
            WHERE user_id = ? AND company_id = ? AND is_active = 1
            ORDER BY created_at DESC, id DESC
            """,
            (user_id, company_id),
        ).fetchall()
        output: list[str] = []
        for row in rows:
            normalized_role = normalize_access_role(str(row["role"] or ""))
            if normalized_role in ROLE_PRIORITY and normalized_role not in output:
                output.append(normalized_role)
        return output
    finally:
        conn.close()


def get_user_role_in_company(user_id: int, company_id: int) -> Optional[str]:
    return resolve_effective_role(get_user_roles_in_company(user_id, company_id))


def count_admins_in_company(company_id: int, exclude_user_id: Optional[int] = None) -> int:
    conn = get_connection()
    try:
        sql = """
            SELECT COUNT(DISTINCT user_id) AS total
            FROM user_company_roles
            WHERE company_id = ? AND role = 'admin' AND is_active = 1
        """
        params: list[object] = [company_id]
        if exclude_user_id is not None:
            sql += " AND user_id != ?"
            params.append(exclude_user_id)
        row = conn.execute(sql, tuple(params)).fetchone()
        return int(row["total"]) if row else 0
    finally:
        conn.close()


def set_user_roles_in_company(user_id: int, company_id: int, roles: list[str]) -> list[str]:
    normalized_roles: list[str] = []
    for role in roles:
        normalized_role = normalize_access_role(role)
        if normalized_role not in ROLE_PRIORITY:
            raise ValueError("role inválido")
        if normalized_role not in normalized_roles:
            normalized_roles.append(normalized_role)

    conn = get_connection()
    try:
        with conn:
            conn.execute(
                """
                UPDATE user_company_roles
                SET is_active = 0
                WHERE user_id = ? AND company_id = ?
                """,
                (user_id, company_id),
            )
            timestamp = _now()
            for role in normalized_roles:
                conn.execute(
                    """
                    INSERT INTO user_company_roles
                    (user_id, company_id, role, is_active, created_at)
                    VALUES (?, ?, ?, 1, ?)
                    ON CONFLICT(user_id, company_id, role)
                    DO UPDATE SET
                      is_active = 1,
                      created_at = excluded.created_at
                    """,
                    (user_id, company_id, role, timestamp),
                )
        return normalized_roles
    finally:
        conn.close()


def revoke_all_user_roles_in_company(user_id: int, company_id: int) -> None:
    conn = get_connection()
    try:
        with conn:
            conn.execute(
                """
                UPDATE user_company_roles
                SET is_active = 0
                WHERE user_id = ? AND company_id = ?
                """,
                (user_id, company_id),
            )
    finally:
        conn.close()


def update_user_account(
    user_id: int,
    full_name: Optional[str] = None,
    password_hash: Optional[str] = None,
    require_password_change: Optional[bool] = None,
) -> None:
    updates: list[str] = []
    params: list[object] = []
    if full_name is not None:
        updates.append("full_name = ?")
        params.append(full_name)
    if password_hash is not None:
        updates.append("password_hash = ?")
        params.append(password_hash)
    if require_password_change is not None:
        updates.append("require_password_change = ?")
        params.append(1 if require_password_change else 0)
    if not updates:
        return

    params.append(user_id)
    conn = get_connection()
    try:
        conn.execute(
            f"UPDATE users SET {', '.join(updates)} WHERE id = ?",
            tuple(params),
        )
        conn.commit()
    finally:
        conn.close()


def record_access_audit_event(
    company_id: int,
    actor_user_id: int,
    target_user_id: int,
    action: str,
    roles: Optional[list[str]] = None,
    note: str = "",
) -> None:
    snapshot = ",".join([normalize_access_role(role) for role in (roles or []) if normalize_access_role(role) in ROLE_PRIORITY])
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO access_audit_log
            (company_id, actor_user_id, target_user_id, action, roles_snapshot, note, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (company_id, actor_user_id, target_user_id, action, snapshot, note or "", _now()),
        )
        conn.commit()
    finally:
        conn.close()


def list_access_audit_events(company_id: int, limit: int = 20, offset: int = 0) -> dict:
    conn = get_connection()
    try:
        safe_limit = max(1, min(limit, 100))
        safe_offset = max(0, offset)
        total_row = conn.execute(
            """
            SELECT COUNT(*) AS total
            FROM access_audit_log
            WHERE company_id = ?
            """,
            (company_id,),
        ).fetchone()
        rows = conn.execute(
            """
            SELECT
              log.id,
              log.action,
              log.roles_snapshot,
              log.note,
              log.created_at,
              actor.full_name AS actor_name,
              actor.email AS actor_email,
              target.full_name AS target_name,
              target.email AS target_email
            FROM access_audit_log log
            JOIN users actor ON actor.id = log.actor_user_id
            JOIN users target ON target.id = log.target_user_id
            WHERE log.company_id = ?
            ORDER BY log.created_at DESC, log.id DESC
            LIMIT ?
            OFFSET ?
            """,
            (company_id, safe_limit, safe_offset),
        ).fetchall()
        output: list[dict] = []
        for row in rows:
            roles = [item for item in str(row["roles_snapshot"] or "").split(",") if item]
            output.append(
                {
                    "id": int(row["id"]),
                    "action": row["action"],
                    "roles": roles,
                    "note": row["note"] or "",
                    "created_at": row["created_at"],
                    "actor_name": row["actor_name"] or row["actor_email"] or "-",
                    "actor_email": row["actor_email"] or "-",
                    "target_name": row["target_name"] or row["target_email"] or "-",
                    "target_email": row["target_email"] or "-",
                }
            )
        return {
            "items": output,
            "total": int(total_row["total"]) if total_row and total_row["total"] is not None else 0,
            "limit": safe_limit,
            "offset": safe_offset,
        }
    finally:
        conn.close()


def get_user_area_scope(user_id: int, company_id: int) -> dict:
    conn = get_connection()
    try:
        row = conn.execute(
            """
            SELECT area_scope_mode
            FROM user_company_scope_settings
            WHERE user_id = ? AND company_id = ?
            LIMIT 1
            """,
            (user_id, company_id),
        ).fetchone()
        rows = conn.execute(
            """
            SELECT area_name
            FROM user_company_area_scopes
            WHERE user_id = ? AND company_id = ?
            ORDER BY area_name
            """,
            (user_id, company_id),
        ).fetchall()
        areas = [str(item["area_name"] or "").strip() for item in rows if str(item["area_name"] or "").strip()]
        return {
            "mode": str(row["area_scope_mode"] or "all") if row else "all",
            "areas": areas,
        }
    finally:
        conn.close()


def list_area_restriction_profiles(company_id: int) -> list[dict]:
    conn = get_connection()
    try:
        profile_rows = conn.execute(
            """
            SELECT id, name, description, created_at, updated_at
            FROM area_restriction_profiles
            WHERE company_id = ?
            ORDER BY name
            """,
            (company_id,),
        ).fetchall()
        area_rows = conn.execute(
            """
            SELECT p.id AS profile_id, a.area_name
            FROM area_restriction_profiles p
            LEFT JOIN area_restriction_profile_areas a ON a.profile_id = p.id
            WHERE p.company_id = ?
            ORDER BY p.name, a.area_name
            """,
            (company_id,),
        ).fetchall()
        profiles: dict[int, dict] = {}
        for row in profile_rows:
            profiles[int(row["id"])] = {
                "id": int(row["id"]),
                "name": row["name"],
                "description": row["description"] or "",
                "areas": [],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
        for row in area_rows:
            profile_id = int(row["profile_id"])
            area_name = str(row["area_name"] or "").strip()
            if profile_id in profiles and area_name:
                profiles[profile_id]["areas"].append(area_name)
        return list(profiles.values())
    finally:
        conn.close()


def create_area_restriction_profile(company_id: int, name: str, areas: list[str], description: str = "") -> dict:
    cleaned_name = str(name or "").strip()
    if not cleaned_name:
        raise ValueError("Nome do perfil é obrigatório")
    cleaned_areas: list[str] = []
    for area in areas:
        cleaned = str(area or "").strip()
        if cleaned and cleaned not in cleaned_areas:
            cleaned_areas.append(cleaned)
    if not cleaned_areas:
        raise ValueError("Selecione ao menos uma área para o perfil")

    conn = get_connection()
    try:
        with conn:
            cursor = conn.execute(
                """
                INSERT INTO area_restriction_profiles (company_id, name, description, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (company_id, cleaned_name, description or "", _now(), _now()),
            )
            profile_id = int(cursor.lastrowid)
            for area_name in cleaned_areas:
                conn.execute(
                    """
                    INSERT INTO area_restriction_profile_areas (profile_id, area_name, created_at)
                    VALUES (?, ?, ?)
                    """,
                    (profile_id, area_name, _now()),
                )
        return {
            "id": profile_id,
            "name": cleaned_name,
            "description": description or "",
            "areas": cleaned_areas,
        }
    except sqlite3.IntegrityError as exc:
        raise ValueError("Já existe um perfil de restrição com esse nome.") from exc
    finally:
        conn.close()


def delete_area_restriction_profile(company_id: int, profile_id: int) -> None:
    conn = get_connection()
    try:
        cursor = conn.execute(
            """
            DELETE FROM area_restriction_profiles
            WHERE company_id = ? AND id = ?
            """,
            (company_id, profile_id),
        )
        conn.commit()
        if cursor.rowcount <= 0:
            raise ValueError("Perfil de restrição não encontrado.")
    finally:
        conn.close()


def get_user_assigned_area_profile_ids(user_id: int, company_id: int) -> list[int]:
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT profile_id
            FROM user_area_restriction_profile_assignments
            WHERE user_id = ? AND company_id = ?
            ORDER BY profile_id
            """,
            (user_id, company_id),
        ).fetchall()
        return [int(row["profile_id"]) for row in rows]
    finally:
        conn.close()


def set_user_assigned_area_profiles(user_id: int, company_id: int, profile_ids: list[int]) -> list[int]:
    cleaned_ids: list[int] = []
    for profile_id in profile_ids:
        try:
            cleaned = int(profile_id)
        except (TypeError, ValueError):
            continue
        if cleaned > 0 and cleaned not in cleaned_ids:
            cleaned_ids.append(cleaned)

    conn = get_connection()
    try:
        available_rows = conn.execute(
            """
            SELECT id
            FROM area_restriction_profiles
            WHERE company_id = ?
            """,
            (company_id,),
        ).fetchall()
        available_ids = {int(row["id"]) for row in available_rows}
        invalid = [profile_id for profile_id in cleaned_ids if profile_id not in available_ids]
        if invalid:
            raise ValueError("Um ou mais perfis de restrição são inválidos para esta empresa.")

        with conn:
            conn.execute(
                """
                DELETE FROM user_area_restriction_profile_assignments
                WHERE user_id = ? AND company_id = ?
                """,
                (user_id, company_id),
            )
            for profile_id in cleaned_ids:
                conn.execute(
                    """
                    INSERT INTO user_area_restriction_profile_assignments (user_id, company_id, profile_id, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (user_id, company_id, profile_id, _now()),
                )
        return cleaned_ids
    finally:
        conn.close()


def get_effective_user_area_scope(user_id: int, company_id: int) -> dict:
    default_scope = get_user_area_scope(user_id, company_id)
    profiles = list_area_restriction_profiles(company_id)
    assigned_ids = get_user_assigned_area_profile_ids(user_id, company_id)
    assigned_profiles = [profile for profile in profiles if int(profile["id"]) in assigned_ids]

    effective_areas: list[str] = []
    if default_scope.get("mode") == "selected":
        for area in default_scope.get("areas") or []:
            cleaned = str(area or "").strip()
            if cleaned and cleaned not in effective_areas:
                effective_areas.append(cleaned)
    for profile in assigned_profiles:
        for area in profile.get("areas") or []:
            cleaned = str(area or "").strip()
            if cleaned and cleaned not in effective_areas:
                effective_areas.append(cleaned)

    if effective_areas:
        effective_mode = "selected"
    elif assigned_profiles:
        effective_mode = "selected"
    else:
        effective_mode = "all" if default_scope.get("mode") == "all" else "selected"

    return {
        "default_scope": default_scope,
        "assigned_profile_ids": assigned_ids,
        "assigned_profiles": assigned_profiles,
        "effective_scope": {
            "mode": effective_mode,
            "areas": effective_areas,
        },
        "profiles": profiles,
    }


def set_user_area_scope(user_id: int, company_id: int, mode: str, areas: list[str]) -> dict:
    normalized_mode = str(mode or "all").strip().lower()
    if normalized_mode not in {"all", "selected"}:
        raise ValueError("mode inválido")

    cleaned_areas: list[str] = []
    for area in areas:
        cleaned = str(area or "").strip()
        if cleaned and cleaned not in cleaned_areas:
            cleaned_areas.append(cleaned)

    conn = get_connection()
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO user_company_scope_settings (user_id, company_id, area_scope_mode, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id, company_id) DO UPDATE SET
                  area_scope_mode = excluded.area_scope_mode,
                  updated_at = excluded.updated_at
                """,
                (user_id, company_id, normalized_mode, _now()),
            )
            conn.execute(
                """
                DELETE FROM user_company_area_scopes
                WHERE user_id = ? AND company_id = ?
                """,
                (user_id, company_id),
            )
            for area_name in cleaned_areas:
                conn.execute(
                    """
                    INSERT INTO user_company_area_scopes (user_id, company_id, area_name, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (user_id, company_id, area_name, _now()),
                )
        return {"mode": normalized_mode, "areas": cleaned_areas}
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
              u.require_password_change,
              r.role,
              r.created_at,
              r.is_active
            FROM users u
            JOIN user_company_roles r ON r.user_id = u.id
            WHERE r.company_id = ?
            ORDER BY u.full_name, r.created_at DESC, r.id DESC
            """,
            (company_id,),
        ).fetchall()
        users_by_id: dict[int, dict] = {}
        for row in rows:
            user_id = int(row["id"])
            if user_id not in users_by_id:
                users_by_id[user_id] = {
                    "id": user_id,
                    "full_name": row["full_name"],
                    "email": row["email"],
                    "require_password_change": bool(row["require_password_change"]) if "require_password_change" in row.keys() else False,
                    "roles": [],
                    "active": False,
                }
            if int(row["is_active"] or 0) != 1:
                continue
            role = normalize_access_role(str(row["role"] or ""))
            if role not in ROLE_PRIORITY:
                continue
            users_by_id[user_id]["active"] = True
            if role not in users_by_id[user_id]["roles"]:
                users_by_id[user_id]["roles"].append(role)
        output: list[dict] = []
        for item in users_by_id.values():
            item["role"] = resolve_effective_role(item["roles"]) or "-"
            scope_bundle = get_effective_user_area_scope(item["id"], company_id)
            scope = scope_bundle.get("effective_scope", {"mode": "all", "areas": []})
            item["area_scope"] = scope
            item["area_scope_profiles"] = scope_bundle.get("assigned_profiles", [])
            item["area_scope_default"] = scope_bundle.get("default_scope", {"mode": "all", "areas": []})
            if scope.get("mode") == "selected":
                area_count = len(scope.get("areas") or [])
                item["area_scope_summary"] = f"{area_count} área(s) permitida(s)"
            else:
                item["area_scope_summary"] = "todas as áreas"
            output.append(item)
        output.sort(key=lambda item: str(item["full_name"] or "").lower())
        return output
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

        require_password_change = int(str(admin_email or "").strip().lower() != str(SUPER_ADMIN_USER or "").strip().lower())
        cur.execute(
            "INSERT INTO users (full_name, email, password_hash, require_password_change, created_at) VALUES (?, ?, ?, ?, ?)",
            (admin_name, admin_email, admin_password_hash, require_password_change, _now()),
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
