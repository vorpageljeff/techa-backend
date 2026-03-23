# ─────────────────────────────────────────────────────────────────
# app/api/v1/dashboard.py
# Endpoint de estatísticas agregadas para a tela inicial do app
# Requer autenticação JWT
# ─────────────────────────────────────────────────────────────────

from uuid import UUID
from typing import Any, Optional
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.database import get_db
from app.core.security import get_current_user_id
from app.models.farm import Farm
from app.models.field import Field
from app.models.anomaly import Anomaly
from app.models.satellite_analysis import SatelliteAnalysis

router = APIRouter()


# ── Schemas de resposta ───────────────────────────────────────────

class FieldSummary(BaseModel):
    id: UUID
    name: str
    farm_name: str
    crop: Optional[str]
    area_ha: Optional[float]
    latest_ndvi: Optional[float] = None
    latest_ndvi_date: Optional[str] = None
    ndvi_status: str = "sem_dados"   # critico | alerta | normal | excelente | sem_dados
    active_anomalies: int = 0


class DashboardResponse(BaseModel):
    farms_count: int
    fields_count: int
    active_anomalies: int
    fields: list[FieldSummary]
    recent_anomalies: list[dict]   # últimas 5 anomalias ativas


def _ndvi_status(ndvi: Optional[float]) -> str:
    if ndvi is None:
        return "sem_dados"
    if ndvi < 0.2:
        return "critico"
    if ndvi < 0.4:
        return "alerta"
    if ndvi < 0.6:
        return "normal"
    return "excelente"


@router.get(
    "/dashboard",
    response_model=DashboardResponse,
    summary="Estatísticas agregadas para a tela inicial",
)
async def get_dashboard(
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
) -> Any:
    """
    Retorna um resumo completo para a tela inicial do aplicativo:
    - Contagem de fazendas e talhões
    - Total de anomalias ativas
    - Lista de talhões com NDVI mais recente e status de alerta
    - Últimas 5 anomalias ativas
    """

    # ── Contagem de fazendas ─────────────────────────────────────
    farms_result = await db.execute(
        select(Farm.id, Farm.name).where(Farm.user_id == user_id)
    )
    farms_rows = farms_result.all()
    farm_ids = [r.id for r in farms_rows]
    farm_name_map = {r.id: r.name for r in farms_rows}
    farms_count = len(farm_ids)

    if not farm_ids:
        return DashboardResponse(
            farms_count=0,
            fields_count=0,
            active_anomalies=0,
            fields=[],
            recent_anomalies=[],
        )

    # ── Talhões ───────────────────────────────────────────────────
    fields_result = await db.execute(
        select(Field).where(Field.farm_id.in_(farm_ids)).order_by(Field.created_at.desc())
    )
    fields = fields_result.scalars().all()
    field_ids = [f.id for f in fields]

    # ── Análise mais recente por talhão ───────────────────────────
    # Subquery: MAX(image_date) por field_id
    latest_analysis_map: dict[UUID, SatelliteAnalysis] = {}
    if field_ids:
        analyses_result = await db.execute(
            select(SatelliteAnalysis)
            .where(
                SatelliteAnalysis.field_id.in_(field_ids),
                SatelliteAnalysis.status == "valid",
            )
            .order_by(
                SatelliteAnalysis.field_id,
                SatelliteAnalysis.image_date.desc(),
            )
        )
        all_analyses = analyses_result.scalars().all()
        # Mantém apenas a mais recente por talhão
        seen: set[UUID] = set()
        for analysis in all_analyses:
            if analysis.field_id not in seen:
                latest_analysis_map[analysis.field_id] = analysis
                seen.add(analysis.field_id)

    # ── Anomalias ativas por talhão ───────────────────────────────
    active_anomalies_map: dict[UUID, int] = {fid: 0 for fid in field_ids}
    if field_ids:
        anomaly_counts_result = await db.execute(
            select(Anomaly.field_id, func.count(Anomaly.id).label("cnt"))
            .where(
                Anomaly.field_id.in_(field_ids),
                Anomaly.status == "active",
            )
            .group_by(Anomaly.field_id)
        )
        for row in anomaly_counts_result.all():
            active_anomalies_map[row.field_id] = row.cnt

    total_active = sum(active_anomalies_map.values())

    # ── Monta sumário de talhões ──────────────────────────────────
    field_summaries: list[FieldSummary] = []
    for f in fields:
        latest = latest_analysis_map.get(f.id)
        field_summaries.append(
            FieldSummary(
                id=f.id,
                name=f.name,
                farm_name=farm_name_map.get(f.farm_id, ""),
                crop=f.crop,
                area_ha=f.area_ha,
                latest_ndvi=latest.ndvi_mean if latest else None,
                latest_ndvi_date=latest.image_date.isoformat() if latest else None,
                ndvi_status=_ndvi_status(latest.ndvi_mean if latest else None),
                active_anomalies=active_anomalies_map.get(f.id, 0),
            )
        )

    # ── Últimas 5 anomalias ativas ────────────────────────────────
    recent_anomalies: list[dict] = []
    if field_ids:
        recent_result = await db.execute(
            select(Anomaly, Field.name.label("field_name"), Farm.name.label("farm_name"))
            .join(Field, Anomaly.field_id == Field.id)
            .join(Farm, Field.farm_id == Farm.id)
            .where(
                Anomaly.field_id.in_(field_ids),
                Anomaly.status == "active",
            )
            .order_by(Anomaly.detected_at.desc())
            .limit(5)
        )
        for anomaly, field_name, farm_name in recent_result.all():
            recent_anomalies.append(
                {
                    "id":               str(anomaly.id),
                    "field_id":         str(anomaly.field_id),
                    "field_name":       field_name,
                    "farm_name":        farm_name,
                    "detected_at":      anomaly.detected_at.isoformat(),
                    "ndvi_drop_pct":    anomaly.ndvi_drop_pct,
                    "affected_area_ha": anomaly.affected_area_ha,
                    "suspected_type":   anomaly.suspected_type,
                    "status":           anomaly.status,
                }
            )

    return DashboardResponse(
        farms_count=farms_count,
        fields_count=len(fields),
        active_anomalies=total_active,
        fields=field_summaries,
        recent_anomalies=recent_anomalies,
    )
