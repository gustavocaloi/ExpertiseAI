from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt
from passlib.context import CryptContext
from pydantic import BaseModel

from .config import (
    ACCESS_CONTROL_ENABLED,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    ALGORITHM,
    REFRESH_TOKEN_EXPIRE_MINUTES,
    SECRET_KEY,
    SUPER_ADMIN_USER,
)
from . import db
from .maintenance import session_epoch


pwd_context = CryptContext(schemes=["pbkdf2_sha256", "bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


class TokenData(BaseModel):
    sub: str
    user_id: int
    company_id: int
    role: str
    email: str
    roles: list[str] = []
    token_type: str = "access"


def _anonymous_user() -> TokenData:
    return TokenData(
        sub="anonymous",
        user_id=0,
        company_id=0,
        role="anonymous",
        email=SUPER_ADMIN_USER,
        roles=["anonymous"],
        token_type="access",
    )


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(
    subject: int,
    company_id: int,
    role: str,
    email: str,
    roles: Optional[list[str]] = None,
    expires_minutes: Optional[int] = None,
) -> str:
    expire = datetime.utcnow() + timedelta(minutes=expires_minutes or ACCESS_TOKEN_EXPIRE_MINUTES)
    normalized_roles = roles or ([role] if role else [])
    to_encode = {
        "sub": str(subject),
        "user_id": subject,
        "company_id": company_id,
        "role": role,
        "roles": normalized_roles,
        "email": email,
        "exp": expire,
        "session_epoch": session_epoch(),
    }
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(
    subject: int,
    company_id: int,
    role: str,
    email: str,
    roles: Optional[list[str]] = None,
    expires_minutes: Optional[int] = None,
) -> str:
    expire = datetime.utcnow() + timedelta(minutes=expires_minutes or REFRESH_TOKEN_EXPIRE_MINUTES)
    normalized_roles = roles or ([role] if role else [])
    to_encode = {
        "sub": str(subject),
        "user_id": subject,
        "company_id": company_id,
        "role": role,
        "roles": normalized_roles,
        "email": email,
        "token_type": "refresh",
        "session_epoch": session_epoch(),
        "exp": expire,
    }
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str, expected_token_type: str = "access") -> TokenData:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("session_epoch", "") != session_epoch():
            raise ValueError("session invalidated by platform restore")
        token_type = str(payload.get("token_type") or "access")
        if token_type != expected_token_type:
            raise ValueError("unexpected token type")
        return TokenData(
            sub=payload.get("sub"),
            user_id=int(payload.get("user_id")),
            company_id=int(payload.get("company_id")),
            role=payload.get("role"),
            email=payload.get("email"),
            roles=[str(item) for item in (payload.get("roles") or [payload.get("role")]) if item],
            token_type=token_type,
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido") from e


async def current_user(token: Optional[str] = Depends(oauth2_scheme)) -> TokenData:
    if not ACCESS_CONTROL_ENABLED:
        return _anonymous_user()
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token de autenticação não informado")
    data = decode_access_token(token)
    if not db.get_user_by_email(data.email):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuário não encontrado ou removido")
    return data


async def optional_current_user(token: Optional[str] = Depends(oauth2_scheme)) -> TokenData:
    if not ACCESS_CONTROL_ENABLED or not token:
        return _anonymous_user()
    data = decode_access_token(token)
    if not db.get_user_by_email(data.email):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuário não encontrado ou removido")
    return data


def _refresh_membership(user: TokenData) -> TokenData:
    roles = db.get_user_roles_in_company(user.user_id, user.company_id)
    if not roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuário não possui mais acesso ativo a esta empresa",
        )
    current_role = str(db.resolve_effective_role(roles) or "").strip()
    if not current_role:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuário sem perfil ativo para esta empresa",
        )
    user.roles = roles
    user.role = current_role
    return user


def user_has_required_role(user: TokenData, *roles: str) -> bool:
    normalized_required = {db.normalize_access_role(role) for role in roles}
    normalized_user_roles = {db.normalize_access_role(role) for role in (user.roles or [user.role])}
    if "admin" in normalized_user_roles:
        return True
    return bool(normalized_required & normalized_user_roles)


def require_role(*roles: str):
    async def _checker(user: TokenData = Depends(current_user)):
        if not ACCESS_CONTROL_ENABLED:
            return user
        user = _refresh_membership(user)
        if not user_has_required_role(user, *roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Perfil insuficiente. Permitido: {', '.join(roles)}",
            )
        return user

    return _checker


def require_company_access(company_id: int, user: TokenData = Depends(current_user)) -> TokenData:
    if not ACCESS_CONTROL_ENABLED:
        return TokenData(
            sub=user.sub,
            user_id=user.user_id,
            company_id=company_id,
            role=user.role,
            email=user.email,
        )
    if user.company_id != company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token fora do contexto da empresa",
        )
    return _refresh_membership(user)


def get_monitoria_scope(company_id: int, user: TokenData):
    from . import monitoria_db as mdb

    if not ACCESS_CONTROL_ENABLED:
        return mdb.resolve_monitoria_scope(
            user.user_id,
            company_id,
            kb_roles=["admin"],
            access_control_enabled=False,
        )
    refreshed = _refresh_membership(user) if user.company_id == company_id else user
    return mdb.resolve_monitoria_scope(
        refreshed.user_id,
        company_id,
        kb_roles=list(refreshed.roles or [refreshed.role]),
        access_control_enabled=True,
    )


def require_monitoria_role(*roles: str):
    async def _checker(
        company_id: int,
        user: TokenData = Depends(current_user),
    ):
        from . import monitoria_db as mdb

        if not ACCESS_CONTROL_ENABLED:
            return user, get_monitoria_scope(company_id, user)
        if user.company_id != company_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Token fora do contexto da empresa",
            )
        user = _refresh_membership(user)
        assert_module_access(company_id, user, "monitoria")
        scope = get_monitoria_scope(company_id, user)
        if not scope.roles and not scope.is_full_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Usuário sem acesso ao módulo de monitoria",
            )
        if roles and not mdb.user_has_monitoria_role(scope, *roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Perfil de monitoria insuficiente. Permitido: {', '.join(roles)}",
            )
        return user, scope

    return _checker


def assert_module_access(company_id: int, user: TokenData, module: str) -> None:
    if ACCESS_CONTROL_ENABLED and module not in db.get_user_modules(user.user_id, company_id)["modules"]:
        raise HTTPException(status_code=403, detail="Usuário sem acesso ao módulo " + module)


def require_content_module(company_id: int, user: TokenData = Depends(current_user)):
    user = require_company_access(company_id, user)
    assert_module_access(company_id, user, "conteudo")
    return user
