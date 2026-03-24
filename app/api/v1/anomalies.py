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
from app.schemas.anomaly import AnomalyResponse, AnomalyConfirmRequest, AnomalyDismissRequest, InspectionResponse

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
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
) -> list[AnomalyResponse]:
    """
    Retorna anomalias do usuário. Filtros: `status`, `field_id`.
    Paginação: `limit`, `offset`.
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

    result = await db.execute(
        query.order_by(Anomaly.detected_at.desc()).limit(limit).offset(offset)
    )
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

    # Registra inspeção de campo com notas e/ou localização GPS
    from app.models.field_inspection import FieldInspection
    location_wkt = None
    if data.location_lat is not None and data.location_lon is not None:
        location_wkt = f"POINT({data.location_lon} {data.location_lat})"

    if data.notes or data.confirmed_issue or location_wkt or data.photo_url:
        inspection = FieldInspection(
            anomaly_id=anomaly.id,
            user_id=user_id,
            notes=data.notes,
            confirmed_issue=data.confirmed_issue,
            location=location_wkt,
            photo_url=data.photo_url,
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


@router.get(
    "/anomalies/{anomaly_id}/inspections",
    response_model=list[InspectionResponse],
    summary="Histórico de inspeções de uma anomalia",
)
async def list_inspections(
    anomaly_id: UUID,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
) -> list[InspectionResponse]:
    """
    Retorna todas as inspeções de campo registradas para uma anomalia,
    ordenadas da mais recente para a mais antiga.
    """
    from app.models.field_inspection import FieldInspection

    # Verifica propriedade da anomalia
    await _get_anomaly_of_user(anomaly_id, user_id, db)

    result = await db.execute(
        select(FieldInspection)
        .where(FieldInspection.anomaly_id == anomaly_id)
        .order_by(FieldInspection.recorded_at.desc())
    )
    inspections = result.scalars().all()

    return [
        InspectionResponse(
            id=i.id,
            anomaly_id=i.anomaly_id,
            user_id=i.user_id,
            notes=i.notes,
            confirmed_issue=i.confirmed_issue,
            location_wkt=i.location,
            photo_url=i.photo_url,
            recorded_at=i.recorded_at,
            synced_at=i.synced_at,
        )
        for i in inspections
    ]
