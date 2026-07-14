# app/api/v1/inspections.py
# Registro de inspeções de campo feitas pelo app mobile.

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user_id
from app.models.anomaly import Anomaly
from app.models.farm import Farm
from app.models.field import Field
from app.models.field_inspection import FieldInspection
from app.schemas.inspection import InspectionCreate, InspectionResponse
from app.services.inspection_service import location_from_wkt, location_to_wkt

router = APIRouter()


def _inspection_to_response(
    inspection: FieldInspection,
    anomaly_status: Optional[str] = None,
) -> InspectionResponse:
    lat, lon = location_from_wkt(inspection.location)
    return InspectionResponse(
        id=inspection.id,
        anomaly_id=inspection.anomaly_id,
        user_id=inspection.user_id,
        notes=inspection.notes,
        confirmed_issue=inspection.confirmed_issue,
        location_wkt=inspection.location,
        location_lat=lat,
        location_lon=lon,
        photo_url=inspection.photo_url,
        recorded_at=inspection.recorded_at,
        synced_at=inspection.synced_at,
        anomaly_status=anomaly_status,
    )


async def _get_anomaly_of_user(
    anomaly_id: UUID,
    user_id: UUID,
    db: AsyncSession,
) -> Anomaly:
    result = await db.execute(
        select(Anomaly)
        .join(Field, Anomaly.field_id == Field.id)
        .join(Farm, Field.farm_id == Farm.id)
        .where(Anomaly.id == anomaly_id, Farm.user_id == user_id)
    )
    anomaly = result.scalar_one_or_none()
    if anomaly is None:
        raise HTTPException(status_code=404, detail="Anomalia não encontrada")
    return anomaly


@router.post(
    "",
    response_model=InspectionResponse,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
@router.post(
    "/",
    response_model=InspectionResponse,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
@router.post(
    "/inspections",
    response_model=InspectionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar inspeção de campo",
)
async def create_inspection(
    data: InspectionCreate,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
) -> InspectionResponse:
    """
    Registra evidências coletadas no campo pelo app mobile.

    O app pode enviar nota, tipo provável do problema, coordenada GPS e a URL
    de uma foto já enviada para um storage externo. Por padrão, uma anomalia
    ativa passa para `inspected` quando a inspeção é sincronizada.
    """
    anomaly = await _get_anomaly_of_user(data.anomaly_id, user_id, db)

    if data.mark_anomaly_inspected and anomaly.status == "active":
        anomaly.status = "inspected"

    now = datetime.now(timezone.utc)
    inspection = FieldInspection(
        anomaly_id=anomaly.id,
        user_id=user_id,
        notes=data.notes,
        confirmed_issue=data.confirmed_issue,
        location=location_to_wkt(data.location_lat, data.location_lon),
        photo_url=data.photo_url,
        recorded_at=data.recorded_at or now,
        synced_at=now,
    )
    db.add(inspection)

    await db.flush()
    await db.refresh(inspection)
    return _inspection_to_response(inspection, anomaly.status)


@router.get(
    "",
    response_model=list[InspectionResponse],
    include_in_schema=False,
)
@router.get(
    "/",
    response_model=list[InspectionResponse],
    include_in_schema=False,
)
@router.get(
    "/inspections",
    response_model=list[InspectionResponse],
    summary="Listar inspeções de campo do usuário",
)
async def list_inspections(
    anomaly_id: Optional[UUID] = Query(None, description="Filtrar por anomalia"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
) -> list[InspectionResponse]:
    query = (
        select(FieldInspection, Anomaly.status)
        .join(Anomaly, FieldInspection.anomaly_id == Anomaly.id)
        .join(Field, Anomaly.field_id == Field.id)
        .join(Farm, Field.farm_id == Farm.id)
        .where(Farm.user_id == user_id)
    )
    if anomaly_id is not None:
        query = query.where(FieldInspection.anomaly_id == anomaly_id)

    result = await db.execute(
        query.order_by(FieldInspection.recorded_at.desc()).limit(limit).offset(offset)
    )
    return [
        _inspection_to_response(inspection, anomaly_status)
        for inspection, anomaly_status in result.all()
    ]


@router.get(
    "/{inspection_id}",
    response_model=InspectionResponse,
    include_in_schema=False,
)
@router.get(
    "/inspections/{inspection_id}",
    response_model=InspectionResponse,
    summary="Detalhe de uma inspeção de campo",
)
async def get_inspection(
    inspection_id: UUID,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
) -> InspectionResponse:
    result = await db.execute(
        select(FieldInspection, Anomaly.status)
        .join(Anomaly, FieldInspection.anomaly_id == Anomaly.id)
        .join(Field, Anomaly.field_id == Field.id)
        .join(Farm, Field.farm_id == Farm.id)
        .where(FieldInspection.id == inspection_id, Farm.user_id == user_id)
    )
    row = result.one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Inspeção não encontrada")

    inspection, anomaly_status = row
    return _inspection_to_response(inspection, anomaly_status)
