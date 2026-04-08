from __future__ import annotations

import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from . import db, services
from .config import (
    ACCESS_CONTROL_ENABLED,
    ALLOW_PUBLIC_COMPANY_CREATE,
    API_BASE_URL,
    DEFAULT_COMPANY_DESCRIPTION,
    DEFAULT_COMPANY_NAME,
    SUPER_ADMIN_USER,
)
from .security import TokenData, create_access_token, current_user, hash_password, optional_current_user, require_company_access, require_role, verify_password


router = APIRouter()


def _slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "empresa"


class CompanyCreatePayload(BaseModel):
    company_name: str
    company_description: str = ""
    admin_name: str
    admin_email: str
    admin_password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserSessionResponse(BaseModel):
    user_id: int
    full_name: str
    email: str
    role: str
    roles: list[str] = []
    require_password_change: bool = False
    company_id: int
    company_name: str
    company_description: str = ""


class LoginPayload(BaseModel):
    email: str
    password: str
    company_id: int


class ChangePasswordPayload(BaseModel):
    new_password: str


class CreateUserPayload(BaseModel):
    full_name: str
    email: str
    password: Optional[str] = None
    role: str
    profile_ids: list[int] = []


class UpdateUserAccessPayload(BaseModel):
    roles: list[str] = []
    full_name: Optional[str] = None
    password: Optional[str] = None


class UpdateUserAreaScopePayload(BaseModel):
    mode: str = "all"
    areas: list[str] = []
    profile_ids: list[int] = []


class AreaRestrictionProfilePayload(BaseModel):
    name: str
    areas: list[str] = []
    description: str = ""


def _is_scoped_access_allowed(company_id: int, user: TokenData) -> None:
    if not ACCESS_CONTROL_ENABLED:
        return
    if user.company_id != company_id:
        raise HTTPException(status_code=403, detail="Token fora do contexto da empresa")


def _must_force_password_change(email: str) -> bool:
    normalized_email = str(email or "").strip().lower()
    normalized_super = str(SUPER_ADMIN_USER or "").strip().lower()
    return bool(normalized_email) and normalized_email != normalized_super


@router.post("/empresas", status_code=201, tags=["empresas"])
def create_company(payload: CompanyCreatePayload, user: TokenData = Depends(optional_current_user)):
    if not ALLOW_PUBLIC_COMPANY_CREATE:
        if not ACCESS_CONTROL_ENABLED:
            raise HTTPException(status_code=403, detail="Criação pública de empresa desabilitada.")
        current_roles = db.get_user_roles_in_company(user.user_id, user.company_id)
        if "admin" not in current_roles:
            raise HTTPException(status_code=403, detail="Apenas administradores podem criar empresas.")
    company_slug = _slugify(payload.company_name)
    company_id = db.create_company(payload.company_name, company_slug, payload.company_description)
    password_hash = hash_password(payload.admin_password)
    user_id = db.create_user(
        payload.admin_name,
        payload.admin_email,
        password_hash,
        require_password_change=_must_force_password_change(payload.admin_email),
    )
    db.assign_role_to_user(user_id, company_id, "admin")
    return {"empresa_id": company_id, "slug": company_slug, "admin_id": user_id}


@router.get("/auth/me", response_model=UserSessionResponse, tags=["auth"])
def get_current_user(user: TokenData = Depends(current_user)):
    if not ACCESS_CONTROL_ENABLED:
        return {
            "user_id": user.user_id,
            "full_name": "Anônimo",
            "email": user.email,
            "role": user.role,
            "roles": user.roles,
            "require_password_change": False,
            "company_id": user.company_id,
            "company_name": DEFAULT_COMPANY_NAME,
            "company_description": DEFAULT_COMPANY_DESCRIPTION,
        }

    row = db.get_user_by_email(user.email)
    if not row:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    company = db.get_company(user.company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Empresa não encontrada")

    roles = db.get_user_roles_in_company(user.user_id, user.company_id)
    role = db.resolve_effective_role(roles)
    if not role or not roles:
        raise HTTPException(status_code=403, detail="Usuário não possui mais acesso ativo a esta empresa")

    return {
        "user_id": user.user_id,
        "full_name": row["full_name"],
        "email": row["email"],
        "role": role,
        "roles": roles,
        "require_password_change": bool(row["require_password_change"]),
        "company_id": user.company_id,
        "company_name": company["name"],
        "company_description": company["description"],
    }


@router.post("/auth/login", response_model=LoginResponse, tags=["auth"])
def login(payload: LoginPayload):
    user = db.get_user_by_email(payload.email)
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciais inválidas")

    roles = db.get_user_roles_in_company(user["id"], payload.company_id)
    role = db.resolve_effective_role(roles)
    if role is None:
        raise HTTPException(status_code=403, detail="Usuário não associado a esta empresa")

    token = create_access_token(
        subject=user["id"],
        company_id=payload.company_id,
        role=role,
        email=user["email"],
        roles=roles,
    )
    return {"access_token": token, "token_type": "bearer"}


@router.post("/auth/change-password", tags=["auth"])
def change_password(payload: ChangePasswordPayload, user: TokenData = Depends(current_user)):
    if not ACCESS_CONTROL_ENABLED:
        raise HTTPException(status_code=400, detail="Troca de senha indisponível sem controle de acesso.")
    row = db.get_user_by_id(user.user_id)
    if not row:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    new_password = str(payload.new_password or "").strip()
    if len(new_password) < 8:
        raise HTTPException(status_code=422, detail="A nova senha deve ter pelo menos 8 caracteres.")
    db.update_user_account(
        user.user_id,
        password_hash=hash_password(new_password),
        require_password_change=False,
    )
    return {"status": "ok"}


@router.get("/empresas/{company_id}/usuarios", tags=["usuarios"])
def list_users(company_id: int, user: TokenData = Depends(require_role("admin"))):
    _is_scoped_access_allowed(company_id, user)
    return db.list_users_in_company(company_id)


@router.get("/empresas/{company_id}/usuarios/auditoria", tags=["usuarios"])
def list_user_access_audit(
    company_id: int,
    limit: int = 20,
    offset: int = 0,
    user: TokenData = Depends(require_role("admin")),
):
    _is_scoped_access_allowed(company_id, user)
    return db.list_access_audit_events(company_id, limit=limit, offset=offset)


@router.get("/empresas/{company_id}/usuarios/{target_user_id}/areas-acesso", tags=["usuarios"])
def get_user_area_scope(
    company_id: int,
    target_user_id: int,
    user: TokenData = Depends(require_role("admin")),
):
    _is_scoped_access_allowed(company_id, user)
    target = db.get_user_by_id(target_user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    available_areas = [str(item).strip() for item in db.list_taxonomies(company_id, "area") if str(item).strip()]
    if services.DEFAULT_AREA not in available_areas:
        available_areas.append(services.DEFAULT_AREA)
    scope_bundle = db.get_effective_user_area_scope(target_user_id, company_id)
    return {
        "usuario_id": target_user_id,
        "empresa_id": company_id,
        "scope": scope_bundle.get("default_scope"),
        "effective_scope": scope_bundle.get("effective_scope"),
        "profiles": scope_bundle.get("profiles", []),
        "assigned_profile_ids": scope_bundle.get("assigned_profile_ids", []),
        "available_areas": available_areas,
    }


@router.put("/empresas/{company_id}/usuarios/{target_user_id}/areas-acesso", tags=["usuarios"])
def update_user_area_scope(
    company_id: int,
    target_user_id: int,
    payload: UpdateUserAreaScopePayload,
    user: TokenData = Depends(require_role("admin")),
):
    _is_scoped_access_allowed(company_id, user)
    target = db.get_user_by_id(target_user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    available_areas = {str(item).strip() for item in db.list_taxonomies(company_id, "area")}
    cleaned_areas: list[str] = []
    for area in payload.areas:
        cleaned_area = str(area or "").strip()
        if cleaned_area == services.DEFAULT_AREA or cleaned_area in available_areas:
            if cleaned_area not in cleaned_areas:
                cleaned_areas.append(cleaned_area)
            continue
        raise HTTPException(status_code=422, detail=f"Área inválida para restrição: {cleaned_area}")

    scope = db.set_user_area_scope(target_user_id, company_id, payload.mode, cleaned_areas)
    assigned_profile_ids = db.set_user_assigned_area_profiles(target_user_id, company_id, payload.profile_ids)
    effective_bundle = db.get_effective_user_area_scope(target_user_id, company_id)
    db.record_access_audit_event(
        company_id=company_id,
        actor_user_id=user.user_id,
        target_user_id=target_user_id,
        action="scope",
        roles=db.get_user_roles_in_company(target_user_id, company_id),
        note=(
            f"Perfil padrão atualizado para modo={scope['mode']} com áreas: {', '.join(scope['areas']) or 'nenhuma'}. "
            f"Perfis atribuídos: {', '.join(str(item) for item in assigned_profile_ids) or 'nenhum'}."
        ),
    )
    return {
        "usuario_id": target_user_id,
        "empresa_id": company_id,
        "scope": scope,
        "effective_scope": effective_bundle.get("effective_scope"),
        "assigned_profile_ids": assigned_profile_ids,
    }


@router.get("/empresas/{company_id}/perfis-restricao-areas", tags=["usuarios"])
def list_area_restriction_profiles(
    company_id: int,
    user: TokenData = Depends(require_role("admin")),
):
    _is_scoped_access_allowed(company_id, user)
    return {"empresa_id": company_id, "items": db.list_area_restriction_profiles(company_id)}


@router.post("/empresas/{company_id}/perfis-restricao-areas", tags=["usuarios"])
def create_area_restriction_profile(
    company_id: int,
    payload: AreaRestrictionProfilePayload,
    user: TokenData = Depends(require_role("admin")),
):
    _is_scoped_access_allowed(company_id, user)
    available_areas = {str(item).strip() for item in db.list_taxonomies(company_id, "area")}
    cleaned_areas: list[str] = []
    for area in payload.areas:
        cleaned_area = str(area or "").strip()
        if cleaned_area == services.DEFAULT_AREA or cleaned_area in available_areas:
            if cleaned_area not in cleaned_areas:
                cleaned_areas.append(cleaned_area)
            continue
        raise HTTPException(status_code=422, detail=f"Área inválida para o perfil: {cleaned_area}")

    try:
        created = db.create_area_restriction_profile(
            company_id=company_id,
            name=payload.name,
            areas=cleaned_areas,
            description=payload.description,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    db.record_access_audit_event(
        company_id=company_id,
        actor_user_id=user.user_id,
        target_user_id=user.user_id,
        action="scope-profile",
        roles=db.get_user_roles_in_company(user.user_id, company_id),
        note=f"Perfil de restrição criado: {created['name']} ({', '.join(created['areas'])}).",
    )
    return {"empresa_id": company_id, "perfil": created}


@router.delete("/empresas/{company_id}/perfis-restricao-areas/{profile_id}", tags=["usuarios"])
def delete_area_restriction_profile(
    company_id: int,
    profile_id: int,
    user: TokenData = Depends(require_role("admin")),
):
    _is_scoped_access_allowed(company_id, user)
    try:
        db.delete_area_restriction_profile(company_id, profile_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    db.record_access_audit_event(
        company_id=company_id,
        actor_user_id=user.user_id,
        target_user_id=user.user_id,
        action="scope-profile",
        roles=db.get_user_roles_in_company(user.user_id, company_id),
        note=f"Perfil de restrição removido: {profile_id}.",
    )
    return {"empresa_id": company_id, "profile_id": profile_id, "status": "removido"}


@router.post("/empresas/{company_id}/usuarios", tags=["usuarios"])
def create_user(
    company_id: int,
    payload: CreateUserPayload,
    user: TokenData = Depends(require_role("admin")),
):
    _is_scoped_access_allowed(company_id, user)
    normalized_role = db.normalize_access_role(payload.role)
    if normalized_role not in {"admin", "editor", "aprovador"}:
        raise HTTPException(status_code=422, detail="role inválido")

    existing = db.get_user_by_email(payload.email)
    if existing:
        user_id = existing["id"]
    else:
        if not payload.password:
            raise HTTPException(status_code=422, detail="password é obrigatória para novo usuário")
        user_id = db.create_user(
            payload.full_name,
            payload.email,
            hash_password(payload.password),
            require_password_change=_must_force_password_change(payload.email),
        )

    db.assign_role_to_user(user_id, company_id, normalized_role)
    assigned_profile_ids = db.set_user_assigned_area_profiles(user_id, company_id, payload.profile_ids)
    db.record_access_audit_event(
        company_id=company_id,
        actor_user_id=user.user_id,
        target_user_id=user_id,
        action="grant",
        roles=db.get_user_roles_in_company(user_id, company_id),
        note=(
            "Usuário criado ou vinculado pela administração."
            if not assigned_profile_ids
            else f"Usuário criado ou vinculado pela administração. Perfis de restrição: {', '.join(str(item) for item in assigned_profile_ids)}."
        ),
    )
    return {
        "message": "usuário criado/vinculado com sucesso",
        "usuario_id": user_id,
        "empresa_id": company_id,
        "role": normalized_role,
        "profile_ids": assigned_profile_ids,
    }


@router.put("/empresas/{company_id}/usuarios/{target_user_id}/acessos", tags=["usuarios"])
def update_user_access(
    company_id: int,
    target_user_id: int,
    payload: UpdateUserAccessPayload,
    user: TokenData = Depends(require_role("admin")),
):
    _is_scoped_access_allowed(company_id, user)
    target = db.get_user_by_id(target_user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    next_full_name = None
    if payload.full_name is not None:
        cleaned_name = payload.full_name.strip()
        if not cleaned_name:
            raise HTTPException(status_code=422, detail="full_name inválido")
        next_full_name = cleaned_name

    normalized_roles: list[str] = []
    for role in payload.roles:
        normalized_role = db.normalize_access_role(role)
        if normalized_role not in {"admin", "editor", "aprovador"}:
            raise HTTPException(status_code=422, detail="role inválido")
        if normalized_role not in normalized_roles:
            normalized_roles.append(normalized_role)

    if "admin" not in normalized_roles and "admin" in db.get_user_roles_in_company(target_user_id, company_id):
        if db.count_admins_in_company(company_id, exclude_user_id=target_user_id) == 0:
            raise HTTPException(status_code=422, detail="A empresa precisa manter ao menos um administrador ativo.")

    db.update_user_account(
        target_user_id,
        full_name=next_full_name,
        password_hash=hash_password(payload.password) if payload.password else None,
        require_password_change=_must_force_password_change(target["email"]) if payload.password else None,
    )
    roles = db.set_user_roles_in_company(target_user_id, company_id, normalized_roles)
    note_parts: list[str] = []
    if next_full_name is not None and next_full_name != target["full_name"]:
        note_parts.append("Nome atualizado")
    if payload.password:
        note_parts.append("Senha redefinida")
    db.record_access_audit_event(
        company_id=company_id,
        actor_user_id=user.user_id,
        target_user_id=target_user_id,
        action="update",
        roles=roles,
        note=". ".join(note_parts) if note_parts else "Perfis atualizados.",
    )
    return {
        "message": "acessos atualizados com sucesso",
        "usuario_id": target_user_id,
        "empresa_id": company_id,
        "roles": roles,
        "role": db.resolve_effective_role(roles),
        "full_name": next_full_name or target["full_name"],
    }


@router.delete("/empresas/{company_id}/usuarios/{target_user_id}/acessos", tags=["usuarios"])
def revoke_user_access(
    company_id: int,
    target_user_id: int,
    user: TokenData = Depends(require_role("admin")),
):
    _is_scoped_access_allowed(company_id, user)
    target = db.get_user_by_id(target_user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    if "admin" in db.get_user_roles_in_company(target_user_id, company_id):
        if db.count_admins_in_company(company_id, exclude_user_id=target_user_id) == 0:
            raise HTTPException(status_code=422, detail="A empresa precisa manter ao menos um administrador ativo.")

    db.revoke_all_user_roles_in_company(target_user_id, company_id)
    db.record_access_audit_event(
        company_id=company_id,
        actor_user_id=user.user_id,
        target_user_id=target_user_id,
        action="revoke",
        roles=[],
        note="Acesso removido da empresa.",
    )
    return {"message": "acesso removido com sucesso", "usuario_id": target_user_id, "empresa_id": company_id}


@router.get("/config", tags=["config"])
def get_system_config():
    return {
        "access_control_enabled": ACCESS_CONTROL_ENABLED,
        "base_url": API_BASE_URL,
        "default_company_id": db.get_first_company_id(),
        "default_company_name": DEFAULT_COMPANY_NAME,
        "default_company_description": DEFAULT_COMPANY_DESCRIPTION,
        "super_admin_user": SUPER_ADMIN_USER,
    }


@router.post("/admin/rebuild-documents", tags=["admin"])
def rebuild_documents_metadata(force: bool = False, user: TokenData = Depends(require_role("admin"))):
    _ = user
    return {
        "status": "ok",
        "result": services.rebuild_documents_from_markdown_files(force=force),
    }
