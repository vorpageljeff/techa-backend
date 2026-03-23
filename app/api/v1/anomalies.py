# ─────────────────────────────────────────────────────────────────
# app/api/v1/anomalies.py
# Consulta e gestão de anomalias detectadas pelo pipeline Sentinel-2
# Requer autenticação JWT
# ─────────────────────────────────────────────────────────────────

from uuid import UUID
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.security import get_current_user_id
from app.models.anomaly import Anomaly
from app.models.field import Field
from app.models.farm import Farm
from app.schemas.anomaly import AnomalyResponse, AnomalyConfirmRequest, AnomalyDismissRequest

router = APIRouter()


async def _get_anomaly_of_user(
    anomaly_id: UUID,
    user_id: UUID,
    db: AsyncSession,
) -> Anomaly:
    """
    Busca anomalia garantindo que pertence ao usuário autenticado
    (via talhão → fazenda → usuário).
    """
    result = await db.execute(
        select(Anomaly)
        .join(Field, Anomaly.field_id == Field.id)
        .join(Farm, Field.farm_id == Farm.id)
        .where(Anomaly.id == anomaly_id, Farm.user_id == user_id)
    )
    anomaly = result.scalar_one_or_none()
    if not anomaly:
        raise HTTPException(status_code=404, detail="Anomalia não encontrada")
    return anomaly


@router.get(
    "/anomalies",
    response_model=list[AnomalyResponse],
    summary="Listar anomalias do usuário",
)
async def list_anomalies(
    status: Optional[str] = Query(None, description="Filtrar por status: active | inspected | dismissed"),
    field_id: Optional[UUID] = Query(None, description="Filtrar por talhão"),
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
) -> list[AnomalyResponse]:
    """
    Retorna anomalias detectadas em fazendas do usuário.
    Filtros opcionais: `status` e `field_id`.
    Ordenadas da mais recente para a mais antiga.
    """
    query = (
        select(Anomaly)
        .join(Field, Anomaly.field_id == Field.id)
        .join(Farm, Field.farm_id == Farm.id)
        .where(Farm.user_id == user_id)
    )
    if status:
        query = query.where(Anomaly.status == status)
    if field_id:
        query = query.where(Anomaly.field_id == field_id)

    result = await db.execute(query.order_by(Anomaly.detected_at.desc()))
    return result.scalars().all()


@router.get(
    "/anomalies/{anomaly_id}",
    response_model=AnomalyResponse,
    summary="Detalhe de uma anomalia",
)
async def get_anomaly(
    anomaly_id: UUID,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
) -> AnomalyResponse:
    """Retorna detalhes completos de uma anomalia."""
    return await _get_anomaly_of_user(anomaly_id, user_id, db)


@router.patch(
    "/anomalies/{anomaly_id}/confirm",
    response_model=AnomalyResponse,
    summary="Confirmar anomalia no campo",
)
async def confirm_anomaly(
    anomaly_id: UUID,
    data: AnomalyConfirmRequest,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
) -> AnomalyResponse:
    """
    Produtor confirma que a anomalia foi verificada no campo.
    Muda o status de 'active' para 'inspected'.
    """
    anomaly = await _get_anomaly_of_user(anomaly_id, user_id, db)

    if anomaly.status not in ("active",):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Anomalia não pode ser confirmada no status '{anomaly.status}'",
        )

    anomaly.status = "inspected"

    # Registra inspeção de campo se notas foram fornecidas
    if data.notes or data.confirmed_issue:
        from app.models.field_inspection import FieldInspection
        inspection = FieldInspection(
            anomaly_id=anomaly.id,
            user_id=user_id,
            notes=data.notes,
            confirmed_issue=data.confirmed_issue,
            recorded_at=datetime.now(timezone.utc),
        )
        db.add(inspection)

    await db.flush()
    await db.refresh(anomaly)
    return anomaly


@router.patch(
    "/anomalies/{anomaly_id}/dismiss",
    response_model=AnomalyResponse,
    summary="Descartar anomalia (falso positivo)",
)
async def dismiss_anomaly(
    anomaly_id: UUID,
    data: AnomalyDismissRequest,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
) -> AnomalyResponse:
    """
    Produtor descarta a anomalia como falso positivo.
    Muda o status para 'dismissed'.
    Útil para treinar o modelo de detecção futuramente.
    """
    anomaly = await _get_anomaly_of_user(anomaly_id, user_id, db)

    if anomaly.status not in ("active",):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Anomalia não pode ser descartada no status '{anomaly.status}'",
        )

    anomaly.status = "dismissed"

    # Registra motivo do descarte como inspeção de campo
    if data.reason:
        from app.models.field_inspection import FieldInspection
        inspection = FieldInspection(
            anomaly_id=anomaly.id,
            user_id=user_id,
            notes=f"[DESCARTE] {data.reason}",
            recorded_at=datetime.now(timezone.utc),
        )
        db.add(inspection)

    await db.flush()
    await db.refresh(anomaly)
    return anomaly
