# app/schemas/farm.py
# Schemas Pydantic para Fazenda — request e response

from pydantic import BaseModel, field_validator
from typing import Optional
from uuid import UUID
from datetime import datetime


class FarmCreate(BaseModel):
    name: str
    area_ha: Optional[float] = None
    crop: Optional[str] = None      # cultura principal (soja, milho, trigo...)
    city: Optional[str] = None
    state: Optional[str] = None

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Nome da fazenda não pode ser vazio")
        return v

    @field_validator("area_ha")
    @classmethod
    def area_positive(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and v <= 0:
            raise ValueError("area_ha deve ser maior que 0")
        return v


class FarmUpdate(BaseModel):
    name: Optional[str] = None
    area_ha: Optional[float] = None
    crop: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None


class FarmResponse(BaseModel):
    id: UUID
    name: str
    area_ha: Optional[float]
    crop: Optional[str]
    city: Optional[str]
    state: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}
