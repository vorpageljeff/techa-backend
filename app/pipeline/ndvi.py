# ─────────────────────────────────────────────────────────────────
# app/pipeline/ndvi.py
# Cálculo de NDVI e estatísticas para detecção de anomalias
# NDVI = (NIR - RED) / (NIR + RED)  — valores entre -1 e +1
# ─────────────────────────────────────────────────────────────────

from typing import Optional, NamedTuple
from uuid import UUID

import numpy as np
from loguru import logger


class NDVIStats(NamedTuple):
    """Estatísticas NDVI de uma cena processada."""
    ndvi_mean: float            # NDVI médio do talhão (pixels válidos)
    ndvi_min: float             # NDVI mínimo
    ndvi_max: float             # NDVI máximo
    ndvi_drop_pct: float        # queda percentual vs semana anterior (0 se sem baseline)
    affected_area_ha: float     # área com queda > threshold (em hectares)
    pixel_resolution_m: float   # resolução do pixel (10m para B04/B08)


def calculate_ndvi(b04: np.ndarray, b08: np.ndarray) -> np.ndarray:
    """
    Calcula NDVI pixel a pixel.

    NDVI = (NIR - RED) / (NIR + RED)
    Pixels com denominador zero ou NaN retornam NaN.

    Args:
        b04: array float32 da banda RED (B04)
        b08: array float32 da banda NIR (B08)

    Returns:
        Array float32 com NDVI (-1 a +1, NaN onde inválido).
    """
    b04 = b04.astype(np.float64)
    b08 = b08.astype(np.float64)
    denominator = b08 + b04

    with np.errstate(divide="ignore", invalid="ignore"):
        ndvi = np.where(
            (denominator == 0) | np.isnan(denominator),
            np.nan,
            (b08 - b04) / denominator,
        )

    return ndvi.astype(np.float32)


def calculate_ndvi_drop(
    ndvi_current: np.ndarray,
    ndvi_baseline: np.ndarray,
) -> np.ndarray:
    """
    Calcula a queda percentual de NDVI pixel a pixel.

    drop_pct = ((baseline - current) / baseline) * 100

    Pixels onde baseline <= 0 ou qualquer um é NaN retornam NaN.
    """
    with np.errstate(divide="ignore", invalid="ignore"):
        drop = np.where(
            (ndvi_baseline <= 0) | np.isnan(ndvi_baseline) | np.isnan(ndvi_current),
            np.nan,
            ((ndvi_baseline - ndvi_current) / ndvi_baseline) * 100.0,
        )
    return drop.astype(np.float32)


def compute_ndvi_stats(
    b04: np.ndarray,
    b08: np.ndarray,
    field_area_ha: float,
    baseline_ndvi_mean: Optional[float] = None,
    pixel_resolution_m: float = 10.0,
    ndvi_drop_threshold_pct: float = 15.0,
) -> NDVIStats:
    """
    Calcula estatísticas NDVI e detecta área afetada.

    Args:
        b04:                  banda RED pré-processada (NaN em pixels inválidos)
        b08:                  banda NIR pré-processada
        field_area_ha:        área total do talhão em hectares
        baseline_ndvi_mean:   NDVI médio da semana anterior (None se não houver)
        pixel_resolution_m:   resolução do pixel em metros (10m para Sentinel-2 B04/B08)
        ndvi_drop_threshold_pct: limiar de queda para considerar pixel "afetado"

    Returns:
        NDVIStats com todas as métricas calculadas.
    """
    ndvi = calculate_ndvi(b04, b08)
    valid_pixels = ndvi[~np.isnan(ndvi)]

    if valid_pixels.size == 0:
        logger.warning("Nenhum pixel válido após SCL mask — NDVI não calculável")
        return NDVIStats(
            ndvi_mean=0.0,
            ndvi_min=0.0,
            ndvi_max=0.0,
            ndvi_drop_pct=0.0,
            affected_area_ha=0.0,
            pixel_resolution_m=pixel_resolution_m,
        )

    ndvi_mean = float(np.nanmean(ndvi))
    ndvi_min = float(np.nanmin(ndvi))
    ndvi_max = float(np.nanmax(ndvi))

    # Calcula queda percentual vs baseline
    ndvi_drop_pct = 0.0
    affected_area_ha = 0.0

    if baseline_ndvi_mean is not None and baseline_ndvi_mean > 0:
        ndvi_drop_pct = max(
            0.0,
            ((baseline_ndvi_mean - ndvi_mean) / baseline_ndvi_mean) * 100.0,
        )

        # Cria array baseline artificial (baseline uniforme, simplificação do MVP)
        # Em versão futura, usar mapa de NDVI pixel-a-pixel da semana anterior
        baseline_arr = np.full_like(ndvi, fill_value=baseline_ndvi_mean, dtype=np.float32)
        drop_map = calculate_ndvi_drop(ndvi, baseline_arr)

        # Pixels com queda > threshold E válidos
        affected_mask = (drop_map > ndvi_drop_threshold_pct) & ~np.isnan(drop_map)
        affected_pixels = int(np.sum(affected_mask))

        # Área: pixels × resolução² → m² → ha
        pixel_area_ha = (pixel_resolution_m ** 2) / 10_000.0
        affected_area_ha = affected_pixels * pixel_area_ha

        logger.info(
            f"NDVI atual={ndvi_mean:.3f} | baseline={baseline_ndvi_mean:.3f} | "
            f"queda={ndvi_drop_pct:.1f}% | área afetada={affected_area_ha:.2f}ha"
        )
    else:
        logger.info(f"NDVI atual={ndvi_mean:.3f} | sem baseline para comparação")

    return NDVIStats(
        ndvi_mean=round(ndvi_mean, 4),
        ndvi_min=round(ndvi_min, 4),
        ndvi_max=round(ndvi_max, 4),
        ndvi_drop_pct=round(ndvi_drop_pct, 2),
        affected_area_ha=round(affected_area_ha, 4),
        pixel_resolution_m=pixel_resolution_m,
    )


async def get_baseline_ndvi(field_id: UUID, db) -> Optional[float]:
    """
    Busca o NDVI médio da análise mais recente dos últimos 14 dias.
    Usado como baseline para calcular a queda.

    Returns:
        float com NDVI médio ou None se não houver análise anterior.
    """
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import select
    from app.models.satellite_analysis import SatelliteAnalysis

    cutoff = datetime.now(timezone.utc) - timedelta(days=14)

    result = await db.execute(
        select(SatelliteAnalysis.ndvi_mean)
        .where(
            SatelliteAnalysis.field_id == field_id,
            SatelliteAnalysis.status == "valid",
            SatelliteAnalysis.processed_at >= cutoff,
            SatelliteAnalysis.ndvi_mean.isnot(None),
        )
        .order_by(SatelliteAnalysis.processed_at.desc())
        .limit(1)
    )
    row = result.scalar_one_or_none()
    return float(row) if row is not None else None
