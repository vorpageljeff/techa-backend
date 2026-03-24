# ─────────────────────────────────────────────────────────────────
# app/api/v1/farms.py
# CRUD de Fazendas — requer autenticação JWT
# ─────────────────────────────────────────────────────────────────

from uuid import UUID

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.security import get_current_user_id
from app.models.farm import Farm
from app.schemas.farm import FarmCreate, FarmUpdate, FarmResponse

router = APIRouter()


@router.post(
    "/farms",
    response_model=FarmResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Criar fazenda",
)
async def create_farm(
    data: FarmCreate,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
) -> FarmResponse:
    """Cria uma nova fazenda vinculada ao usuário autenticado."""
    farm = Farm(
        user_id=user_id,
        name=data.name,
        area_ha=data.area_ha,
        crop=data.crop,
        city=data.city,
        state=data.state,
    )
    db.add(farm)
    await db.flush()
    await db.refresh(farm)
    return farm


@router.get(
    "/farms",
    response_model=list[FarmResponse],
    summary="Listar fazendas do usuário",
)
async def list_farms(
    limit: int = Query(50, ge=1, le=200, description="Máximo de itens por página"),
    offset: int = Query(0, ge=0, description="Número de itens a pular"),
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
) -> list[FarmResponse]:
    """Retorna fazendas do usuário autenticado. Suporta paginação via `limit` e `offset`."""
    result = await db.execute(
        select(Farm)
        .where(Farm.user_id == user_id)
        .order_by(Farm.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return result.scalars().all()


@router.get(
    "/farms/{farm_id}",
    response_model=FarmResponse,
    summary="Detalhe de uma fazenda",
)
async def get_farm(
    farm_id: UUID,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
) -> FarmResponse:
    """Retorna os detalhes de uma fazenda. Exige que pertença ao usuário."""
    result = await db.execute(
        select(Farm).where(Farm.id == farm_id, Farm.user_id == user_id)
    )
    farm = result.scalar_one_or_none()
    if not farm:
        raise HTTPException(status_code=404, detail="Fazenda não encontrada")
    return farm


@router.patch(
    "/farms/{farm_id}",
    response_model=FarmResponse,
    summary="Atualizar fazenda",
)
async def update_farm(
    farm_id: UUID,
    data: FarmUpdate,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
) -> FarmResponse:
    """Atualiza campos de uma fazenda. Apenas campos enviados são alterados."""
    result = await db.execute(
        select(Farm).where(Farm.id == farm_id, Farm.user_id == user_id)
    )
    farm = result.scalar_one_or_none()
    if not farm:
        raise HTTPException(status_code=404, detail="Fazenda não encontrada")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(farm, field, value)

    await db.flush()
    await db.refresh(farm)
    return farm


@router.delete(
    "/farms/{farm_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Deletar fazenda",
)
async def delete_farm(
    farm_id: UUID,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
) -> None:
    """
    Remove permanentemente uma fazenda e todos seus talhões (cascade).
    Ação irreversível.
    """
    result = await db.execute(
        select(Farm).where(Farm.id == farm_id, Farm.user_id == user_id)
    )
    farm = result.scalar_one_or_none()
    if not farm:
        raise HTTPException(status_code=404, detail="Fazenda não encontrada")

    await db.delete(farm)
