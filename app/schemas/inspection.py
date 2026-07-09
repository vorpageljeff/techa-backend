# app/schemas/inspection.py
# Schemas Pydantic para registro de inspeções de campo.

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, field_validator


class InspectionCreate(BaseModel):
    anomaly_id: UUID
    notes: Optional[str] = None
    confirmed_issue: Optional[str] = None
    location_lat: Optional[float] = None
    location_lon: Optional[float] = None
    photo_url: Optional[str] = None
    recorded_at: Optional[datetime] = None
    mark_anomaly_inspected: bool = True

    @field_validator("notes", "confirmed_issue", "photo_url")
    @classmethod
    def empty_string_to_none(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator("location_lat")
    @classmethod
    def validate_lat(cls, value: Optional[float]) -> Optional[float]:
        if value is not None and not (-90 <= value <= 90):
            raise ValueError("latitude deve estar entre -90 e 90")
        return value

    @field_validator("location_lon")
    @classmethod
    def validate_lon(cls, value: Optional[float]) -> Optional[float]:
        if value is not None and not (-180 <= value <= 180):
            raise ValueError("longitude deve estar entre -180 e 180")
        return value

    @field_validator("photo_url")
    @classmethod
    def validate_photo_url(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        if len(value) > 500:
            raise ValueError("photo_url deve ter no máximo 500 caracteres")
        if not value.startswith(("https://", "http://")):
            raise ValueError("photo_url deve começar com http:// ou https://")
        return value


class InspectionResponse(BaseModel):
    id: UUID
    anomaly_id: UUID
    user_id: UUID
    notes: Optional[str]
    confirmed_issue: Optional[str]
    location_wkt: Optional[str] = None
    location_lat: Optional[float] = None
    location_lon: Optional[float] = None
    photo_url: Optional[str] = None
    recorded_at: datetime
    synced_at: datetime
    anomaly_status: Optional[str] = None

    model_config = {"from_attributes": True}
