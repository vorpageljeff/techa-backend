from app.pipeline.anomaly_detector import should_alert
from app.pipeline.ndvi import NDVIStats


def make_stats(ndvi_mean: float, ndvi_drop_pct: float = 0.0, affected_area_ha: float = 0.0) -> NDVIStats:
    return NDVIStats(
        ndvi_mean=ndvi_mean,
        ndvi_min=ndvi_mean,
        ndvi_max=ndvi_mean,
        ndvi_drop_pct=ndvi_drop_pct,
        affected_area_ha=affected_area_ha,
        pixel_resolution_m=10.0,
    )


def test_low_ndvi_mean_triggers_alert_without_baseline_drop():
    alert, reason = should_alert(
        make_stats(ndvi_mean=0.206),
        field_area_ha=10.0,
        cloud_cover_pct=0.0,
    )

    assert alert is True
    assert "NDVI" in reason


def test_normal_ndvi_without_drop_does_not_trigger_alert():
    alert, reason = should_alert(
        make_stats(ndvi_mean=0.514),
        field_area_ha=10.0,
        cloud_cover_pct=0.0,
    )

    assert alert is False
    assert "abaixo do limiar" in reason
