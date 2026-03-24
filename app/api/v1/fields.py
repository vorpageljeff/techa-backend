# ─────────────────────────────────────────────────────────────────
# app/api/v1/fields.py
# CRUD de Talhões com polígono GeoJSON — requer autenticação JWT
# Geometria armazenada como WKT (Text) no banco.
# Conversão GeoJSON ↔ WKT feita via shapely (sem PostGIS).
# ─────────────────────────────────────────────────────────────────

import uuid as _uuid
from uuid import UUID
from typing import Any, Optional
from datetime import datetime, date, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from shapely.geometry import shape, mapping
from shapely import wkt as shapely_wkt
from pyproj import Geod

from app.core.database import get_db
from app.core.security import get_current_user_id
from app.models.field import Field
from app.models.farm import Farm
from app.models.satellite_analysis import SatelliteAnalysis
from app.models.anomaly import Anomaly
from app.schemas.field import FieldCreate, FieldUpdate, FieldResponse
from app.services.report_service import generate_field_report

router = APIRouter()

# Objeto para calcular área geodésica (WGS84)
_geod = Geod(ellps="WGS84")


# ── Schema de resposta para análises ──────────────────────────────
class SatelliteAnalysisResponse(BaseModel):
    id: UUID
    field_id: UUID
    image_date: date
    source: str
    cloud_cover_pct: Optional[float] = None
    ndvi_mean: Optional[float] = None
    ndvi_min: Optional[float] = None
    ndvi_max: Optional[float] = None
    status: str
    processed_at: datetime

    model_config = {"from_attributes": True}


def _calc_area_ha(shapely_geom) -> float:
    """Calcula área em hectares de um polígono WGS84 usando pyproj."""
    area_m2, _ = _geod.geometry_area_perimeter(shapely_geom)
    return abs(area_m2) / 10_000


def _geom_to_geojson(wkt_text) -> dict | None:
    """Converte WKT string para dict GeoJSON usando shapely."""
    if not wkt_text:
        return None
    try:
        return dict(mapping(shapely_wkt.loads(wkt_text)))
    except Exception:
        return None


def _field_to_response(field: Field) -> dict:
    """Serializa um Field ORM para dict compatível com FieldResponse."""
    return {
        "id": field.id,
        "farm_id": field.farm_id,
        "name": field.name,
        "crop": field.crop,
        "area_ha": field.area_ha,
        "planting_date": field.planting_date,
        "geometry": _geom_to_geojson(field.geometry),
        "created_at": field.created_at,
    }


async def _get_farm_or_404(
    farm_id: UUID,
    user_id: UUID,
    db: AsyncSession,
) -> Farm:
    """Busca fazenda verificando propriedade. Lança 404 se não encontrada."""
    result = await db.execute(
        select(Farm).where(Farm.id == farm_id, Farm.user_id == user_id)
    )
    farm = result.scalar_one_or_none()
    if not farm:
        raise HTTPException(status_code=404, detail="Fazenda não encontrada")
    return farm


async def _get_field_owned_or_404(
    field_id: UUID,
    user_id: UUID,
    db: AsyncSession,
) -> Field:
    """Busca talhão verificando propriedade via join com Farm."""
    result = await db.execute(
        select(Field)
        .join(Farm, Field.farm_id == Farm.id)
        .where(Field.id == field_id, Farm.user_id == user_id)
    )
    field = result.scalar_one_or_none()
    if not field:
        raise HTTPException(status_code=404, detail="Talhão não encontrado")
    return field


@router.post(
    "/farms/{farm_id}/fields",
    response_model=FieldResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Criar talhão em uma fazenda",
)
async def create_field(
    farm_id: UUID,
    data: FieldCreate,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
) -> Any:
    """
    Cria um talhão com polígono GeoJSON.
    A área é calculada automaticamente via pyproj (WGS84).
    A geometria é armazenada como WKT (Text) e a área calculada via pyproj (WGS84).
    """
    await _get_farm_or_404(farm_id, user_id, db)

    # Converte GeoJSON → Shapely para cálculo de área e WKT
    try:
        shapely_geom = shape(data.geometry)
        if not shapely_geom.is_valid:
            shapely_geom = shapely_geom.buffer(0)   # auto-reparo
        area_ha = _calc_area_ha(shapely_geom)
        wkt_text = shapely_geom.wkt   # armazenado como texto simples
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Geometria inválida: {exc}",
        )

    # INSERT via raw SQL — geometry como texto WKT simples (sem PostGIS)
    field_id = _uuid.uuid4()
    now = datetime.now(timezone.utc)

    await db.execute(
        text("""
            INSERT INTO fields
                (id, farm_id, name, crop, planting_date, geometry, area_ha, created_at)
            VALUES
                (:id, :farm_id, :name, :crop, :planting_date,
                 :geom, :area_ha, :created_at)
        """),
        {
            "id": str(field_id),
            "farm_id": str(farm_id),
            "name": data.name,
            "crop": data.crop,
            "planting_date": data.planting_date,
            "geom": wkt_text,
            "area_ha": round(area_ha, 4),
            "created_at": now,
        },
    )

    # Busca o talhão recém-criado via ORM para retornar com geometry serializada
    result = await db.execute(select(Field).where(Field.id == field_id))
    field = result.scalar_one()
    return _field_to_response(field)


@router.get(
    "/farms/{farm_id}/fields",
    response_model=list[FieldResponse],
    summary="Listar talhões de uma fazenda",
)
async def list_fields(
    farm_id: UUID,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
) -> Any:
    """Lista talhões de uma fazenda do usuário. Suporta paginação via `limit` e `offset`."""
    await _get_farm_or_404(farm_id, user_id, db)

    result = await db.execute(
        select(Field)
        .where(Field.farm_id == farm_id)
        .order_by(Field.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    fields = result.scalars().all()
    return [_field_to_response(f) for f in fields]


@router.get(
    "/fields/{field_id}",
    response_model=FieldResponse,
    summary="Detalhe de um talhão",
)
async def get_field(
    field_id: UUID,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
) -> Any:
    """Retorna detalhes completos de um talhão com geometria GeoJSON."""
    field = await _get_field_owned_or_404(field_id, user_id, db)
    return _field_to_response(field)


@router.get(
    "/fields/{field_id}/analyses",
    response_model=list[SatelliteAnalysisResponse],
    summary="Histórico de análises de satélite de um talhão",
)
async def list_analyses(
    field_id: UUID,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
) -> Any:
    """
    Retorna análises Sentinel-2 do talhão, ordenadas da mais recente.
    Suporta paginação via `limit` e `offset`.
    """
    await _get_field_owned_or_404(field_id, user_id, db)

    result = await db.execute(
        select(SatelliteAnalysis)
        .where(
            SatelliteAnalysis.field_id == field_id,
            SatelliteAnalysis.status == "valid",
        )
        .order_by(SatelliteAnalysis.image_date.desc())
        .limit(limit)
        .offset(offset)
    )
    return result.scalars().all()


@router.get(
    "/fields/{field_id}/analyses/latest",
    response_model=SatelliteAnalysisResponse,
    summary="Análise de satélite mais recente de um talhão",
)
async def get_latest_analysis(
    field_id: UUID,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
) -> Any:
    """
    Retorna a análise Sentinel-2 mais recente (status=valid) do talhão.
    Retorna 404 se ainda não há análises processadas.
    """
    await _get_field_owned_or_404(field_id, user_id, db)

    result = await db.execute(
        select(SatelliteAnalysis)
        .where(
            SatelliteAnalysis.field_id == field_id,
            SatelliteAnalysis.status == "valid",
        )
        .order_by(SatelliteAnalysis.image_date.desc())
        .limit(1)
    )
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(
            status_code=404,
            detail="Nenhuma análise disponível para este talhão ainda",
        )
    return analysis


@router.patch(
    "/fields/{field_id}",
    response_model=FieldResponse,
    summary="Atualizar talhão",
)
async def update_field(
    field_id: UUID,
    data: FieldUpdate,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
) -> Any:
    """Atualiza nome, cultura ou data de plantio. Apenas campos enviados são alterados."""
    field = await _get_field_owned_or_404(field_id, user_id, db)

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(field, key, value)

    await db.flush()
    await db.refresh(field)
    return _field_to_response(field)


@router.get(
    "/fields/{field_id}/anomalies",
    response_model=list,
    summary="Listar anomalias de um talhão",
)
async def list_field_anomalies(
    field_id: UUID,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
) -> Any:
    """
    Retorna anomalias detectadas no talhão.
    Parâmetro opcional: `status` (active | inspected | dismissed).
    """
    await _get_field_owned_or_404(field_id, user_id, db)

    query = (
        select(Anomaly)
        .where(Anomaly.field_id == field_id)
        .order_by(Anomaly.detected_at.desc())
    )
    if status:
        query = query.where(Anomaly.status == status)

    result = await db.execute(query)
    anomalies = result.scalars().all()

    return [
        {
            "id":               str(a.id),
            "field_id":         str(a.field_id),
            "analysis_id":      str(a.analysis_id),
            "detected_at":      a.detected_at.isoformat(),
            "ndvi_drop_pct":    a.ndvi_drop_pct,
            "affected_area_ha": a.affected_area_ha,
            "suspected_type":   a.suspected_type,
            "status":           a.status,
            "push_sent":        a.push_sent,
        }
        for a in anomalies
    ]


@router.delete(
    "/fields/{field_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Deletar talhão",
)
async def delete_field(
    field_id: UUID,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
) -> None:
    """Remove um talhão e suas análises/anomalias (cascade). Ação irreversível."""
    field = await _get_field_owned_or_404(field_id, user_id, db)
    await db.delete(field)


# ── Relatório PDF ─────────────────────────────────────────────────

@router.post(
    "/fields/{field_id}/report",
    summary="Gerar relatório PDF do talhão",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
)
async def generate_report(
    field_id: UUID,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
) -> Response:
    """
    Gera e retorna um PDF com dados NDVI, histórico de análises e anomalias do talhão.
    Requer autenticação JWT.
    """
    # Valida propriedade do talhão
    field = await _get_field_owned_or_404(field_id, user_id, db)

    # Busca a fazenda para o nome
    farm_result = await db.execute(select(Farm).where(Farm.id == field.farm_id))
    farm = farm_result.scalar_one_or_none()

    # Histórico de análises (válidas, mais recentes primeiro)
    analyses_result = await db.execute(
        select(SatelliteAnalysis)
        .where(
            SatelliteAnalysis.field_id == field_id,
            SatelliteAnalysis.status == "valid",
        )
        .order_by(SatelliteAnalysis.image_date.desc())
        .limit(24)
    )
    analyses = analyses_result.scalars().all()

    # Anomalias do talhão
    anomalies_result = await db.execute(
        select(Anomaly)
        .where(Anomaly.field_id == field_id)
        .order_by(Anomaly.detected_at.desc())
        .limit(20)
    )
    anomalies = anomalies_result.scalars().all()

    # Converte para dicts simples para o serviço de PDF
    analyses_data = [
        {
            "image_date": a.image_date,
            "ndvi_mean":  a.ndvi_mean,
            "ndvi_min":   a.ndvi_min,
            "ndvi_max":   a.ndvi_max,
            "status":     a.status,
        }
        for a in analyses
    ]
    anomalies_data = [
        {
            "detected_at":      a.detected_at,
            "ndvi_drop_pct":    a.ndvi_drop_pct,
            "affected_area_ha": a.affected_area_ha,
            "suspected_type":   a.suspected_type,
            "status":           a.status,
        }
        for a in anomalies
    ]
    latest = analyses_data[0] if analyses_data else None

    # Gera o PDF
    pdf_bytes = generate_field_report(
        field_name=field.name,
        farm_name=farm.name if farm else "—",
        crop=field.crop,
        area_ha=field.area_ha,
        planting_date=field.planting_date,
        analyses=analyses_data,
        anomalies=anomalies_data,
        latest=latest,
        field_id=str(field_id),
    )

    filename = f"relatorio_{field.name.replace(' ', '_')}_{field_id}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


class WhatsAppReportRequest(BaseModel):
    phone_number: str


@router.post(
    "/fields/{field_id}/report/whatsapp",
    summary="Enviar relatório PDF via WhatsApp",
)
async def send_report_whatsapp(
    field_id: UUID,
    body: WhatsAppReportRequest,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
) -> dict:
    """
    Gera o relatório e envia por WhatsApp para o número informado.
    Requer integração Twilio/WhatsApp Business configurada no ambiente.
    """
    # Valida propriedade do talhão
    field = await _get_field_owned_or_404(field_id, user_id, db)

    # Sanitiza o número
    phone = "".join(c for c in body.phone_number if c.isdigit() or c == "+")
    if len(phone) < 10:
        raise HTTPException(status_code=400, detail="Número de telefone inválido")

    # Tenta usar Twilio se configurado
    try:
        import os
        from twilio.rest import Client as TwilioClient

        account_sid = os.getenv("TWILIO_ACCOUNT_SID")
        auth_token  = os.getenv("TWILIO_AUTH_TOKEN")
        from_number = os.getenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")

        if not account_sid or not auth_token:
            raise ImportError("Twilio não configurado")

        client = TwilioClient(account_sid, auth_token)
        to_number = f"whatsapp:+{phone.lstrip('+')}"

        client.messages.create(
            from_=from_number,
            to=to_number,
            body=(
                f"*Relatório NDVI — Techá*\n\n"
                f"Talhão: *{field.name}*\n"
                f"Área: {field.area_ha:.1f} ha\n"
                f"Cultura: {field.crop or 'não informada'}\n\n"
                f"Acesse o app Techá para ver o relatório completo com mapa NDVI."
            ),
        )
        return {"status": "sent", "to": phone}

    except ImportError:
        # Twilio não instalado ou não configurado — retorna sucesso simulado em dev
        return {
            "status": "queued",
            "to": phone,
            "note": "Integração WhatsApp não configurada. Configure TWILIO_ACCOUNT_SID e TWILIO_AUTH_TOKEN no .env do servidor.",
        }
