from __future__ import annotations

import json
import math
import time
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from . import db
from .config import AI_PROVIDER


MONITORIA_ROLES = {
    "monitoria_admin": 4,
    "monitoria_supervisor": 3,
    "monitoria_analista": 2,
    "monitoria_operador": 1,
}

MONITORIA_SPEAKERS = {"cliente", "operador"}
MONITORIA_JOB_STATUSES = {"queued", "processing", "completed", "failed"}
MONITORIA_CONVERSATION_STATUSES = {"queued", "processing", "completed", "failed"}


def _now() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _row_to_dict(row: Optional[sqlite3.Row]) -> Optional[dict[str, Any]]:
    if row is None:
        return None
    return {key: row[key] for key in row.keys()}


def init_monitoria_tables(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS monitoria_centrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE,
            UNIQUE(company_id, name)
        )
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_monitoria_centrals_company
        ON monitoria_centrals (company_id, is_active)
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS monitoria_teams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER NOT NULL,
            central_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE,
            FOREIGN KEY (central_id) REFERENCES monitoria_centrals(id) ON DELETE CASCADE,
            UNIQUE(central_id, name)
        )
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_monitoria_teams_central
        ON monitoria_teams (central_id, is_active)
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS monitoria_memberships (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            role TEXT NOT NULL CHECK(role IN (
                'monitoria_admin', 'monitoria_supervisor',
                'monitoria_analista', 'monitoria_operador'
            )),
            central_id INTEGER,
            team_id INTEGER,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (central_id) REFERENCES monitoria_centrals(id) ON DELETE SET NULL,
            FOREIGN KEY (team_id) REFERENCES monitoria_teams(id) ON DELETE SET NULL
        )
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_monitoria_memberships_user
        ON monitoria_memberships (company_id, user_id, is_active)
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS monitoria_pillars (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            prompt TEXT NOT NULL DEFAULT '',
            weight REAL NOT NULL DEFAULT 1.0,
            version INTEGER NOT NULL DEFAULT 1,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE,
            UNIQUE(company_id, name, version)
        )
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_monitoria_pillars_company
        ON monitoria_pillars (company_id, is_active)
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS monitoria_ai_settings (
            company_id INTEGER PRIMARY KEY,
            provider TEXT NOT NULL DEFAULT 'mock',
            transcription_model TEXT NOT NULL DEFAULT '',
            evaluation_model TEXT NOT NULL DEFAULT '',
            language TEXT NOT NULL DEFAULT 'pt',
            temperature REAL NOT NULL DEFAULT 0.2,
            is_enabled INTEGER NOT NULL DEFAULT 1,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS monitoria_conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER NOT NULL,
            conversation_uuid TEXT NOT NULL UNIQUE,
            ticket_id TEXT NOT NULL DEFAULT '',
            cliente TEXT NOT NULL DEFAULT '',
            central_id INTEGER,
            team_id INTEGER,
            operador_user_id INTEGER,
            analista_user_id INTEGER,
            audio_path TEXT NOT NULL DEFAULT '',
            audio_filename TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'queued' CHECK(status IN (
                'queued', 'processing', 'completed', 'failed'
            )),
            error_message TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE,
            FOREIGN KEY (central_id) REFERENCES monitoria_centrals(id) ON DELETE SET NULL,
            FOREIGN KEY (team_id) REFERENCES monitoria_teams(id) ON DELETE SET NULL,
            FOREIGN KEY (operador_user_id) REFERENCES users(id) ON DELETE SET NULL,
            FOREIGN KEY (analista_user_id) REFERENCES users(id) ON DELETE SET NULL
        )
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_monitoria_conversations_company
        ON monitoria_conversations (company_id, created_at DESC)
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_monitoria_conversations_filters
        ON monitoria_conversations (company_id, central_id, cliente, operador_user_id, status)
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS monitoria_turns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL,
            turn_index INTEGER NOT NULL,
            speaker TEXT NOT NULL CHECK(speaker IN ('cliente', 'operador')),
            text TEXT NOT NULL DEFAULT '',
            t_start REAL,
            t_end REAL,
            FOREIGN KEY (conversation_id) REFERENCES monitoria_conversations(id) ON DELETE CASCADE,
            UNIQUE(conversation_id, turn_index)
        )
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_monitoria_turns_conversation
        ON monitoria_turns (conversation_id, turn_index)
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS monitoria_pillar_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL,
            pillar_id INTEGER NOT NULL,
            pillar_name TEXT NOT NULL,
            pillar_version INTEGER NOT NULL DEFAULT 1,
            score REAL NOT NULL,
            rationale TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            FOREIGN KEY (conversation_id) REFERENCES monitoria_conversations(id) ON DELETE CASCADE,
            FOREIGN KEY (pillar_id) REFERENCES monitoria_pillars(id) ON DELETE CASCADE,
            UNIQUE(conversation_id, pillar_id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS monitoria_turn_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL,
            turn_id INTEGER NOT NULL,
            pillar_id INTEGER NOT NULL,
            pillar_name TEXT NOT NULL,
            score REAL NOT NULL,
            evidence TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            FOREIGN KEY (conversation_id) REFERENCES monitoria_conversations(id) ON DELETE CASCADE,
            FOREIGN KEY (turn_id) REFERENCES monitoria_turns(id) ON DELETE CASCADE,
            FOREIGN KEY (pillar_id) REFERENCES monitoria_pillars(id) ON DELETE CASCADE,
            UNIQUE(turn_id, pillar_id)
        )
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_monitoria_turn_scores_conversation
        ON monitoria_turn_scores (conversation_id, pillar_id)
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS monitoria_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER NOT NULL,
            job_id TEXT NOT NULL UNIQUE,
            conversation_uuid TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'queued' CHECK(status IN (
                'queued', 'processing', 'completed', 'failed'
            )),
            error_message TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE
        )
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_monitoria_jobs_company
        ON monitoria_jobs (company_id, created_at DESC)
        """
    )

    for table, columns in {
        "monitoria_conversations": {"tipo": "TEXT NOT NULL DEFAULT ''", "provider": "TEXT NOT NULL DEFAULT 'mock'", "evaluation_config": "TEXT"},
        "monitoria_pillar_scores": {"weight": "REAL NOT NULL DEFAULT 1.0", "prompt": "TEXT", "description": "TEXT"},
        "monitoria_pillars": {"family_id": "INTEGER"},
        "monitoria_jobs": {"lease_owner": "TEXT", "lease_until": "REAL", "durable": "INTEGER NOT NULL DEFAULT 0"},
    }.items():
        existing = {row[1] for row in cur.execute(f"PRAGMA table_info({table})")}
        for column, definition in columns.items():
            if column not in existing:
                cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    # Group historical versions without inventing missing historical prompt snapshots.
    cur.execute("""UPDATE monitoria_pillars SET family_id = (
        SELECT MIN(p.id) FROM monitoria_pillars p
        WHERE p.company_id = monitoria_pillars.company_id AND p.name = monitoria_pillars.name
    ) WHERE family_id IS NULL""")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_monitoria_pillars_family ON monitoria_pillars(company_id, family_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_monitoria_jobs_lease ON monitoria_jobs(status, lease_until)")
    # Existing in-flight jobs get a bounded grace period on first migration.
    cur.execute("UPDATE monitoria_jobs SET lease_until = ? WHERE lease_until IS NULL AND durable = 0 AND status IN ('queued', 'processing')", (time.time() + 60,))

    cur.execute("""CREATE TABLE IF NOT EXISTS monitoria_batches (
        batch_id TEXT PRIMARY KEY, company_id INTEGER NOT NULL, created_by INTEGER NOT NULL,
        request_key TEXT NOT NULL, fingerprint TEXT NOT NULL, created_at TEXT NOT NULL,
        UNIQUE(company_id, created_by, request_key),
        FOREIGN KEY(company_id) REFERENCES companies(id) ON DELETE CASCADE
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS monitoria_batch_items (
        batch_id TEXT NOT NULL, item_index INTEGER NOT NULL, filename TEXT NOT NULL,
        metadata TEXT NOT NULL, job_id TEXT, conversation_uuid TEXT, error_message TEXT NOT NULL DEFAULT '',
        PRIMARY KEY(batch_id, item_index),
        FOREIGN KEY(batch_id) REFERENCES monitoria_batches(batch_id) ON DELETE CASCADE
    )""")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_monitoria_batches_owner ON monitoria_batches(company_id, created_by, created_at DESC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_monitoria_durable_queue ON monitoria_jobs(durable, status, id)")

    columns = {r["name"] for r in conn.execute("PRAGMA table_info(monitoria_conversations)")}
    for column in ("area", "categoria"):
        if column not in columns:
            conn.execute(f"ALTER TABLE monitoria_conversations ADD COLUMN {column} TEXT NOT NULL DEFAULT ''")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_monitoria_taxonomy ON monitoria_conversations(company_id, area, categoria, created_at DESC)")


@dataclass
class MonitoriaScope:
    user_id: int
    company_id: int
    is_full_access: bool = False
    roles: list[str] = field(default_factory=list)
    central_ids: set[int] = field(default_factory=set)
    team_ids: set[int] = field(default_factory=set)
    area_mode: Optional[str] = None
    allowed_areas: set[str] = field(default_factory=set)
    operator_only: bool = False
    assigned_analyst_only: bool = False

    def can_access_conversation(self, conversation: dict[str, Any]) -> bool:
        if conversation.get("company_id", self.company_id) != self.company_id:
            return False
        if self.area_mode is not None:
            if self.is_full_access:
                return True
            area = conversation.get("area") or ""
            return bool(self.roles and area and (self.area_mode == "all" or area in self.allowed_areas)
                and (not self.operator_only or conversation.get("operador_user_id") == self.user_id))
        return bool(
            self.is_full_access
            or (self.operator_only and conversation.get("operador_user_id") == self.user_id)
            or conversation.get("central_id") in self.central_ids
            or conversation.get("team_id") in self.team_ids
            or (self.assigned_analyst_only and conversation.get("analista_user_id") == self.user_id)
        )


def normalize_monitoria_role(role: str) -> str:
    return str(role or "").strip().lower()


def resolve_monitoria_scope(
    user_id: int,
    company_id: int,
    *,
    kb_roles: Optional[list[str]] = None,
    access_control_enabled: bool = True,
) -> MonitoriaScope:
    if not access_control_enabled:
        return MonitoriaScope(
            user_id=user_id,
            company_id=company_id,
            is_full_access=True,
            roles=["monitoria_admin"],
        )

    if "monitoria" not in db.get_user_modules(user_id, company_id)["modules"]:
        return MonitoriaScope(user_id=user_id, company_id=company_id, area_mode="selected")
    kb = kb_roles if kb_roles is not None else db.get_user_roles_in_company(user_id, company_id)
    if "admin" in {db.normalize_access_role(r) for r in kb}:
        return MonitoriaScope(
            user_id=user_id,
            company_id=company_id,
            is_full_access=True,
            roles=["monitoria_admin"],
        )

    access = db.get_user_modules(user_id, company_id)
    if "monitoria" not in access["modules"]:
        return MonitoriaScope(user_id=user_id, company_id=company_id, area_mode="selected")
    area_scope = db.get_effective_user_area_scope(user_id, company_id)["effective_scope"]
    role = access["monitoria_role"]
    mode = area_scope.get("mode", "all")
    return MonitoriaScope(user_id=user_id, company_id=company_id, roles=[role], area_mode=mode,
        allowed_areas=set(area_scope.get("areas", [])),
        is_full_access=role == "monitoria_admin" and mode == "all",
        operator_only=role == "monitoria_operador", assigned_analyst_only=role == "monitoria_analista")


def user_has_monitoria_role(scope: MonitoriaScope, *roles: str) -> bool:
    if scope.is_full_access:
        return True
    required = {normalize_monitoria_role(role) for role in roles}
    return bool(required & set(scope.roles))


# --- Centrals / teams / memberships ---

def create_central(company_id: int, name: str) -> dict[str, Any]:
    clean_name = str(name or "").strip()
    if not clean_name:
        raise ValueError("nome da central é obrigatório")
    conn = db.get_connection()
    try:
        cur = conn.execute(
            """
            INSERT INTO monitoria_centrals (company_id, name, is_active, created_at)
            VALUES (?, ?, 1, ?)
            """,
            (company_id, clean_name, _now()),
        )
        conn.commit()
        return get_central(company_id, int(cur.lastrowid))  # type: ignore[arg-type]
    finally:
        conn.close()


def list_centrals(company_id: int, *, active_only: bool = True) -> list[dict[str, Any]]:
    conn = db.get_connection()
    try:
        sql = "SELECT * FROM monitoria_centrals WHERE company_id = ?"
        params: list[Any] = [company_id]
        if active_only:
            sql += " AND is_active = 1"
        sql += " ORDER BY name COLLATE NOCASE"
        return [_row_to_dict(row) for row in conn.execute(sql, params).fetchall()]  # type: ignore[misc]
    finally:
        conn.close()


def get_central(company_id: int, central_id: int) -> Optional[dict[str, Any]]:
    conn = db.get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM monitoria_centrals WHERE company_id = ? AND id = ?",
            (company_id, central_id),
        ).fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


def update_central(company_id: int, central_id: int, *, name: Optional[str] = None, is_active: Optional[bool] = None) -> Optional[dict[str, Any]]:
    current = get_central(company_id, central_id)
    if not current:
        return None
    next_name = str(name).strip() if name is not None else current["name"]
    next_active = int(bool(is_active)) if is_active is not None else int(current["is_active"])
    conn = db.get_connection()
    try:
        conn.execute(
            """
            UPDATE monitoria_centrals
            SET name = ?, is_active = ?
            WHERE company_id = ? AND id = ?
            """,
            (next_name, next_active, company_id, central_id),
        )
        conn.commit()
        return get_central(company_id, central_id)
    finally:
        conn.close()


def create_team(company_id: int, central_id: int, name: str) -> dict[str, Any]:
    clean_name = str(name or "").strip()
    if not clean_name:
        raise ValueError("nome da equipe é obrigatório")
    if not get_central(company_id, central_id):
        raise ValueError("central não encontrada")
    conn = db.get_connection()
    try:
        cur = conn.execute(
            """
            INSERT INTO monitoria_teams (company_id, central_id, name, is_active, created_at)
            VALUES (?, ?, ?, 1, ?)
            """,
            (company_id, central_id, clean_name, _now()),
        )
        conn.commit()
        return get_team(company_id, int(cur.lastrowid))  # type: ignore[arg-type]
    finally:
        conn.close()


def list_teams(company_id: int, *, central_id: Optional[int] = None, active_only: bool = True) -> list[dict[str, Any]]:
    conn = db.get_connection()
    try:
        sql = "SELECT * FROM monitoria_teams WHERE company_id = ?"
        params: list[Any] = [company_id]
        if central_id is not None:
            sql += " AND central_id = ?"
            params.append(central_id)
        if active_only:
            sql += " AND is_active = 1"
        sql += " ORDER BY name COLLATE NOCASE"
        return [_row_to_dict(row) for row in conn.execute(sql, params).fetchall()]  # type: ignore[misc]
    finally:
        conn.close()


def get_team(company_id: int, team_id: int) -> Optional[dict[str, Any]]:
    conn = db.get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM monitoria_teams WHERE company_id = ? AND id = ?",
            (company_id, team_id),
        ).fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


def update_team(
    company_id: int,
    team_id: int,
    *,
    name: Optional[str] = None,
    is_active: Optional[bool] = None,
) -> Optional[dict[str, Any]]:
    current = get_team(company_id, team_id)
    if not current:
        return None
    next_name = str(name).strip() if name is not None else current["name"]
    next_active = int(bool(is_active)) if is_active is not None else int(current["is_active"])
    conn = db.get_connection()
    try:
        conn.execute(
            """
            UPDATE monitoria_teams
            SET name = ?, is_active = ?
            WHERE company_id = ? AND id = ?
            """,
            (next_name, next_active, company_id, team_id),
        )
        conn.commit()
        return get_team(company_id, team_id)
    finally:
        conn.close()


def create_membership(
    company_id: int,
    user_id: int,
    role: str,
    *,
    central_id: Optional[int] = None,
    team_id: Optional[int] = None,
) -> dict[str, Any]:
    if not db.get_user_roles_in_company(user_id, company_id):
        raise ValueError("utilizador sem vínculo ativo com a empresa")
    normalized = normalize_monitoria_role(role)
    if normalized not in MONITORIA_ROLES:
        raise ValueError("papel de monitoria inválido")
    if team_id is not None:
        team = get_team(company_id, team_id)
        if not team or (central_id is not None and team["central_id"] != central_id):
            raise ValueError("equipe não pertence à central/empresa")
        central_id = int(team["central_id"])
    elif central_id is not None and not get_central(company_id, central_id):
        raise ValueError("central não encontrada")
    conn = db.get_connection()
    try:
        cur = conn.execute(
            """
            INSERT INTO monitoria_memberships
            (company_id, user_id, role, central_id, team_id, is_active, created_at)
            VALUES (?, ?, ?, ?, ?, 1, ?)
            """,
            (company_id, user_id, normalized, central_id, team_id, _now()),
        )
        conn.commit()
        return get_membership(company_id, int(cur.lastrowid))  # type: ignore[arg-type]
    finally:
        conn.close()


def list_memberships(
    company_id: int,
    *,
    user_id: Optional[int] = None,
    active_only: bool = True,
) -> list[dict[str, Any]]:
    conn = db.get_connection()
    try:
        sql = "SELECT * FROM monitoria_memberships WHERE company_id = ?"
        params: list[Any] = [company_id]
        if user_id is not None:
            sql += " AND user_id = ?"
            params.append(user_id)
        if active_only:
            sql += " AND is_active = 1"
        sql += " ORDER BY created_at DESC, id DESC"
        return [_row_to_dict(row) for row in conn.execute(sql, params).fetchall()]  # type: ignore[misc]
    finally:
        conn.close()


def get_membership(company_id: int, membership_id: int) -> Optional[dict[str, Any]]:
    conn = db.get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM monitoria_memberships WHERE company_id = ? AND id = ?",
            (company_id, membership_id),
        ).fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


def deactivate_membership(company_id: int, membership_id: int) -> Optional[dict[str, Any]]:
    current = get_membership(company_id, membership_id)
    if not current:
        return None
    conn = db.get_connection()
    try:
        conn.execute(
            "UPDATE monitoria_memberships SET is_active = 0 WHERE company_id = ? AND id = ?",
            (company_id, membership_id),
        )
        conn.commit()
        return get_membership(company_id, membership_id)
    finally:
        conn.close()


# --- Pillars ---

def _insert_pillar_version(conn, company_id, name, description, prompt, weight, *, is_active=True):
    name = str(name or "").strip()
    if not name:
        raise ValueError("nome do pilar é obrigatório")
    weight = float(weight)
    if not math.isfinite(weight) or not 0 < weight <= 100:
        raise ValueError("peso deve ser finito, maior que zero e até 100")
    current = conn.execute("""SELECT COALESCE(MAX(version), 0) AS version, MIN(family_id) AS family_id
        FROM monitoria_pillars WHERE company_id = ? AND name = ?""", (company_id, name)).fetchone()
    timestamp = _now()
    if is_active:
        conn.execute("UPDATE monitoria_pillars SET is_active = 0, updated_at = ? WHERE company_id = ? AND name = ?",
                     (timestamp, company_id, name))
    row = conn.execute("""INSERT INTO monitoria_pillars
        (company_id, name, description, prompt, weight, version, is_active, created_at, updated_at, family_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (company_id, name, str(description), str(prompt), weight, current["version"] + 1,
         int(is_active), timestamp, timestamp, current["family_id"]))
    pillar_id = row.lastrowid
    if current["family_id"] is None:
        conn.execute("UPDATE monitoria_pillars SET family_id = ? WHERE id = ?", (pillar_id, pillar_id))
    return pillar_id


def create_pillar(company_id: int, name: str, *, description: str = "", prompt: str = "", weight: float = 1.0) -> dict[str, Any]:
    conn = db.get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        pillar_id = _insert_pillar_version(conn, company_id, name, description, prompt, weight)
        conn.commit()
        return get_pillar(company_id, pillar_id)
    finally:
        conn.close()


def list_pillars(company_id: int, *, active_only: bool = True) -> list[dict[str, Any]]:
    conn = db.get_connection()
    try:
        sql = "SELECT * FROM monitoria_pillars WHERE company_id = ?"
        params: list[Any] = [company_id]
        if active_only:
            sql += " AND is_active = 1"
        sql += " ORDER BY name COLLATE NOCASE, version DESC"
        return [_row_to_dict(row) for row in conn.execute(sql, params).fetchall()]  # type: ignore[misc]
    finally:
        conn.close()


def get_pillar(company_id: int, pillar_id: int) -> Optional[dict[str, Any]]:
    conn = db.get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM monitoria_pillars WHERE company_id = ? AND id = ?",
            (company_id, pillar_id),
        ).fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


def update_pillar(
    company_id: int,
    pillar_id: int,
    *,
    description: Optional[str] = None,
    prompt: Optional[str] = None,
    weight: Optional[float] = None,
    is_active: Optional[bool] = None,
    bump_version: bool = False,
) -> Optional[dict[str, Any]]:
    conn = db.get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM monitoria_pillars WHERE company_id = ? AND id = ?", (company_id, pillar_id)).fetchone()
        if not row:
            return None
        current = dict(row)
        next_description = current["description"] if description is None else description
        next_prompt = current["prompt"] if prompt is None else prompt
        next_weight = current["weight"] if weight is None else weight
        changed = (next_description, next_prompt, next_weight) != (current["description"], current["prompt"], current["weight"])
        if changed or bump_version:
            conn.execute("UPDATE monitoria_pillars SET is_active = 0, updated_at = ? WHERE id = ?", (_now(), pillar_id))
            pillar_id = _insert_pillar_version(conn, company_id, current["name"], next_description, next_prompt, next_weight,
                is_active=bool(current["is_active"]) if is_active is None else is_active)
        elif is_active is not None:
            if is_active:
                conn.execute("UPDATE monitoria_pillars SET is_active = 0, updated_at = ? WHERE company_id = ? AND family_id = ?",
                    (_now(), company_id, current["family_id"]))
            conn.execute("UPDATE monitoria_pillars SET is_active = ?, updated_at = ? WHERE company_id = ? AND id = ?",
                (int(is_active), _now(), company_id, pillar_id))
        conn.commit()
        return get_pillar(company_id, pillar_id)
    finally:
        conn.close()


# --- AI settings ---

def get_ai_settings(company_id: int) -> dict[str, Any]:
    conn = db.get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM monitoria_ai_settings WHERE company_id = ?",
            (company_id,),
        ).fetchone()
        if row:
            return _row_to_dict(row)  # type: ignore[return-value]
    finally:
        conn.close()
    return {
        "company_id": company_id,
        "provider": AI_PROVIDER or "mock",
        "transcription_model": "",
        "evaluation_model": "",
        "language": "pt",
        "temperature": 0.2,
        "is_enabled": 1,
        "updated_at": None,
    }


def upsert_ai_settings(
    company_id: int,
    *,
    provider: Optional[str] = None,
    transcription_model: Optional[str] = None,
    evaluation_model: Optional[str] = None,
    language: Optional[str] = None,
    temperature: Optional[float] = None,
    is_enabled: Optional[bool] = None,
) -> dict[str, Any]:
    current = get_ai_settings(company_id)
    payload = {
        "provider": (provider or current["provider"] or "mock").strip().lower(),
        "transcription_model": (
            current["transcription_model"] if transcription_model is None else str(transcription_model)
        ),
        "evaluation_model": (
            current["evaluation_model"] if evaluation_model is None else str(evaluation_model)
        ),
        "language": (language or current.get("language") or "pt").strip() or "pt",
        "temperature": float(current["temperature"]) if temperature is None else float(temperature),
        "is_enabled": int(current["is_enabled"]) if is_enabled is None else int(bool(is_enabled)),
        "updated_at": _now(),
    }
    conn = db.get_connection()
    try:
        conn.execute(
            """
            INSERT INTO monitoria_ai_settings
            (company_id, provider, transcription_model, evaluation_model, language, temperature, is_enabled, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(company_id) DO UPDATE SET
              provider = excluded.provider,
              transcription_model = excluded.transcription_model,
              evaluation_model = excluded.evaluation_model,
              language = excluded.language,
              temperature = excluded.temperature,
              is_enabled = excluded.is_enabled,
              updated_at = excluded.updated_at
            """,
            (
                company_id,
                payload["provider"],
                payload["transcription_model"],
                payload["evaluation_model"],
                payload["language"],
                payload["temperature"],
                payload["is_enabled"],
                payload["updated_at"],
            ),
        )
        conn.commit()
        return get_ai_settings(company_id)
    finally:
        conn.close()


# --- Conversations / turns / scores / jobs ---

def create_conversation(
    company_id: int,
    conversation_uuid: str,
    *,
    ticket_id: str = "",
    cliente: str = "",
    tipo: str = "",
    area: str = "",
    categoria: str = "",
    central_id: Optional[int] = None,
    team_id: Optional[int] = None,
    operador_user_id: Optional[int] = None,
    analista_user_id: Optional[int] = None,
    audio_path: str = "",
    audio_filename: str = "",
    status: str = "queued",
    provider: str = "mock",
    connection=None,
) -> dict[str, Any]:
    timestamp = _now()
    conn = connection or db.get_connection()
    try:
        cur = conn.execute(
            """
            INSERT INTO monitoria_conversations
            (company_id, conversation_uuid, ticket_id, cliente, central_id, team_id,
             operador_user_id, analista_user_id, audio_path, audio_filename,
             status, error_message, created_at, updated_at, tipo, provider, area, categoria)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '', ?, ?, ?, ?, ?, ?)
            """,
            (
                company_id,
                conversation_uuid,
                str(ticket_id or ""),
                str(cliente or ""),
                central_id,
                team_id,
                operador_user_id,
                analista_user_id,
                audio_path,
                audio_filename,
                status,
                timestamp,
                timestamp,
                tipo,
                provider, area, categoria,
            ),
        )
        if connection is None:
            conn.commit()
        return dict(conn.execute("SELECT * FROM monitoria_conversations WHERE id = ?", (cur.lastrowid,)).fetchone())
    finally:
        if connection is None:
            conn.close()


def update_conversation(
    company_id: int,
    conversation_uuid: str,
    **fields: Any,
) -> Optional[dict[str, Any]]:
    allowed = {
        "tipo", "area", "categoria",
        "provider",
        "ticket_id",
        "cliente",
        "central_id",
        "team_id",
        "operador_user_id",
        "analista_user_id",
        "audio_path",
        "audio_filename",
        "status",
        "error_message",
    }
    updates = {key: value for key, value in fields.items() if key in allowed}
    if not updates:
        return get_conversation_by_uuid(company_id, conversation_uuid)
    updates["updated_at"] = _now()
    assignments = ", ".join(f"{key} = ?" for key in updates)
    values = list(updates.values()) + [company_id, conversation_uuid]
    conn = db.get_connection()
    try:
        conn.execute(
            f"""
            UPDATE monitoria_conversations
            SET {assignments}
            WHERE company_id = ? AND conversation_uuid = ?
            """,
            values,
        )
        conn.commit()
        return get_conversation_by_uuid(company_id, conversation_uuid)
    finally:
        conn.close()


def get_conversation_by_uuid(company_id: int, conversation_uuid: str) -> Optional[dict[str, Any]]:
    conn = db.get_connection()
    try:
        row = conn.execute(
            """
            SELECT * FROM monitoria_conversations
            WHERE company_id = ? AND conversation_uuid = ?
            """,
            (company_id, conversation_uuid),
        ).fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


def get_conversation_by_id(company_id: int, conversation_id: int) -> Optional[dict[str, Any]]:
    conn = db.get_connection()
    try:
        row = conn.execute(
            """
            SELECT * FROM monitoria_conversations
            WHERE company_id = ? AND id = ?
            """,
            (company_id, conversation_id),
        ).fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


def _scope_sql_clause(scope: MonitoriaScope, alias: str = "c") -> tuple[str, list[Any]]:
    if scope.is_full_access:
        return "1=1", []
    if scope.area_mode is not None:
        if not scope.roles:
            return "0=1", []
        clauses, params = [f"{alias}.area != ''"], []
        if scope.area_mode == "selected":
            if not scope.allowed_areas:
                return "0=1", []
            clauses.append(f"{alias}.area IN ({','.join('?' for _ in scope.allowed_areas)})")
            params.extend(sorted(scope.allowed_areas))
        if scope.operator_only:
            clauses.append(f"{alias}.operador_user_id = ?")
            params.append(scope.user_id)
        return '(' + ' AND '.join(clauses) + ')', params
    clauses: list[str] = []
    params: list[Any] = []
    if scope.operator_only:
        clauses.append(f"{alias}.operador_user_id = ?")
        params.append(scope.user_id)
    if scope.team_ids:
        placeholders = ", ".join("?" for _ in scope.team_ids)
        clauses.append(f"{alias}.team_id IN ({placeholders})")
        params.extend(sorted(scope.team_ids))
    if scope.central_ids:
        placeholders = ", ".join("?" for _ in scope.central_ids)
        clauses.append(f"{alias}.central_id IN ({placeholders})")
        params.extend(sorted(scope.central_ids))
    if scope.assigned_analyst_only:
        clauses.append(f"{alias}.analista_user_id = ?")
        params.append(scope.user_id)
    if not clauses:
        return "0=1", []
    return "(" + " OR ".join(clauses) + ")", params


def list_conversations(
    company_id: int,
    scope: MonitoriaScope,
    *,
    area: Optional[str] = None,
    categoria: Optional[str] = None,
    central_id: Optional[int] = None,
    team_id: Optional[int] = None,
    cliente: Optional[str] = None,
    operador_user_id: Optional[int] = None,
    analista_user_id: Optional[int] = None,
    tipo: Optional[str] = None,
    pillar_id: Optional[int] = None,
    pillar_family_id: Optional[int] = None,
    status: Optional[str] = None,
    created_from: Optional[str] = None,
    created_to: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
) -> dict[str, Any]:
    scope_sql, scope_params = _scope_sql_clause(scope)
    sql = f"FROM monitoria_conversations c WHERE c.company_id = ? AND {scope_sql}"
    params: list[Any] = [company_id, *scope_params]
    for key, value in (("area", area), ("categoria", categoria)):
        if value is not None:
            sql += f" AND c.{key} = ?"
            params.append(value)
    if central_id is not None:
        sql += " AND c.central_id = ?"
        params.append(central_id)
    if team_id is not None:
        sql += " AND c.team_id = ?"
        params.append(team_id)
    if cliente:
        sql += " AND LOWER(c.cliente) LIKE ?"
        params.append(f"%{cliente.strip().lower()}%")
    if operador_user_id is not None:
        sql += " AND c.operador_user_id = ?"
        params.append(operador_user_id)
    if analista_user_id is not None:
        sql += " AND c.analista_user_id = ?"
        params.append(analista_user_id)
    if tipo:
        sql += " AND c.tipo = ?"
        params.append(tipo)
    if pillar_family_id is not None:
        sql += " AND EXISTS (SELECT 1 FROM monitoria_pillar_scores ps JOIN monitoria_pillars p ON p.id = ps.pillar_id WHERE ps.conversation_id = c.id AND p.company_id = c.company_id AND p.family_id = ?)"
        params.append(pillar_family_id)
    if pillar_id is not None:
        sql += " AND EXISTS (SELECT 1 FROM monitoria_pillar_scores ps WHERE ps.conversation_id = c.id AND ps.pillar_id = ?)"
        params.append(pillar_id)
    if status:
        sql += " AND c.status = ?"
        params.append(status)
    if created_from:
        sql += " AND c.created_at >= ?"
        params.append(created_from)
    if created_to:
        sql += " AND c.created_at <= ?"
        params.append(created_to)

    safe_limit = max(1, min(int(limit or 20), 200))
    safe_offset = max(0, int(offset or 0))
    conn = db.get_connection()
    try:
        total = int(conn.execute(f"SELECT COUNT(*) AS total {sql}", params).fetchone()["total"])
        rows = conn.execute(
            f"""
            SELECT c.*,
              (SELECT SUM(ps.score * ps.weight) / SUM(ps.weight) FROM monitoria_pillar_scores ps WHERE ps.conversation_id = c.id) AS score,
              (SELECT name FROM monitoria_centrals WHERE id = c.central_id) AS central_name,
              (SELECT full_name FROM users WHERE id = c.operador_user_id) AS operador_name,
              (SELECT full_name FROM users WHERE id = c.analista_user_id) AS analista_name
            {sql}
            ORDER BY c.created_at DESC, c.id DESC
            LIMIT ? OFFSET ?
            """,
            [*params, safe_limit, safe_offset],
        ).fetchall()
        items = [_row_to_dict(row) for row in rows]
        for item in items:
            item.pop("audio_path", None)
            item["is_mock"] = item["provider"] == "mock"
        summary = dict(conn.execute(f"""
            SELECT COUNT(*) AS total,
              COALESCE(SUM(c.status = 'completed'), 0) AS completed,
              COALESCE(SUM(c.status = 'failed'), 0) AS failed,
              AVG((SELECT SUM(ps.score * ps.weight) / SUM(ps.weight)
                   FROM monitoria_pillar_scores ps WHERE ps.conversation_id = c.id)) AS average_score
            {sql}
        """, params).fetchone())
        return {"total": total, "items": items, "limit": safe_limit, "offset": safe_offset, "summary": summary}
    finally:
        conn.close()


def replace_turns(conversation_id: int, turns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    conn = db.get_connection()
    try:
        with conn:
            conn.execute("DELETE FROM monitoria_turns WHERE conversation_id = ?", (conversation_id,))
            for index, turn in enumerate(turns):
                speaker = str(turn.get("speaker") or "").strip().lower()
                if speaker not in MONITORIA_SPEAKERS:
                    raise ValueError("speaker inválido")
                conn.execute(
                    """
                    INSERT INTO monitoria_turns
                    (conversation_id, turn_index, speaker, text, t_start, t_end)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        conversation_id,
                        int(turn.get("turn_index", index)),
                        speaker,
                        str(turn.get("text") or ""),
                        turn.get("t_start"),
                        turn.get("t_end"),
                    ),
                )
        return list_turns(conversation_id)
    finally:
        conn.close()


def list_turns(conversation_id: int) -> list[dict[str, Any]]:
    conn = db.get_connection()
    try:
        rows = conn.execute(
            """
            SELECT * FROM monitoria_turns
            WHERE conversation_id = ?
            ORDER BY turn_index ASC, id ASC
            """,
            (conversation_id,),
        ).fetchall()
        return [_row_to_dict(row) for row in rows]  # type: ignore[misc]
    finally:
        conn.close()


def replace_scores(
    conversation_id: int,
    pillar_scores: list[dict[str, Any]],
    turn_scores: list[dict[str, Any]],
) -> None:
    timestamp = _now()
    conn = db.get_connection()
    try:
        with conn:
            conn.execute("DELETE FROM monitoria_turn_scores WHERE conversation_id = ?", (conversation_id,))
            conn.execute("DELETE FROM monitoria_pillar_scores WHERE conversation_id = ?", (conversation_id,))
            for item in pillar_scores:
                conn.execute(
                    """
                    INSERT INTO monitoria_pillar_scores
                    (conversation_id, pillar_id, pillar_name, pillar_version, score, rationale, created_at, weight)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        conversation_id,
                        int(item["pillar_id"]),
                        str(item["pillar_name"]),
                        int(item.get("pillar_version") or 1),
                        float(item["score"]),
                        str(item.get("rationale") or ""),
                        timestamp,
                        float(item.get("weight", 1.0)),
                    ),
                )
            for item in turn_scores:
                conn.execute(
                    """
                    INSERT INTO monitoria_turn_scores
                    (conversation_id, turn_id, pillar_id, pillar_name, score, evidence, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        conversation_id,
                        int(item["turn_id"]),
                        int(item["pillar_id"]),
                        str(item["pillar_name"]),
                        float(item["score"]),
                        str(item.get("evidence") or ""),
                        timestamp,
                    ),
                )
    finally:
        conn.close()


def list_pillar_scores(conversation_id: int) -> list[dict[str, Any]]:
    conn = db.get_connection()
    try:
        rows = conn.execute(
            """
            SELECT * FROM monitoria_pillar_scores
            WHERE conversation_id = ?
            ORDER BY pillar_name COLLATE NOCASE
            """,
            (conversation_id,),
        ).fetchall()
        return [_row_to_dict(row) for row in rows]  # type: ignore[misc]
    finally:
        conn.close()


def list_turn_scores(conversation_id: int) -> list[dict[str, Any]]:
    conn = db.get_connection()
    try:
        rows = conn.execute(
            """
            SELECT ts.*, t.turn_index, t.speaker, t.t_start, t.t_end
            FROM monitoria_turn_scores ts
            JOIN monitoria_turns t ON t.id = ts.turn_id
            WHERE ts.conversation_id = ?
            ORDER BY t.turn_index ASC, ts.pillar_name COLLATE NOCASE
            """,
            (conversation_id,),
        ).fetchall()
        return [_row_to_dict(row) for row in rows]  # type: ignore[misc]
    finally:
        conn.close()


def create_job(company_id: int, job_id: str, conversation_uuid: str, status: str = "queued", *, durable: bool = False, connection=None) -> dict[str, Any]:
    timestamp = _now()
    conn = connection or db.get_connection()
    try:
        conn.execute(
            """
            INSERT INTO monitoria_jobs
            (company_id, job_id, conversation_uuid, status, error_message, created_at, updated_at, lease_until, durable)
            VALUES (?, ?, ?, ?, '', ?, ?, ?, ?)
            """,
            (company_id, job_id, conversation_uuid, status, timestamp, timestamp, None if durable else time.time() + 60, int(durable)),
        )
        if connection is None:
            conn.commit()
        return dict(conn.execute("SELECT * FROM monitoria_jobs WHERE job_id = ?", (job_id,)).fetchone())
    finally:
        if connection is None:
            conn.close()


def update_job(company_id: int, job_id: str, *, status: Optional[str] = None, error_message: Optional[str] = None) -> Optional[dict[str, Any]]:
    current = get_job(company_id, job_id)
    if not current:
        return None
    conn = db.get_connection()
    try:
        conn.execute(
            """
            UPDATE monitoria_jobs
            SET status = ?, error_message = ?, updated_at = ?
            WHERE company_id = ? AND job_id = ?
            """,
            (
                status if status is not None else current["status"],
                current["error_message"] if error_message is None else str(error_message),
                _now(),
                company_id,
                job_id,
            ),
        )
        conn.commit()
        return get_job(company_id, job_id)
    finally:
        conn.close()


def get_job(company_id: int, job_id: str) -> Optional[dict[str, Any]]:
    conn = db.get_connection()
    try:
        row = conn.execute(
            """
            SELECT * FROM monitoria_jobs
            WHERE company_id = ? AND job_id = ?
            """,
            (company_id, job_id),
        ).fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


def list_jobs(company_id: int, *, status: Optional[str] = None, limit: int = 50) -> list[dict[str, Any]]:
    conn = db.get_connection()
    try:
        sql = "SELECT * FROM monitoria_jobs WHERE company_id = ?"
        params: list[Any] = [company_id]
        if status:
            sql += " AND status = ?"
            params.append(status)
        sql += " ORDER BY created_at DESC, id DESC LIMIT ?"
        params.append(max(1, min(int(limit or 50), 200)))
        return [_row_to_dict(row) for row in conn.execute(sql, params).fetchall()]  # type: ignore[misc]
    finally:
        conn.close()


def conversation_detail_payload(conversation: dict[str, Any]) -> dict[str, Any]:
    conversation_id = int(conversation["id"])
    turns = list_turns(conversation_id)
    pillar_scores = list_pillar_scores(conversation_id)
    for score in pillar_scores:
        score["snapshot_available"] = score.get("prompt") is not None
    turn_scores = list_turn_scores(conversation_id)
    telemetry = []
    for score in turn_scores:
        telemetry.append(
            {
                "turn_id": score["turn_id"],
                "turn_index": score["turn_index"],
                "t_start": score["t_start"],
                "t_end": score["t_end"],
                "speaker": score["speaker"],
                "pillar_id": score["pillar_id"],
                "pillar_name": score["pillar_name"],
                "score": score["score"],
                "evidence": score["evidence"],
            }
        )
    public = {key: value for key, value in conversation.items() if key != "audio_path"}
    weights = sum(p["weight"] for p in pillar_scores)
    return {
        **public,
        "is_mock": conversation.get("provider") == "mock",
        "evaluation_config": json.loads(conversation["evaluation_config"]) if conversation.get("evaluation_config") else None,
        "score": round(sum(p["score"] * p["weight"] for p in pillar_scores) / weights, 1) if weights else None,
        "turns": turns,
        "pillar_scores": pillar_scores,
        "turn_scores": turn_scores,
        "telemetry": telemetry,
        "metadata": {
            "ticket_id": conversation.get("ticket_id"),
            "cliente": conversation.get("cliente"),
            "central_id": conversation.get("central_id"),
            "team_id": conversation.get("team_id"),
            "operador_user_id": conversation.get("operador_user_id"),
            "analista_user_id": conversation.get("analista_user_id"),
        },
    }


def dump_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


# Persistent processing ownership. All state transitions serialize in SQLite.
def claim_job(company_id: int, job_id: str, conversation_uuid: str, owner: str, lease_seconds: float = 60) -> bool:
    conn = db.get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        now = time.time()
        row = conn.execute("""UPDATE monitoria_jobs SET status = 'processing', lease_owner = ?,
            lease_until = ?, updated_at = ? WHERE company_id = ? AND job_id = ? AND conversation_uuid = ?
            AND status = 'queued' AND (lease_until > ? OR (durable = 1 AND lease_until IS NULL))
            AND EXISTS (SELECT 1 FROM monitoria_conversations c WHERE c.company_id = ?
                        AND c.conversation_uuid = ? AND c.status = 'queued')""",
            (owner, now + lease_seconds, _now(), company_id, job_id, conversation_uuid, now, company_id, conversation_uuid))
        if row.rowcount != 1:
            return False
        conn.execute("UPDATE monitoria_conversations SET status = 'processing', error_message = '', updated_at = ? WHERE company_id = ? AND conversation_uuid = ?",
            (_now(), company_id, conversation_uuid))
        conn.commit()
        return True
    finally:
        conn.close()


def renew_job_lease(company_id: int, job_id: str, owner: str, lease_seconds: float = 60) -> bool:
    conn = db.get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        now = time.time()
        row = conn.execute("""UPDATE monitoria_jobs SET lease_until = ?, updated_at = ?
            WHERE company_id = ? AND job_id = ? AND status = 'processing' AND lease_owner = ? AND lease_until > ?""",
            (now + lease_seconds, _now(), company_id, job_id, owner, now))
        conn.commit()
        return row.rowcount == 1
    finally:
        conn.close()


def _owned_job(conn, company_id, job_id, owner):
    return conn.execute("""SELECT j.*, c.id AS conversation_id FROM monitoria_jobs j
        JOIN monitoria_conversations c ON c.company_id = j.company_id AND c.conversation_uuid = j.conversation_uuid
        WHERE j.company_id = ? AND j.job_id = ? AND j.status = 'processing'
          AND j.lease_owner = ? AND j.lease_until > ? AND c.status = 'processing'""",
        (company_id, job_id, owner, time.time())).fetchone()


def complete_job(company_id, job_id, owner, turns, pillar_scores, turn_scores, evaluation_config) -> bool:
    """Commit a fully validated result and its status atomically, fenced by ownership."""
    conn = db.get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        job = _owned_job(conn, company_id, job_id, owner)
        if not job:
            return False
        cid = job["conversation_id"]
        # Child-first deletion works even in databases created without foreign_keys enabled.
        for table in ("monitoria_turn_scores", "monitoria_pillar_scores", "monitoria_turns"):
            conn.execute(f"DELETE FROM {table} WHERE conversation_id = ?", (cid,))
        ids = {}
        for turn in turns:
            row = conn.execute("""INSERT INTO monitoria_turns (conversation_id, turn_index, speaker, text, t_start, t_end)
                VALUES (?, ?, ?, ?, ?, ?)""", (cid, turn.turn_index, turn.speaker, turn.text, turn.t_start, turn.t_end))
            ids[turn.turn_index] = row.lastrowid
        for score in pillar_scores:
            conn.execute("""INSERT INTO monitoria_pillar_scores
                (conversation_id, pillar_id, pillar_name, pillar_version, score, rationale, created_at, weight, prompt, description)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (cid, score["pillar_id"], score["pillar_name"], score["pillar_version"], score["score"], score["rationale"],
                 _now(), score["weight"], score["prompt"], score["description"]))
        for score in turn_scores:
            conn.execute("""INSERT INTO monitoria_turn_scores
                (conversation_id, turn_id, pillar_id, pillar_name, score, evidence, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (cid, ids[score["turn_index"]], score["pillar_id"], score["pillar_name"], score["score"], score["evidence"], _now()))
        conn.execute("""UPDATE monitoria_conversations SET status = 'completed', error_message = '',
            evaluation_config = ?, updated_at = ? WHERE id = ?""", (dump_json(evaluation_config), _now(), cid))
        conn.execute("UPDATE monitoria_jobs SET status = 'completed', error_message = '', lease_owner = NULL, lease_until = NULL, updated_at = ? WHERE id = ?",
            (_now(), job["id"]))
        conn.commit()
        return True
    finally:
        conn.close()


def fail_owned_job(company_id, job_id, owner, message) -> bool:
    conn = db.get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        job = _owned_job(conn, company_id, job_id, owner)
        if not job:
            return False
        conn.execute("UPDATE monitoria_jobs SET status = 'failed', error_message = ?, lease_owner = NULL, lease_until = NULL, updated_at = ? WHERE id = ?",
            (message, _now(), job["id"]))
        conn.execute("UPDATE monitoria_conversations SET status = 'failed', error_message = ?, updated_at = ? WHERE id = ?",
            (message, _now(), job["conversation_id"]))
        conn.commit()
        return True
    finally:
        conn.close()


def expire_job_leases(limit: int = 200) -> int:
    conn = db.get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        rows = conn.execute("""SELECT id, company_id, conversation_uuid FROM monitoria_jobs
            WHERE status IN ('queued', 'processing') AND lease_until <= ? ORDER BY lease_until LIMIT ?""",
            (time.time(), limit)).fetchall()
        message = "Processamento interrompido: prazo de execução sem renovação."
        for row in rows:
            conn.execute("UPDATE monitoria_jobs SET status = 'failed', error_message = ?, lease_owner = NULL, lease_until = NULL, updated_at = ? WHERE id = ?",
                (message, _now(), row["id"]))
            conn.execute("""UPDATE monitoria_conversations SET status = 'failed', error_message = ?, updated_at = ?
                WHERE company_id = ? AND conversation_uuid = ? AND status IN ('queued', 'processing')""",
                (message, _now(), row["company_id"], row["conversation_uuid"]))
        conn.commit()
        return len(rows)
    finally:
        conn.close()


# Batch intake is atomic: workers can only see a fully committed batch.
def find_batch_request(company_id, created_by, request_key):
    conn = db.get_connection()
    try:
        row = conn.execute("SELECT * FROM monitoria_batches WHERE company_id = ? AND created_by = ? AND request_key = ?",
            (company_id, created_by, request_key)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def persist_batch(company_id, created_by, batch_id, request_key, fingerprint, items, provider):
    conn = db.get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("INSERT INTO monitoria_batches VALUES (?, ?, ?, ?, ?, ?)",
            (batch_id, company_id, created_by, request_key, fingerprint, _now()))
        for item in items:
            if not item.get('error_message'):
                create_conversation(company_id, item['conversation_uuid'], **item['metadata'],
                    audio_path=item['audio_path'], audio_filename=item['filename'], provider=provider, connection=conn)
                create_job(company_id, item['job_id'], item['conversation_uuid'], durable=True, connection=conn)
            conn.execute("""INSERT INTO monitoria_batch_items
                (batch_id, item_index, filename, metadata, job_id, conversation_uuid, error_message)
                VALUES (?, ?, ?, ?, ?, ?, ?)""", (batch_id, item['index'], item['filename'], dump_json(item['metadata']),
                    item.get('job_id'), item.get('conversation_uuid'), item.get('error_message', '')))
        conn.commit()
    finally:
        conn.close()


def pending_batch_jobs(limit=2):
    conn = db.get_connection()
    try:
        return [dict(row) for row in conn.execute("""SELECT company_id, job_id, conversation_uuid FROM monitoria_jobs
            WHERE durable = 1 AND status = 'queued' ORDER BY id LIMIT ?""", (limit,))]
    finally:
        conn.close()


def batch_payload(company_id, batch_id, scope):
    conn = db.get_connection()
    try:
        batch = conn.execute("SELECT * FROM monitoria_batches WHERE company_id = ? AND batch_id = ?",
            (company_id, batch_id)).fetchone()
        if not batch or not (scope.is_full_access or batch['created_by'] == scope.user_id):
            return None
        scope_sql, scope_params = _scope_sql_clause(scope)
        rows = conn.execute(f"""SELECT i.*, j.status, j.error_message AS job_error, c.provider, c.ticket_id, c.cliente
            FROM monitoria_batch_items i
            JOIN monitoria_batches b ON b.batch_id = i.batch_id
            LEFT JOIN monitoria_conversations c ON c.conversation_uuid = i.conversation_uuid AND c.company_id = b.company_id
            LEFT JOIN monitoria_jobs j ON j.job_id = i.job_id AND j.company_id = b.company_id
            WHERE b.company_id = ? AND b.batch_id = ? AND (i.job_id IS NULL OR ({scope_sql}))
            ORDER BY i.item_index""", [company_id, batch_id, *scope_params]).fetchall()
        if not rows:
            return None
        items = []
        counts = dict.fromkeys(['queued', 'processing', 'completed', 'failed', 'rejected'], 0)
        for row in rows:
            status = row['status'] or 'rejected'
            counts[status] += 1
            metadata = json.loads(row['metadata'])
            items.append({'index': row['item_index'], 'filename': row['filename'], 'status': status,
                'ticket_id': row['ticket_id'] if row['job_id'] else metadata.get('ticket_id', ''),
                'cliente': row['cliente'] if row['job_id'] else metadata.get('cliente', ''),
                'conversation_uuid': row['conversation_uuid'], 'job_id': row['job_id'],
                'is_mock': row['provider'] == 'mock' if row['job_id'] else None,
                'error_message': row['job_error'] or row['error_message']})
        status = ('processing' if counts['processing'] else 'queued') if counts['queued'] or counts['processing'] else (
            'completed_with_errors' if counts['failed'] or counts['rejected'] else 'completed')
        return {'batch_id': batch_id, 'created_at': batch['created_at'], 'status': status,
            'total': len(items), 'counts': counts, 'items': items}
    finally:
        conn.close()


def list_batches(company_id, scope, limit=20):
    conn = db.get_connection()
    try:
        # Scope is applied before limiting: inaccessible batches cannot hide visible ones.
        scope_sql, scope_params = _scope_sql_clause(scope)
        rows = conn.execute(f"""SELECT b.batch_id FROM monitoria_batches b
            WHERE b.company_id = ? AND (? OR b.created_by = ?)
            AND EXISTS (SELECT 1 FROM monitoria_batch_items i
                LEFT JOIN monitoria_conversations c ON c.conversation_uuid = i.conversation_uuid AND c.company_id = b.company_id
                WHERE i.batch_id = b.batch_id AND (i.job_id IS NULL OR ({scope_sql})))
            ORDER BY b.created_at DESC, b.rowid DESC LIMIT ?""",
            [company_id, int(scope.is_full_access), scope.user_id, *scope_params, limit]).fetchall()
    finally:
        conn.close()
    return [payload for row in rows if (payload := batch_payload(company_id, row['batch_id'], scope))]
