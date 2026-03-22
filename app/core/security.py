# ─────────────────────────────────────────────────────────────────
# app/core/security.py
# Autenticação JWT e hashing de senhas
# ─────────────────────────────────────────────────────────────────

from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

import bcrypt as _bcrypt
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from loguru import logger

from app.core.config import settings

# ── Esquema OAuth2 (Bearer token no header Authorization) ─────────
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


# ── Funções de senha (bcrypt direto — sem passlib) ────────────────

def hash_password(plain_password: str) -> str:
    """Gera o hash bcrypt de uma senha em texto plano."""
    return _bcrypt.hashpw(plain_password.encode(), _bcrypt.gensalt()).decode()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica se uma senha em texto plano corresponde ao hash bcrypt."""
    try:
        return _bcrypt.checkpw(plain_password.encode(), hashed_password.encode())
    except Exception:
        return False


# ── Funções JWT ───────────────────────────────────────────────────

def create_access_token(
    user_id: UUID,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Gera um JWT token para o usuário autenticado.

    Payload inclui:
      - sub: ID do usuário (string UUID)
      - exp: timestamp de expiração
      - iat: timestamp de emissão
    """
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(days=settings.JWT_EXPIRY_DAYS)
    )
    payload = {
        "sub": str(user_id),
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(
        payload,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def decode_access_token(token: str) -> dict:
    """
    Decodifica e valida um JWT token.
    Lança HTTPException 401 se o token for inválido ou expirado.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token inválido ou expirado",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
        return {"user_id": user_id}
    except JWTError as e:
        logger.warning(f"JWT inválido: {e}")
        raise credentials_exception


# ── Dependency: usuário atual autenticado ─────────────────────────

async def get_current_user_id(
    token: str = Depends(oauth2_scheme),
) -> UUID:
    """
    Dependency FastAPI: extrai o user_id do token JWT.
    Injete em qualquer rota protegida:

        async def rota(user_id: UUID = Depends(get_current_user_id)):
    """
    payload = decode_access_token(token)
    try:
        return UUID(payload["user_id"])
    except (ValueError, KeyError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token com formato inválido",
        )
