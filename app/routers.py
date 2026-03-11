from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from . import db
from .config import ACCESS_CONTROL_ENABLED, SUPER_ADMIN_USER
from .security import TokenData, create_access_token, current_user, hash_password, require_company_access, require_role, verify_password


router = APIRouter()


def _slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "empresa"


class CompanyCreatePayload(BaseModel):
    company_name: str
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
    company_id: int
    company_name: str


class LoginPayload(BaseModel):
    email: str
    password: str
    company_id: int


class CreateUserPayload(BaseModel):
    full_name: str
    email: str
    password: str
    role: str


def _is_scoped_access_allowed(company_id: int, user: TokenData) -> None:
    if not ACCESS_CONTROL_ENABLED:
        return
    if user.company_id != company_id:
        raise HTTPException(status_code=403, detail="Token fora do contexto da empresa")


@router.post("/empresas", status_code=201)
def create_company(payload: CompanyCreatePayload):
    company_slug = _slugify(payload.company_name)
    company_id = db.create_company(payload.company_name, company_slug)
    password_hash = hash_password(payload.admin_password)
    user_id = db.create_user(payload.admin_name, payload.admin_email, password_hash)
    db.assign_role_to_user(user_id, company_id, "admin")
    return {"empresa_id": company_id, "slug": company_slug, "admin_id": user_id}


@router.get("/auth/me", response_model=UserSessionResponse)
def get_current_user(user: TokenData = Depends(current_user)):
    if not ACCESS_CONTROL_ENABLED:
        return {
            "user_id": user.user_id,
            "full_name": "Anônimo",
            "email": user.email,
            "role": user.role,
            "company_id": user.company_id,
            "company_name": "Empresa anônima",
        }

    row = db.get_user_by_email(user.email)
    if not row:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    company = db.get_company(user.company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Empresa não encontrada")

    role = db.get_user_role_in_company(user.user_id, user.company_id) or user.role

    return {
        "user_id": user.user_id,
        "full_name": row["full_name"],
        "email": row["email"],
        "role": role,
        "company_id": user.company_id,
        "company_name": company["name"],
    }


@router.post("/auth/login", response_model=LoginResponse)
def login(payload: LoginPayload):
    user = db.get_user_by_email(payload.email)
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciais inválidas")

    role = db.get_user_role_in_company(user["id"], payload.company_id)
    if role is None:
        raise HTTPException(status_code=403, detail="Usuário não associado a esta empresa")

    token = create_access_token(
        subject=user["id"],
        company_id=payload.company_id,
        role=role,
        email=user["email"],
    )
    return {"access_token": token, "token_type": "bearer"}


@router.get("/empresas/{company_id}/usuarios")
def list_users(company_id: int, user: TokenData = Depends(require_role("admin"))):
    _is_scoped_access_allowed(company_id, user)
    return db.list_users_in_company(company_id)


@router.post("/empresas/{company_id}/usuarios")
def create_user(
    company_id: int,
    payload: CreateUserPayload,
    user: TokenData = Depends(require_role("admin")),
):
    _is_scoped_access_allowed(company_id, user)
    if payload.role not in {"admin", "editor", "revisor"}:
        raise HTTPException(status_code=422, detail="role inválido")

    existing = db.get_user_by_email(payload.email)
    if existing:
        user_id = existing["id"]
    else:
        user_id = db.create_user(payload.full_name, payload.email, hash_password(payload.password))

    db.assign_role_to_user(user_id, company_id, payload.role)
    return {"message": "usuário criado/vinculado com sucesso", "usuario_id": user_id, "empresa_id": company_id, "role": payload.role}


@router.get("/config")
def get_system_config():
    return {
        "access_control_enabled": ACCESS_CONTROL_ENABLED,
        "default_company_id": db.get_first_company_id(),
        "super_admin_user": SUPER_ADMIN_USER,
    }
