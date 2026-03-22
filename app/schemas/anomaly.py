# app/schemas/anomaly.py
# Schemas Pydantic para Anomalia — request e response

from pydantic import BaseModel
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


class AnomalyDismissRequest(BaseModel):
    reason: Optional[str] = None            # motivo do descarte (falso positivo)
