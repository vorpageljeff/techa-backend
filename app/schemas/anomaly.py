# app/schemas/anomaly.py
# Schemas Pydantic para Anomalia — request e response

from pydantic import BaseModel, field_validator
from typing import Optional
from uuid import UUID
from datetime import datetime


class AnomalyResponse(BaseModel):
    id: UUID
    field_id: UUID
    analysis_id: UUID
    detected_at: datetime
    ndvi_drop_pct: float
    affected_area_ha: float
    suspected_type: str
    status: str
    push_sent: bool
    alert_sent_at: Optional[datetime]

    model_config = {"from_attributes": True}


class AnomalyConfirmRequest(BaseModel):
    notes: Optional[str] = None
    confirmed_issue: Optional[str] = None   # ex: "praga", "hidrico"
    # Coordenadas GPS da localização inspecionada (opcional)
    location_lat: Optional[float] = None
    location_lon: Optional[float] = None

    @field_validator("location_lat")
    @classmethod
    def validate_lat(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and not (-90 <= v <= 90):
            raise ValueError("latitude deve estar entre -90 e 90")
        return v

    @field_validator("location_lon")
    @classmethod
    def validate_lon(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and not (-180 <= v <= 180):
            raise ValueError("longitude deve estar entre -180 e 180")
        return v


class AnomalyDismissRequest(BaseModel):
    reason: Optional[str] = None            # motivo do descarte (falso positivo)


class InspectionResponse(BaseModel):
    id: UUID
    anomaly_id: UUID
    user_id: UUID
    notes: Optional[str]
    confirmed_issue: Optional[str]
    location_wkt: Optional[str] = None      # WKT do ponto GPS
    recorded_at: datetime
    synced_at: datetime

    model_config = {"from_attributes": True}
