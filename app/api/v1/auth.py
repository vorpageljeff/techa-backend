# ─────────────────────────────────────────────────────────────────
# app/api/v1/auth.py
# Endpoints de autenticação — registro, login e recuperação de senha
# ─────────────────────────────────────────────────────────────────

import random
import string
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status, BackgroundTasks
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete, select, func

from uuid import UUID
from loguru import logger
from app.core.limiter import limiter as _limiter

from app.core.config import settings
from app.core.database import get_db
from app.core.security import hash_password, verify_password, create_access_token, get_current_user_id
from app.core.email import send_reset_code
from app.models.password_reset import PasswordResetCode
from app.models.admin_audit_log import AdminAuditLog
from app.models.user import User
from app.schemas.auth import UserRegister, UserLogin, TokenResponse, UserResponse

router = APIRouter()

_RESET_TTL_SEC = settings.RESET_CODE_TTL_MINUTES * 60


def _make_otp() -> str:
    """Gera código OTP de 6 dígitos."""
    return "".join(random.choices(string.digits, k=6))


@router.post(
    "/auth/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar novo usuário",
)
async def register(
    data: UserRegister,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """
    Cria uma nova conta de usuário.
    Retorna os dados do usuário criado (sem senha).
    """
    # Verifica se e-mail já está em uso (case-insensitive)
    email_lower = data.email.strip().lower()
    result = await db.execute(select(User).where(func.lower(User.email) == email_lower))
    if result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Este e-mail já está cadastrado",
        )

    user = User(
        name=data.name.strip(),
        email=email_lower,
        password=hash_password(data.password),
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    token = create_access_token(user.id)
    return {"access_token": token, "token_type": "bearer"}


@router.post(
    "/auth/login",
    response_model=TokenResponse,
    summary="Login — obtém JWT",
)
@_limiter.limit("10/minute")
async def login(
    request: Request,
    data: UserLogin,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """
    Autentica com e-mail e senha.
    Retorna um Bearer token JWT válido por 30 dias.
    """
    result = await db.execute(select(User).where(func.lower(User.email) == data.email.strip().lower()))
    user = result.scalar_one_or_none()

    # Mensagem genérica para não revelar se o e-mail existe
    if not user or not verify_password(data.password, user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="E-mail ou senha inválidos",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Conta desativada — entre em contato com o suporte",
        )

    user.last_login_at = datetime.now(timezone.utc)
    if user.plan == "admin":
        db.add(AdminAuditLog(
            actor_user_id=user.id,
            actor_email=user.email,
            action="admin.login",
            target_type="session",
            target_id=str(user.id),
            details={},
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        ))

    token = create_access_token(user.id)
    return {"access_token": token, "token_type": "bearer"}


@router.get(
    "/auth/me",
    response_model=UserResponse,
    summary="Dados do usuário autenticado",
)
async def me(
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
) -> UserResponse:
    """Retorna os dados do usuário logado a partir do JWT."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    return user


class _UpdateMeRequest(BaseModel):
    name: str | None = None


@router.patch(
    "/auth/me",
    response_model=UserResponse,
    summary="Atualizar perfil do usuário",
)
async def update_me(
    data: _UpdateMeRequest,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
) -> UserResponse:
    """Atualiza o nome do usuário autenticado."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    if data.name is not None:
        name = data.name.strip()
        if len(name) < 2:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Nome deve ter ao menos 2 caracteres",
            )
        user.name = name

    await db.flush()
    await db.refresh(user)
    return user


class _ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


@router.patch(
    "/auth/change-password",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Alterar senha (usuário autenticado)",
)
async def change_password(
    data: _ChangePasswordRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
) -> None:
    """Altera a senha do usuário logado após verificar a senha atual."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usu\u00e1rio n\u00e3o encontrado")

    if not verify_password(data.current_password, user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Senha atual incorreta",
        )

    minimum_length = 12 if user.plan == "admin" else 8
    if len(data.new_password) < minimum_length:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Nova senha deve ter pelo menos {minimum_length} caracteres"
            ),
        )

    user.password = hash_password(data.new_password)
    user.must_change_password = False
    if user.plan == "admin":
        db.add(AdminAuditLog(
            actor_user_id=user.id,
            actor_email=user.email,
            action="admin.password_changed",
            target_type="user",
            target_id=str(user.id),
            details={},
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        ))
    await db.flush()


@router.delete(
    "/auth/account",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Excluir conta (LGPD)",
)
async def delete_account(
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
) -> None:
    """
    Exclui permanentemente a conta do usuário e todos os seus dados.
    Cascade: fazendas → talhões → análises → anomalias → inspeções.
    """
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user:
        await db.delete(user)
        await db.flush()


# ── Recuperação de Senha ─────────────────────────────────────────────────────

class _ForgotRequest(BaseModel):
    email: EmailStr


class _ResetRequest(BaseModel):
    email: EmailStr
    code: str        # OTP de 6 dígitos recebido por e-mail
    new_password: str


class _VerifyRequest(BaseModel):
    email: EmailStr
    code: str


@router.post(
    "/auth/forgot-password",
    status_code=status.HTTP_200_OK,
    summary="Solicitar código de recuperação de senha",
)
async def forgot_password(
    data: _ForgotRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Envia um código OTP de 6 dígitos para o e-mail cadastrado.
    Válido por 15 minutos. Pode ser chamado mesmo se o e-mail não existir
    (resposta genérica para não revelar cadastros).
    """
    # Busca o usuário — resposta genérica independente de existir ou não
    result = await db.execute(select(User).where(func.lower(User.email) == data.email.strip().lower()))
    user = result.scalar_one_or_none()

    if user and user.is_active:
        email_lower = data.email.strip().lower()
        code = _make_otp()
        now = datetime.now(timezone.utc)
        reset_code = await db.get(PasswordResetCode, email_lower)
        if reset_code:
            reset_code.code = code
            reset_code.expires_at = now + timedelta(seconds=_RESET_TTL_SEC)
            reset_code.created_at = now
        else:
            db.add(PasswordResetCode(
                email=email_lower,
                code=code,
                expires_at=now + timedelta(seconds=_RESET_TTL_SEC),
                created_at=now,
            ))
        await db.flush()

        # Envia e-mail de forma assíncrona com log de erro
        import asyncio as _asyncio
        loop = _asyncio.get_event_loop()
        try:
            sent = await loop.run_in_executor(
                None, send_reset_code, user.email.lower(), user.name, code
            )
            if sent:
                logger.info(f"Email OTP enviado para {user.email.lower()}")
            else:
                logger.error(f"Email OTP NAO enviado para {user.email.lower()} — verifique configuracao Resend")
                await db.execute(delete(PasswordResetCode).where(PasswordResetCode.email == email_lower))
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Não foi possível enviar o e-mail de recuperação. Verifique a configuração de e-mail.",
                )
        except HTTPException:
            raise
        except Exception as email_err:
            logger.error(f"Excecao ao enviar email OTP para {user.email}: {email_err}")
            await db.execute(delete(PasswordResetCode).where(PasswordResetCode.email == email_lower))
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Não foi possível enviar o e-mail de recuperação. Tente novamente em instantes.",
            )

    return {
        "message": (
            "Se este e-mail estiver cadastrado, você receberá um código "
            f"em instantes. Válido por {settings.RESET_CODE_TTL_MINUTES} minutos."
        )
    }


@router.post(
    "/auth/verify-reset-code",
    status_code=status.HTTP_200_OK,
    summary="Verificar se o código OTP é válido (antes de trocar a senha)",
)
async def verify_reset_code(
    data: _VerifyRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Verifica o código OTP sem consumi-lo.
    Use para dar feedback imediato ao usuário no app (ex: campo verde/vermelho).
    """
    email_lower = data.email.strip().lower()
    reset_code = await db.get(PasswordResetCode, email_lower)
    now = datetime.now(timezone.utc)
    expires_at = reset_code.expires_at if reset_code else None
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if not reset_code or reset_code.code != data.code.strip() or not expires_at or expires_at <= now:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Código inválido ou expirado.",
        )
    return {"valid": True}


@router.post(
    "/auth/reset-password",
    status_code=status.HTTP_200_OK,
    summary="Redefinir senha com o código OTP recebido por e-mail",
)
async def reset_password(
    data: _ResetRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Redefine a senha do usuário usando o código OTP recebido por e-mail.
    O código é consumido (invalidado) após uso bem-sucedido.
    """
    email_lower = data.email.strip().lower()
    reset_code = await db.get(PasswordResetCode, email_lower)
    now = datetime.now(timezone.utc)
    expires_at = reset_code.expires_at if reset_code else None
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if not reset_code or reset_code.code != data.code.strip() or not expires_at or expires_at <= now:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Código inválido ou expirado. Solicite um novo código.",
        )

    # Busca o usuário (case-insensitive)
    result = await db.execute(select(User).where(func.lower(User.email) == email_lower))
    user   = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Código inválido ou expirado.",
        )

    minimum_length = 12 if user.plan == "admin" else 8
    if len(data.new_password) < minimum_length:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "A nova senha deve ter pelo menos "
                f"{minimum_length} caracteres."
            ),
        )

    # Atualiza senha e invalida o código
    user.password = hash_password(data.new_password)
    user.must_change_password = False
    await db.delete(reset_code)
    await db.flush()

    return {"message": "Senha redefinida com sucesso. Faça login com a nova senha."}


# ── FCM Token ────────────────────────────────────────────────────────────────

class _FCMTokenUpdate(BaseModel):
    fcm_token: str


@router.patch(
    "/auth/fcm-token",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Atualizar FCM token do dispositivo",
)
async def update_fcm_token(
    data: _FCMTokenUpdate,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
) -> None:
    """
    Salva o FCM token do dispositivo do usuário.
    Chamado pelo app mobile após obter o token do Firebase.
    """
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    user.fcm_token = data.fcm_token.strip()
    await db.flush()
