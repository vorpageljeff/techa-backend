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
from pathlib import Path

import csv
import io
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse, Response, StreamingResponse
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
from app.services.kml_importer import parse_kml_polygons
from app.services.report_service import generate_field_report
from app.core.config import settings

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
    tiles_path: Optional[str] = None
    tile_url: Optional[str] = None
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


def _tile_path_for_field(field_id: UUID) -> Path:
    return Path(settings.TILES_STORAGE_PATH) / str(field_id) / "ndvi_latest.png"


def _analysis_to_response(analysis: SatelliteAnalysis) -> dict:
    tile_path = analysis.tiles_path or str(_tile_path_for_field(analysis.field_id))
    has_tile = bool(tile_path and Path(tile_path).exists())

    return {
        "id": analysis.id,
        "field_id": analysis.field_id,
        "image_date": analysis.image_date,
        "source": analysis.source,
        "cloud_cover_pct": analysis.cloud_cover_pct,
        "ndvi_mean": analysis.ndvi_mean,
        "ndvi_min": analysis.ndvi_min,
        "ndvi_max": analysis.ndvi_max,
        "tiles_path": tile_path if has_tile else analysis.tiles_path,
        "tile_url": f"/api/v1/fields/{analysis.field_id}/ndvi-tile" if has_tile else None,
        "status": analysis.status,
        "processed_at": analysis.processed_at,
    }


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


async def _check_field_limit(
    farm_id: UUID,
    db: AsyncSession,
    new_fields_count: int = 1,
) -> None:
    from sqlalchemy import func as _func
    from app.models.user import User

    plan_result = await db.execute(
        select(User.plan)
        .join(Farm, Farm.user_id == User.id)
        .where(Farm.id == farm_id)
    )
    user_plan = plan_result.scalar_one_or_none() or "free"
    field_limits = {"free": 5, "pro": 200, "admin": 9999}
    field_limit = field_limits.get(user_plan, 5)

    count_result = await db.execute(
        select(_func.count(Field.id)).where(Field.farm_id == farm_id)
    )
    current_fields = count_result.scalar_one()
    if current_fields + new_fields_count > field_limit:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Plano '{user_plan}' permite no máximo {field_limit} talhão(ões) "
                "por fazenda. Faça upgrade para adicionar mais."
            ),
        )


async def _insert_field_from_geometry(
    farm_id: UUID,
    name: str,
    crop: Optional[str],
    planting_date: Optional[date],
    geometry: dict,
    db: AsyncSession,
) -> Field:
    try:
        shapely_geom = shape(geometry)
        if not shapely_geom.is_valid:
            shapely_geom = shapely_geom.buffer(0)
        area_ha = _calc_area_ha(shapely_geom)
        wkt_text = shapely_geom.wkt
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Geometria inválida: {exc}",
        )

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
            "name": name,
            "crop": crop,
            "planting_date": planting_date,
            "geom": wkt_text,
            "area_ha": round(area_ha, 4),
            "created_at": now,
        },
    )

    result = await db.execute(select(Field).where(Field.id == field_id))
    return result.scalar_one()


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

    # ── Verificação de limite por plano ──────────────────────────
    from sqlalchemy import func as _func
    from app.models.user import User

    plan_result = await db.execute(
        select(User.plan)
        .join(Farm, Farm.user_id == User.id)
        .where(Farm.id == farm_id)
    )
    user_plan = plan_result.scalar_one_or_none() or "free"
    _FIELD_LIMITS = {"free": 5, "pro": 200, "admin": 9999}
    field_limit = _FIELD_LIMITS.get(user_plan, 5)

    count_result = await db.execute(
        select(_func.count(Field.id)).where(Field.farm_id == farm_id)
    )
    current_fields = count_result.scalar_one()
    if current_fields >= field_limit:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Plano '{user_plan}' permite no m\u00e1ximo {field_limit} talh\u00e3o(ões) por fazenda. "
                   f"Fa\u00e7a upgrade para adicionar mais.",
        )

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


@router.post(
    "/farms/{farm_id}/fields/import-kml",
    response_model=list[FieldResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Importar talhão real a partir de KML",
)
async def import_fields_from_kml(
    farm_id: UUID,
    file: UploadFile = File(...),
    name: Optional[str] = Form(None),
    crop: Optional[str] = Form(None),
    planting_date: Optional[date] = Form(None),
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
) -> list[FieldResponse]:
    """
    Importa polígonos KML exportados do Google Earth como talhões.

    Cada Placemark com Polygon vira um talhão. Se `name` for enviado, ele é
    usado quando o KML tiver apenas um polígono; caso contrário, usa o nome do
    Placemark ou o nome do arquivo.
    """
    await _get_farm_or_404(farm_id, user_id, db)

    filename = file.filename or "talhao.kml"
    if not filename.lower().endswith((".kml", ".xml")):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Envie um arquivo .kml válido.",
        )

    raw = await file.read()
    try:
        kml_text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="KML deve estar em UTF-8.",
        )

    try:
        polygons = parse_kml_polygons(kml_text)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )

    await _check_field_limit(farm_id, db, new_fields_count=len(polygons))

    created: list[FieldResponse] = []
    base_name = filename.rsplit(".", 1)[0].replace("_", " ").strip()
    for index, polygon in enumerate(polygons, start=1):
        field_name = (
            name.strip()
            if name and len(polygons) == 1
            else polygon.name or f"{base_name} {index}"
        )
        field = await _insert_field_from_geometry(
            farm_id=farm_id,
            name=field_name,
            crop=crop,
            planting_date=planting_date,
            geometry=polygon.geometry,
            db=db,
        )
        created.append(_field_to_response(field))

    return created


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
    analyses = result.scalars().all()
    return [_analysis_to_response(a) for a in analyses]


@router.get(
    "/fields/{field_id}/analyses/export",
    summary="Exportar histórico NDVI em CSV",
)
async def export_analyses_csv(
    field_id: UUID,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
) -> StreamingResponse:
    """
    Exporta todas as análises Sentinel-2 do talhão em formato CSV.
    Colunas: data, ndvi_mean, ndvi_min, ndvi_max, cloud_cover_pct, status
    """
    field = await _get_field_owned_or_404(field_id, user_id, db)

    result = await db.execute(
        select(SatelliteAnalysis)
        .where(SatelliteAnalysis.field_id == field_id)
        .order_by(SatelliteAnalysis.image_date.asc())
    )
    analyses = result.scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "data", "ndvi_medio", "ndvi_min", "ndvi_max",
        "cobertura_nuvem_pct", "status", "fonte"
    ])
    for a in analyses:
        writer.writerow([
            a.image_date,
            round(a.ndvi_mean, 4) if a.ndvi_mean is not None else "",
            round(a.ndvi_min, 4)  if a.ndvi_min  is not None else "",
            round(a.ndvi_max, 4)  if a.ndvi_max  is not None else "",
            round(a.cloud_cover_pct, 1) if a.cloud_cover_pct is not None else "",
            a.status,
            a.source,
        ])

    output.seek(0)
    filename = f"ndvi_{field.name.replace(' ', '_')}_{field_id}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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
    return _analysis_to_response(analysis)


@router.get(
    "/fields/{field_id}/ndvi-tile",
    summary="Imagem PNG NDVI mais recente de um talhao",
)
async def get_ndvi_tile(
    field_id: UUID,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
) -> FileResponse:
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
        raise HTTPException(status_code=404, detail="Tile nao disponivel")

    candidates = [
        Path(analysis.tiles_path) if analysis.tiles_path else None,
        _tile_path_for_field(field_id),
    ]
    tile_path = next((p for p in candidates if p and p.exists()), None)
    if not tile_path:
        raise HTTPException(status_code=404, detail="Tile nao disponivel")

    return FileResponse(tile_path, media_type="image/png")


@router.get(
    "/fields/{field_id}/growth-stage",
    summary="Estágio fenológico atual do talhão",
)
async def get_growth_stage(
    field_id: UUID,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
) -> dict:
    """
    Retorna o estágio fenológico atual da cultura com base na data de plantio.
    Culturas suportadas: soja, milho, trigo, algodao.
    Retorna 400 se o talhão não tiver data de plantio cadastrada.
    """
    from datetime import date as date_type

    field = await _get_field_owned_or_404(field_id, user_id, db)

    if not field.planting_date:
        raise HTTPException(
            status_code=400,
            detail="Este talhão não tem data de plantio cadastrada. "
                   "Atualize via PATCH /fields/{id}.",
        )

    crop = (field.crop or "soja").lower().replace("ã", "a").replace("ç", "c")
    today = date_type.today()
    days = (today - field.planting_date).days

    if days < 0:
        return {
            "field_id": str(field_id),
            "crop": field.crop,
            "planting_date": field.planting_date.isoformat(),
            "days_since_planting": days,
            "stage_key": "pre_plantio",
            "stage_label": "Pré-plantio",
            "stage_description": "Data de plantio futura.",
            "progress_pct": 0,
        }

    # ── Tabelas fenologicas (ASCII-safe para evitar encoding issues no deploy)
    # (dias apos plantio -> lista de estagios)
    STAGES: dict[str, list[tuple[int, str, str]]] = {
        "soja": [
            (0,   "VE",  "Emerg\u00eancia"),
            (7,   "V1",  "Primeiro trif\u00f3lio"),
            (20,  "V3",  "Terceiro trif\u00f3lio"),
            (35,  "V5",  "Quinto trif\u00f3lio"),
            (45,  "R1",  "In\u00edcio do florescimento"),
            (55,  "R3",  "In\u00edcio da frutifica\u00e7\u00e3o"),
            (70,  "R5",  "In\u00edcio do enchimento de gr\u00e3o"),
            (90,  "R6",  "Gr\u00e3o cheio"),
            (110, "R7",  "In\u00edcio da matura\u00e7\u00e3o"),
            (125, "R8",  "Matura\u00e7\u00e3o plena"),
        ],
        "milho": [
            (0,   "VE",  "Emerg\u00eancia"),
            (10,  "V3",  "Terceira folha"),
            (25,  "V6",  "Sexta folha"),
            (40,  "V10", "D\u00e9cima folha"),
            (55,  "VT",  "Pendoamento"),
            (62,  "R1",  "Espigamento / Silagem"),
            (75,  "R2",  "Gr\u00e3o bolhoso"),
            (90,  "R4",  "Gr\u00e3o pastoso"),
            (105, "R5",  "Gr\u00e3o farin\u00e1ceo"),
            (120, "R6",  "Matura\u00e7\u00e3o fisiol\u00f3gica"),
        ],
        "trigo": [
            (0,   "Z10", "Germina\u00e7\u00e3o"),
            (15,  "Z13", "Tr\u00eas folhas"),
            (30,  "Z21", "In\u00edcio do afilhamento"),
            (50,  "Z30", "In\u00edcio do alongamento"),
            (65,  "Z51", "In\u00edcio da espiga\u00e7\u00e3o"),
            (75,  "Z60", "Florescimento"),
            (90,  "Z71", "Gr\u00e3o aquoso"),
            (105, "Z83", "Gr\u00e3o farin\u00e1ceo"),
            (120, "Z87", "Gr\u00e3o duro"),
            (130, "Z92", "Matura\u00e7\u00e3o plena"),
        ],
        "algodao": [
            (0,   "VE",  "Emerg\u00eancia"),
            (15,  "V1",  "Cotil\u00e9dones abertos"),
            (30,  "V3",  "Terceiro n\u00f3"),
            (50,  "B1",  "Primeiro bot\u00e3o floral"),
            (70,  "FL",  "Pleno florescimento"),
            (90,  "C1",  "Primeiro capulho"),
            (110, "C3",  "Capulhos desenvolvidos"),
            (130, "M",   "In\u00edcio da abertura"),
            (150, "MA",  "Matura\u00e7\u00e3o plena"),
        ],
    }

    # Fallback para soja se cultura não mapeada
    stages = STAGES.get(crop, STAGES["soja"])
    total_days = stages[-1][0]

    # Determina estágio atual
    current_stage = stages[0]
    for stage in stages:
        if days >= stage[0]:
            current_stage = stage
        else:
            break

    # Progresso dentro do ciclo
    progress_pct = min(round((days / total_days) * 100, 1), 100.0)

    # Próximo estágio
    current_idx = stages.index(current_stage)
    next_stage = stages[current_idx + 1] if current_idx + 1 < len(stages) else None
    days_to_next = (next_stage[0] - days) if next_stage else None

    return {
        "field_id":              str(field_id),
        "crop":                  field.crop,
        "planting_date":         field.planting_date.isoformat(),
        "days_since_planting":   days,
        "stage_key":             current_stage[1],
        "stage_label":           current_stage[2],
        "stage_description":     f"Estagio {current_stage[1]}: {current_stage[2]}",
        "progress_pct":          progress_pct,
        "next_stage_key":        next_stage[1] if next_stage else None,
        "next_stage_label":      next_stage[2] if next_stage else None,
        "days_to_next_stage":    days_to_next,
        "cycle_complete":        days >= total_days,
    }


@router.get(
    "/fields/{field_id}/ndvi-history",
    summary="Série histórica de NDVI para gráfico",
)
async def get_ndvi_history(
    field_id: UUID,
    limit: int = Query(90, ge=1, le=365, description="Máximo de pontos (dias)"),
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
) -> dict:
    """
    Retorna a série temporal de NDVI do talhão, otimizada para renderização
    de gráfico no app mobile. Cada ponto contém:
    - date: data da imagem (ISO 8601)
    - ndvi_mean / ndvi_min / ndvi_max: valores NDVI
    - cloud_cover_pct: cobertura de nuvem (%)
    - status: indicador de saúde (critico / alerta / normal / excelente)
    """
    await _get_field_owned_or_404(field_id, user_id, db)

    result = await db.execute(
        select(SatelliteAnalysis)
        .where(
            SatelliteAnalysis.field_id == field_id,
            SatelliteAnalysis.status == "valid",
        )
        .order_by(SatelliteAnalysis.image_date.asc())
        .limit(limit)
    )
    analyses = result.scalars().all()

    points = [
        {
            "date":            a.image_date.isoformat(),
            "ndvi_mean":       round(a.ndvi_mean, 4) if a.ndvi_mean is not None else None,
            "ndvi_min":        round(a.ndvi_min, 4)  if a.ndvi_min  is not None else None,
            "ndvi_max":        round(a.ndvi_max, 4)  if a.ndvi_max  is not None else None,
            "cloud_cover_pct": round(a.cloud_cover_pct, 1) if a.cloud_cover_pct is not None else None,
            "status":          _ndvi_status_label(a.ndvi_mean),
        }
        for a in analyses
    ]

    # Calcula tendência simples (último vs penúltimo)
    trend = None
    if len(points) >= 2:
        last, prev = points[-1]["ndvi_mean"], points[-2]["ndvi_mean"]
        if last is not None and prev is not None and prev != 0:
            change_pct = round(((last - prev) / prev) * 100, 1)
            trend = "up" if change_pct > 2 else "down" if change_pct < -2 else "stable"

    return {
        "field_id":   str(field_id),
        "data_points": len(points),
        "trend":       trend,
        "series":      points,
    }


def _ndvi_status_label(ndvi: float | None) -> str:
    if ndvi is None:  return "sem_dados"
    if ndvi < 0.2:    return "critico"
    if ndvi < 0.4:    return "alerta"
    if ndvi < 0.6:    return "normal"
    return "excelente"


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
