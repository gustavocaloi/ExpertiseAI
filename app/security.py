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
    SECRET_KEY,
    SUPER_ADMIN_USER,
)
from . import db


pwd_context = CryptContext(schemes=["pbkdf2_sha256", "bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


class TokenData(BaseModel):
    sub: str
    user_id: int
    company_id: int
    role: str
    email: str


def _anonymous_user() -> TokenData:
    return TokenData(
        sub="anonymous",
        user_id=0,
        company_id=0,
        role="anonymous",
        email=SUPER_ADMIN_USER,
    )


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(subject: int, company_id: int, role: str, email: str, expires_minutes: Optional[int] = None) -> str:
    expire = datetime.utcnow() + timedelta(minutes=expires_minutes or ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = {
        "sub": str(subject),
        "user_id": subject,
        "company_id": company_id,
        "role": role,
        "email": email,
        "exp": expire,
    }
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> TokenData:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return TokenData(
            sub=payload.get("sub"),
            user_id=int(payload.get("user_id")),
            company_id=int(payload.get("company_id")),
            role=payload.get("role"),
            email=payload.get("email"),
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido") from e


async def current_user(token: Optional[str] = Depends(oauth2_scheme)) -> TokenData:
    if not ACCESS_CONTROL_ENABLED:
        return _anonymous_user()
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token de autenticação não informado")
    data = decode_access_token(token)
    return data


def require_role(*roles: str):
    async def _checker(user: TokenData = Depends(current_user)):
        if not ACCESS_CONTROL_ENABLED:
            return user
        if user.role not in roles:
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
    current_role = db.get_user_role_in_company(user.user_id, company_id)
    if current_role and current_role != user.role:
        user.role = current_role
    return user
