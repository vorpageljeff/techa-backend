# ─────────────────────────────────────────────────────────────────
# app/api/v1/admin.py
# Endpoints administrativos — requer plano "admin"
# ─────────────────────────────────────────────────────────────────

from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.database import get_db
from app.core.security import get_current_user_id
from app.models.user import User
from app.models.farm import Farm
from app.models.field import Field
from app.models.satellite_analysis import SatelliteAnalysis
from app.models.anomaly import Anomaly

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


# ── Schemas ───────────────────────────────────────────────────────

class UserAdminResponse(BaseModel):
    id: UUID
    name: str
    email: str
    plan: str
    is_active: bool
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
        UserAdminResponse(
            id=u.id,
            name=u.name,
            email=u.email,
            plan=u.plan,
            is_active=u.is_active,
            created_at=u.created_at,
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
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
) -> UserAdminResponse:
    """
    Altera o plano de um usuário (free → pro → admin).
    Requer plano admin para executar.
    """
    await _require_admin(user_id, db)

    if data.plan not in _VALID_PLANS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Plano inválido. Use: {', '.join(_VALID_PLANS)}",
        )

    result = await db.execute(select(User).where(User.id == target_user_id))
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    target.plan = data.plan
    await db.flush()
    await db.refresh(target)

    # Contagens para o response
    farms_count = (await db.execute(
        select(func.count(Farm.id)).where(Farm.user_id == target_user_id)
    )).scalar_one()
    fields_count = (await db.execute(
        select(func.count(Field.id))
        .join(Farm, Field.farm_id == Farm.id)
        .where(Farm.user_id == target_user_id)
    )).scalar_one()

    return UserAdminResponse(
        id=target.id,
        name=target.name,
        email=target.email,
        plan=target.plan,
        is_active=target.is_active,
        created_at=target.created_at,
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
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
) -> UserAdminResponse:
    """Inverte o status ativo/inativo de um usuário. Requer plano admin."""
    await _require_admin(user_id, db)

    result = await db.execute(select(User).where(User.id == target_user_id))
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    target.is_active = not target.is_active
    await db.flush()
    await db.refresh(target)

    return UserAdminResponse(
        id=target.id,
        name=target.name,
        email=target.email,
        plan=target.plan,
        is_active=target.is_active,
        created_at=target.created_at,
        farms_count=0,
        fields_count=0,
    )


@router.post(
    "/admin/bootstrap",
    summary="Promover o primeiro admin (uso \u00fanico)",
    status_code=status.HTTP_200_OK,
    tags=["Admin"],
)
async def bootstrap_admin(
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
) -> dict:
    """
    Promove o usu\u00e1rio autenticado para admin.
    S\u00f3 funciona se ainda n\u00e3o existir nenhum usu\u00e1rio com plano 'admin'.
    Torna-se inoperante ap\u00f3s o primeiro uso.
    """
    existing_admin = (await db.execute(
        select(func.count(User.id)).where(User.plan == "admin")
    )).scalar_one()

    if existing_admin > 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bootstrap j\u00e1 realizado. Um administrador j\u00e1 existe.",
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usu\u00e1rio n\u00e3o encontrado")

    user.plan = "admin"
    await db.flush()
    await db.refresh(user)
    return {"message": f"Usu\u00e1rio {user.email} promovido a admin.", "plan": "admin"}
