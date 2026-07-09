# ─────────────────────────────────────────────────────────────────
# app/pipeline/scheduler.py
# Agendador do pipeline Sentinel-2 — roda a cada 30 minutos
# Usa AsyncIOScheduler para funcionar no loop asyncio do FastAPI
# ─────────────────────────────────────────────────────────────────

from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from loguru import logger


def start_scheduler() -> AsyncIOScheduler:
    """
    Inicia o scheduler assíncrono e registra o job do pipeline.
    Chamado no lifespan do FastAPI (app/main.py).
    """
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        run_pipeline_cycle,
        trigger="interval",
        minutes=30,
        id="sentinel_pipeline",
        replace_existing=True,
        max_instances=1,        # evita execuções sobrepostas
        misfire_grace_time=300, # tolera atraso de até 5 min antes de pular
        next_run_time=datetime.now(timezone.utc),
    )
    scheduler.start()
    logger.info("✅ Scheduler Sentinel-2 iniciado — ciclo a cada 30 minutos")
    return scheduler


async def run_pipeline_cycle() -> None:
    """
    Ciclo principal do pipeline: itera sobre todos os talhões ativos
    e processa as imagens Sentinel-2 disponíveis.

    Executado automaticamente pelo scheduler a cada 30 minutos.
    """
    logger.info("[PIPELINE] Iniciando ciclo Sentinel-2...")

    from sqlalchemy import select
    from app.core.database import AsyncSessionLocal
    from app.models.field import Field
    from app.models.farm import Farm
    from app.models.user import User

    try:
        async with AsyncSessionLocal() as db:
            # Busca talhões com fazenda, user e fcm_token em uma query
            result = await db.execute(
                select(Field, Farm.name, User.fcm_token, User.email, User.name)
                .join(Farm, Field.farm_id == Farm.id)
                .join(User, Farm.user_id == User.id)
                .where(Farm.user_id.isnot(None))
            )
            rows = result.all()

        if not rows:
            logger.info("Nenhum talhão cadastrado — ciclo encerrado")
            return

        logger.info(f"Processando {len(rows)} talhão(ões)...")
        ok, errors = 0, 0

        for field, farm_name, user_fcm_token, user_email, user_name in rows:
            success = await _process_field(
                field=field,
                farm_name=farm_name or "",
                user_fcm_token=user_fcm_token,
                user_email=user_email,
                user_name=user_name or "",
            )
            if success:
                ok += 1
            else:
                errors += 1

        logger.info(
            f"[PIPELINE] Ciclo concluído: {ok} sucesso(s), {errors} erro(s) "
            f"de {len(rows)} talhão(ões)"
        )

    except Exception as exc:
        logger.error(f"Erro crítico no ciclo do pipeline: {exc}")


async def _process_field(
    field: "Field",
    farm_name: str = "",
    user_fcm_token: Optional[str] = None,
    user_email: Optional[str] = None,
    user_name: str = "",
) -> bool:
    """
    Processa o pipeline completo para um único talhão.

    Fluxo:
      1. Calcula bbox do talhão a partir da geometria WKT
      2. Busca imagens Sentinel-2 disponíveis (STAC)
      3. Baixa bandas B04, B08, SCL
      4. Aplica SCL mask (descarta se nuvem > 20%)
      5. Calcula NDVI e estatísticas
      6. Salva SatelliteAnalysis no banco
      7. Detecta anomalia e salva se necessário
      8. Envia push FCM + e-mail se anomalia detectada

    Returns:
        True se processado com sucesso, False em caso de erro.
    """
    from app.core.database import AsyncSessionLocal
    from app.pipeline.downloader import search_images, download_bands
    from app.pipeline.preprocessor import apply_scl_mask
    from app.pipeline.ndvi import compute_ndvi_stats, get_baseline_ndvi
    from app.pipeline.anomaly_detector import save_analysis, detect_and_save
    from app.pipeline.tiles import generate_ndvi_png

    field_id = field.id
    field_area_ha = field.area_ha or 0.0
    field_name = field.name or ""

    try:
        # ── 1. Calcula bbox do talhão ─────────────────────────────
        bbox = _get_field_bbox(field)
        if bbox is None:
            logger.warning(f"Talhão {field_id} sem geometria válida — pulando")
            return False

        # ── 2. Busca imagens disponíveis ──────────────────────────
        items = search_images(bbox, days_back=60)
        if not items:
            logger.info(f"Talhão {field_id}: nenhuma imagem disponível nos ultimos 60 dias")
            return True  # não é erro, apenas sem imagem nova

        # Usa a imagem mais recente (itens já ordenados por data)
        stac_item = items[0]
        image_date = stac_item.datetime.date()

        # Verifica se já processamos esta data para este talhão
        already_processed = await _is_already_processed(field_id, image_date)
        if already_processed:
            logger.debug(f"Talhão {field_id}: imagem {image_date} já processada")
            return True

        logger.info(f"Talhão {field_id}: processando imagem de {image_date}")

        # ── 3. Baixa bandas ───────────────────────────────────────
        band_paths = download_bands(stac_item, str(field_id))
        if band_paths is None:
            logger.error(f"Talhão {field_id}: falha no download das bandas")
            return False

        # ── 4. SCL Mask + cobertura de nuvem ─────────────────────
        clip_geom = _get_field_shapely(field)
        preproc = apply_scl_mask(band_paths, clip_geom=clip_geom)
        if preproc is None:
            # Imagem descartada por excesso de nuvem
            async with AsyncSessionLocal() as db:
                from app.models.satellite_analysis import SatelliteAnalysis
                discarded = SatelliteAnalysis(
                    field_id=field_id,
                    image_date=image_date,
                    source="sentinel-2-l2a",
                    status="discarded_cloud",
                )
                db.add(discarded)
                await db.commit()  # flush não persiste sem commit
            return True

        # ── 5. NDVI + estatísticas ────────────────────────────────
        async with AsyncSessionLocal() as db:
            baseline_ndvi = await get_baseline_ndvi(field_id, db)

        stats = compute_ndvi_stats(
            b04=preproc.b04,
            b08=preproc.b08,
            field_area_ha=field_area_ha,
            baseline_ndvi_mean=baseline_ndvi,
        )
        tiles_path = generate_ndvi_png(
            b04=preproc.b04,
            b08=preproc.b08,
            field_id=field_id,
            bounds=bbox,
        )

        # ── 6. Salva análise + 7. Detecta anomalia + 8. FCM ──────
        async with AsyncSessionLocal() as db:
            raster_path = str(band_paths.get("B08", ""))
            analysis = await save_analysis(
                field_id=field_id,
                image_date=image_date,
                stats=stats,
                cloud_cover_pct=preproc.cloud_cover_pct,
                raster_path=raster_path,
                db=db,
                tiles_path=tiles_path,
            )

            if baseline_ndvi is not None:
                await detect_and_save(
                    field_id=field_id,
                    field_area_ha=field_area_ha,
                    analysis=analysis,
                    stats=stats,
                    cloud_cover_pct=preproc.cloud_cover_pct,
                    db=db,
                    user_fcm_token=user_fcm_token,
                    user_email=user_email,
                    user_name=user_name,
                    farm_name=farm_name,
                    field_name=field_name,
                )

            await db.commit()  # persiste analysis + anomalia (flush não é suficiente)

        logger.info(f"[OK] Talhão {field_id} processado com sucesso ({image_date})")
        return True

    except ImportError as exc:
        # rasterio ou outra dependência de sistema não instalada
        logger.warning(f"Dependência de sistema não disponível: {exc}")
        return False
    except Exception as exc:
        logger.error(f"Erro ao processar talhão {field_id}: {exc}")
        return False


def _get_field_bbox(field) -> Optional[list[float]]:
    """Extrai bbox [min_lon, min_lat, max_lon, max_lat] da geometria do talhão (WKT)."""
    if not field.geometry:
        return None
    try:
        from shapely import wkt as shapely_wkt
        geom = shapely_wkt.loads(field.geometry)
        bounds = geom.bounds   # (minx, miny, maxx, maxy)
        return list(bounds)
    except Exception as exc:
        logger.error(f"Erro ao extrair bbox do talhão {field.id}: {exc}")
        return None


def _get_field_shapely(field):
    """Retorna geometria Shapely do talhão para recorte do raster."""
    if not field.geometry:
        return None
    try:
        from shapely import wkt as shapely_wkt
        return shapely_wkt.loads(field.geometry)
    except Exception:
        return None


async def _is_already_processed(field_id: UUID, image_date) -> bool:
    """Verifica se já existe SatelliteAnalysis para este talhão e data."""
    from sqlalchemy import select
    from app.core.database import AsyncSessionLocal
    from app.models.satellite_analysis import SatelliteAnalysis

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(SatelliteAnalysis).where(
                SatelliteAnalysis.field_id == field_id,
                SatelliteAnalysis.image_date == image_date,
            ).order_by(SatelliteAnalysis.processed_at.desc()).limit(1)
        )
        analysis = result.scalar_one_or_none()
        if not analysis:
            return False

        return bool(analysis.tiles_path and Path(analysis.tiles_path).exists())
