# ─────────────────────────────────────────────────────────────────
# app/api/v1/admin.py
# Endpoints administrativos — requer plano "admin"
# ─────────────────────────────────────────────────────────────────

import secrets
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user_id, hash_password
from app.models.admin_audit_log import AdminAuditLog
from app.models.user import User
from app.models.farm import Farm
from app.models.field import Field
from app.models.satellite_analysis import SatelliteAnalysis
from app.models.anomaly import Anomaly
from app.schemas.admin import AdminBootstrapRequest

router = APIRouter()

# Planos válidos
_VALID_PLANS = ("free", "pro", "admin")


async def _require_admin(user_id: UUID, db: AsyncSession) -> User:
    """Verifica que o usuário tem plano 'admin'."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or user.plan != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito a administradores.",
        )
    return user


def _request_metadata(request: Request) -> dict[str, str | None]:
    return {
        "ip_address": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent"),
    }


def _audit(
    db: AsyncSession,
    actor: User,
    request: Request,
    *,
    action: str,
    target_type: str,
    target_id: str | None = None,
    details: dict | None = None,
) -> None:
    db.add(AdminAuditLog(
        actor_user_id=actor.id,
        actor_email=actor.email,
        action=action,
        target_type=target_type,
        target_id=target_id,
        details=details or {},
        **_request_metadata(request),
    ))


async def _user_counts(db: AsyncSession, user_id: UUID) -> tuple[int, int]:
    farms_count = (await db.execute(
        select(func.count(Farm.id)).where(Farm.user_id == user_id)
    )).scalar_one()
    fields_count = (await db.execute(
        select(func.count(Field.id))
        .join(Farm, Field.farm_id == Farm.id)
        .where(Farm.user_id == user_id)
    )).scalar_one()
    return farms_count, fields_count


def _user_response(
    user: User,
    *,
    farms_count: int = 0,
    fields_count: int = 0,
) -> "UserAdminResponse":
    return UserAdminResponse(
        id=user.id,
        name=user.name,
        email=user.email,
        plan=user.plan,
        is_active=user.is_active,
        must_change_password=user.must_change_password,
        last_login_at=user.last_login_at,
        created_at=user.created_at,
        farms_count=farms_count,
        fields_count=fields_count,
    )


# ── Schemas ───────────────────────────────────────────────────────

class UserAdminResponse(BaseModel):
    id: UUID
    name: str
    email: str
    plan: str
    is_active: bool
    must_change_password: bool
    last_login_at: datetime | None = None
    created_at: datetime
    farms_count: int = 0
    fields_count: int = 0

    model_config = {"from_attributes": True}


class PlanUpgradeRequest(BaseModel):
    plan: str  # free | pro | admin


class GlobalStatsResponse(BaseModel):
    users_total: int
    users_by_plan: dict
    farms_total: int
    fields_total: int
    analyses_total: int
    active_anomalies: int
    anomalies_total: int


class AdminAuditLogResponse(BaseModel):
    id: UUID
    actor_email: str
    action: str
    target_type: str
    target_id: str | None
    details: dict
    ip_address: str | None
    user_agent: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Endpoints ─────────────────────────────────────────────────────

@router.get(
    "/admin/stats",
    response_model=GlobalStatsResponse,
    summary="Estatísticas globais da plataforma",
)
async def global_stats(
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
) -> GlobalStatsResponse:
    """Retorna métricas globais da plataforma. Requer plano admin."""
    await _require_admin(user_id, db)

    # Contagens em paralelo
    users_total = (await db.execute(select(func.count(User.id)))).scalar_one()
    farms_total = (await db.execute(select(func.count(Farm.id)))).scalar_one()
    fields_total = (await db.execute(select(func.count(Field.id)))).scalar_one()
    analyses_total = (await db.execute(select(func.count(SatelliteAnalysis.id)))).scalar_one()
    active_anomalies = (await db.execute(
        select(func.count(Anomaly.id)).where(Anomaly.status == "active")
    )).scalar_one()
    anomalies_total = (await db.execute(select(func.count(Anomaly.id)))).scalar_one()

    # Distribuição de planos
    plan_rows = (await db.execute(
        select(User.plan, func.count(User.id)).group_by(User.plan)
    )).all()
    users_by_plan = {plan: count for plan, count in plan_rows}

    return GlobalStatsResponse(
        users_total=users_total,
        users_by_plan=users_by_plan,
        farms_total=farms_total,
        fields_total=fields_total,
        analyses_total=analyses_total,
        active_anomalies=active_anomalies,
        anomalies_total=anomalies_total,
    )


@router.get(
    "/admin/users",
    response_model=list[UserAdminResponse],
    summary="Listar todos os usuários",
)
async def list_users(
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
) -> list[UserAdminResponse]:
    """Lista todos os usuários da plataforma. Requer plano admin."""
    await _require_admin(user_id, db)

    result = await db.execute(
        select(
            User,
            func.count(Farm.id.distinct()).label("farms_count"),
            func.count(Field.id.distinct()).label("fields_count"),
        )
        .outerjoin(Farm, Farm.user_id == User.id)
        .outerjoin(Field, Field.farm_id == Farm.id)
        .group_by(User.id)
        .order_by(User.created_at.desc())
    )

    rows = result.all()
    return [
        _user_response(
            u,
            farms_count=farms_count,
            fields_count=fields_count,
        )
        for u, farms_count, fields_count in rows
    ]


@router.patch(
    "/admin/users/{target_user_id}/plan",
    response_model=UserAdminResponse,
    summary="Alterar plano de um usuário",
)
async def upgrade_user_plan(
    target_user_id: UUID,
    data: PlanUpgradeRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
) -> UserAdminResponse:
    """
    Altera o plano de um usuário (free → pro → admin).
    Requer plano admin para executar.
    """
    actor = await _require_admin(user_id, db)

    if data.plan not in _VALID_PLANS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Plano inválido. Use: {', '.join(_VALID_PLANS)}",
        )

    result = await db.execute(select(User).where(User.id == target_user_id))
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    if target.id == actor.id and data.plan != "admin":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Você não pode remover seu próprio acesso administrativo.",
        )

    previous_plan = target.plan
    target.plan = data.plan
    _audit(
        db,
        actor,
        request,
        action="user.plan_changed",
        target_type="user",
        target_id=str(target.id),
        details={
            "email": target.email,
            "previous_plan": previous_plan,
            "new_plan": data.plan,
        },
    )
    await db.flush()
    await db.refresh(target)

    farms_count, fields_count = await _user_counts(db, target_user_id)
    return _user_response(
        target,
        farms_count=farms_count,
        fields_count=fields_count,
    )


@router.patch(
    "/admin/users/{target_user_id}/active",
    response_model=UserAdminResponse,
    summary="Ativar ou desativar uma conta",
)
async def toggle_user_active(
    target_user_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
) -> UserAdminResponse:
    """Inverte o status ativo/inativo de um usuário. Requer plano admin."""
    actor = await _require_admin(user_id, db)

    result = await db.execute(select(User).where(User.id == target_user_id))
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    if target.id == actor.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Você não pode desativar sua própria conta administrativa.",
        )

    target.is_active = not target.is_active
    _audit(
        db,
        actor,
        request,
        action="user.access_changed",
        target_type="user",
        target_id=str(target.id),
        details={
            "email": target.email,
            "is_active": target.is_active,
        },
    )
    await db.flush()
    await db.refresh(target)

    farms_count, fields_count = await _user_counts(db, target_user_id)
    return _user_response(
        target,
        farms_count=farms_count,
        fields_count=fields_count,
    )


@router.get(
    "/admin/audit-logs",
    response_model=list[AdminAuditLogResponse],
    summary="Listar trilha de auditoria administrativa",
)
async def list_audit_logs(
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    action: str | None = Query(default=None, max_length=80),
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
) -> list[AdminAuditLogResponse]:
    await _require_admin(user_id, db)

    query = select(AdminAuditLog)
    if action:
        query = query.where(AdminAuditLog.action == action)
    query = (
        query
        .order_by(AdminAuditLog.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return list((await db.execute(query)).scalars().all())


@router.post(
    "/admin/bootstrap",
    summary="Promover o primeiro admin (uso \u00fanico)",
    status_code=status.HTTP_200_OK,
    tags=["Admin"],
)
async def bootstrap_admin(
    data: AdminBootstrapRequest,
    request: Request,
    bootstrap_token: str | None = Header(
        default=None,
        alias="X-Admin-Bootstrap-Token",
    ),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Cria o primeiro administrador usando um segredo de bootstrap do ambiente.
    Torna-se inoperante após o primeiro uso.
    """
    configured_token = settings.ADMIN_BOOTSTRAP_TOKEN
    if not configured_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Bootstrap administrativo não configurado.",
        )
    if not bootstrap_token or not secrets.compare_digest(
        bootstrap_token,
        configured_token,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token de bootstrap inválido.",
        )

    existing_admin = (await db.execute(
        select(func.count(User.id)).where(User.plan == "admin")
    )).scalar_one()

    if existing_admin > 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bootstrap j\u00e1 realizado. Um administrador j\u00e1 existe.",
        )

    email = data.email.strip().lower()
    user = (await db.execute(
        select(User).where(func.lower(User.email) == email)
    )).scalar_one_or_none()
    if user:
        user.name = data.name.strip()
        user.password = hash_password(data.password)
        user.plan = "admin"
        user.is_active = True
        user.must_change_password = True
    else:
        user = User(
            name=data.name.strip(),
            email=email,
            password=hash_password(data.password),
            plan="admin",
            is_active=True,
            must_change_password=True,
        )
        db.add(user)

    await db.flush()
    await db.refresh(user)
    db.add(AdminAuditLog(
        actor_user_id=user.id,
        actor_email=user.email,
        action="admin.bootstrap_created",
        target_type="user",
        target_id=str(user.id),
        details={"email": user.email},
        **_request_metadata(request),
    ))
    return {
        "message": "Administrador inicial criado. Troque a senha no primeiro acesso.",
        "email": user.email,
        "plan": "admin",
        "must_change_password": True,
    }
