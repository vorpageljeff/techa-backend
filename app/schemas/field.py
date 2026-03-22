# app/schemas/field.py
# Schemas Pydantic para Talhão — request e response

from pydantic import BaseModel, field_validator
from typing import Optional, Any
from uuid import UUID
from datetime import datetime, date


class FieldCreate(BaseModel):
    name: str
    crop: Optional[str] = None
    planting_date: Optional[date] = None
    geometry: dict   # GeoJSON Polygon obrigatório

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Nome do talhão não pode ser vazio")
        return v

    @field_validator("geometry")
    @classmethod
    def geometry_must_be_polygon(cls, v: dict) -> dict:
        geo_type = v.get("type", "")
        if geo_type not in ("Polygon", "MultiPolygon"):
            raise ValueError("geometry deve ser um GeoJSON Polygon ou MultiPolygon")
        if "coordinates" not in v:
            raise ValueError("geometry precisa ter 'coordinates'")
        return v


class FieldResponse(BaseModel):
    id: UUID
    farm_id: UUID
    name: str
    crop: Optional[str]
    area_ha: Optional[float]
    planting_date: Optional[date]
    geometry: Optional[dict] = None   # GeoJSON serializado
    created_at: datetime

    model_config = {"from_attributes": True}
