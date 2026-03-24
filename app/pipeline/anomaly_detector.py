# ─────────────────────────────────────────────────────────────────
# app/pipeline/anomaly_detector.py
# Motor de detecção de anomalias — regra de negócio central do Techá
#
# ALERTA disparado quando TODOS os 3 critérios forem verdadeiros:
#   1. NDVI caiu > 15% vs semana anterior
#   2. Área afetada >= threshold dinâmico do talhão:
#        <= 100ha  → 3% da área
#        <= 500ha  → 2% da área
#        >  500ha  → 1.5% (mínimo absoluto de 10ha)
#   3. Cobertura de nuvem < 20% (garantida pelo preprocessor)
# ─────────────────────────────────────────────────────────────────

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from loguru import logger

from app.pipeline.ndvi import NDVIStats


def get_area_threshold(field_area_ha: float) -> float:
    """
    Retorna o percentual mínimo de área afetada para disparar alerta.

    Regra de negócio (validada com agrônomo):
        Até 100ha    → 3% da área
        100 a 500ha  → 2% da área
        Acima 500ha  → 1.5% (com mínimo absoluto de 10ha)

    Args:
        field_area_ha: área total do talhão em hectares

    Returns:
        Percentual threshold (ex: 3.0 representa 3%)
    """
    if field_area_ha <= 100.0:
        return 3.0
    elif field_area_ha <= 500.0:
        return 2.0
    else:
        # Para talhões grandes, garante no mínimo 10ha afetados
        min_pct_for_10ha = (10.0 / field_area_ha) * 100.0
        return max(1.5, min_pct_for_10ha)


def should_alert(
    stats: NDVIStats,
    field_area_ha: float,
    cloud_cover_pct: float,
    ndvi_drop_threshold: float = 15.0,
    cloud_cover_max: float = 20.0,
) -> tuple[bool, str]:
    """
    Avalia os 3 critérios de alerta.

    Returns:
        (deve_alertar, motivo_textual)
    """
    reasons = []

    # Critério 1: queda de NDVI > 15%
    if stats.ndvi_drop_pct <= ndvi_drop_threshold:
        return False, f"NDVI drop {stats.ndvi_drop_pct:.1f}% abaixo do limiar {ndvi_drop_threshold}%"

    # Critério 2: área afetada >= threshold dinâmico
    threshold_pct = get_area_threshold(field_area_ha)
    min_area_ha = (threshold_pct / 100.0) * field_area_ha

    if stats.affected_area_ha < min_area_ha:
        return (
            False,
            f"Área afetada {stats.affected_area_ha:.2f}ha < mínimo {min_area_ha:.2f}ha "
            f"({threshold_pct}% de {field_area_ha:.0f}ha)",
        )

    # Critério 3: cobertura de nuvem < 20% (já garantida pelo preprocessor,
    # mas verificamos novamente por segurança)
    if cloud_cover_pct >= cloud_cover_max:
        return False, f"Cobertura de nuvem {cloud_cover_pct:.1f}% >= {cloud_cover_max}%"

    reason = (
        f"NDVI drop={stats.ndvi_drop_pct:.1f}% | "
        f"área afetada={stats.affected_area_ha:.2f}ha ({threshold_pct}% threshold) | "
        f"nuvem={cloud_cover_pct:.1f}%"
    )
    return True, reason


async def save_analysis(
    field_id: UUID,
    image_date,
    stats: NDVIStats,
    cloud_cover_pct: float,
    raster_path: Optional[str],
    db,
) -> "SatelliteAnalysis":
    """
    Salva o registro de análise de satélite no banco.

    Returns:
        Objeto SatelliteAnalysis criado.
    """
    from sqlalchemy import select
    from app.models.satellite_analysis import SatelliteAnalysis

    analysis = SatelliteAnalysis(
        field_id=field_id,
        image_date=image_date,
        source="sentinel-2-l2a",
        cloud_cover_pct=cloud_cover_pct,
        ndvi_mean=stats.ndvi_mean,
        ndvi_min=stats.ndvi_min,
        ndvi_max=stats.ndvi_max,
        raster_path=raster_path,
        status="valid",
    )
    db.add(analysis)
    await db.flush()
    await db.refresh(analysis)
    logger.info(
        f"SatelliteAnalysis salvo: field={field_id} | "
        f"date={image_date} | ndvi={stats.ndvi_mean:.3f}"
    )
    return analysis


async def detect_and_save(
    field_id: UUID,
    field_area_ha: float,
    analysis,
    stats: NDVIStats,
    cloud_cover_pct: float,
    db,
    user_fcm_token: Optional[str] = None,
    user_email: Optional[str] = None,
    user_name: str = "",
    farm_name: str = "",
    field_name: str = "",
) -> Optional["Anomaly"]:
    """
    Avalia os critérios de alerta e salva anomalia no banco se necessário.
    Se anomalia detectada e user_fcm_token fornecido, envia push FCM.

    Args:
        field_id:        UUID do talhão
        field_area_ha:   área total do talhão (para calcular threshold)
        analysis:        SatelliteAnalysis já salvo
        stats:           NDVIStats calculados
        cloud_cover_pct: cobertura de nuvem da cena
        db:              sessão async do SQLAlchemy
        user_fcm_token:  token FCM do usuário (opcional)
        farm_name:       nome da fazenda para notificação
        field_name:      nome do talhão para notificação

    Returns:
        Anomaly criado ou None se não houver alerta.
    """
    alert, reason = should_alert(stats, field_area_ha, cloud_cover_pct)

    if not alert:
        logger.info(f"Sem anomalia detectada para field={field_id}: {reason}")
        return None

    logger.warning(
        f"[ANOMALIA] DETECTADA | field={field_id} | {reason}"
    )

    from app.models.anomaly import Anomaly

    anomaly = Anomaly(
        analysis_id=analysis.id,
        field_id=field_id,
        ndvi_drop_pct=stats.ndvi_drop_pct,
        affected_area_ha=stats.affected_area_ha,
        suspected_type="unknown",    # classificação futura por IA
        status="active",
        push_sent=False,
        detected_at=datetime.now(timezone.utc),
    )
    db.add(anomaly)
    await db.flush()
    await db.refresh(anomaly)

    logger.info(f"Anomalia salva: id={anomaly.id} | status=active")

    _farm  = farm_name  or "Fazenda"
    _field = field_name or "Talh\u00e3o"
    alert_sent = False

    # ── Push FCM (mobile) ────────────────────────────────────────
    if user_fcm_token:
        try:
            from app.services.notification import notify_anomaly
            push_sent = await notify_anomaly(
                fcm_token=user_fcm_token,
                farm_name=_farm,
                field_name=_field,
                ndvi_drop_pct=stats.ndvi_drop_pct,
                anomaly_id=str(anomaly.id),
            )
            if push_sent:
                alert_sent = True
        except Exception as exc:
            logger.error(f"Falha ao enviar FCM para anomalia {anomaly.id}: {exc}")

    # ── E-mail (fallback / adicional ao FCM) ─────────────────────
    if user_email:
        try:
            import asyncio
            from app.core.email import send_anomaly_alert
            # send_anomaly_alert é síncrono — executa em thread pool
            loop = asyncio.get_event_loop()
            email_sent = await loop.run_in_executor(
                None,
                send_anomaly_alert,
                user_email,
                user_name or "Produtor",
                _farm,
                _field,
                stats.ndvi_drop_pct,
                stats.affected_area_ha,
                str(anomaly.id),
            )
            if email_sent:
                alert_sent = True
        except Exception as exc:
            logger.error(f"Falha ao enviar e-mail para anomalia {anomaly.id}: {exc}")

    if alert_sent:
        anomaly.push_sent = True
        anomaly.alert_sent_at = datetime.now(timezone.utc)
        await db.flush()

    return anomaly
