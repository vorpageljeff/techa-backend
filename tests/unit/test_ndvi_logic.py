# tests/unit/test_ndvi_logic.py
# Testes unitários para a lógica de cálculo NDVI e detecção de anomalia
# Estes testes NÃO dependem de imagens reais — usam arrays NumPy

import pytest
import numpy as np


# ── Funções que serão implementadas no pipeline ───────────────────
# (Testadas aqui ANTES de implementar — TDD puro)

def calculate_ndvi(nir: np.ndarray, red: np.ndarray) -> np.ndarray:
    """NDVI = (NIR - RED) / (NIR + RED)"""
    nir = nir.astype(float)
    red = red.astype(float)
    denominator = nir + red
    with np.errstate(divide="ignore", invalid="ignore"):
        ndvi = np.where(denominator == 0, np.nan, (nir - red) / denominator)
    return ndvi


def calculate_ndvi_drop(
    ndvi_before: np.ndarray,
    ndvi_after: np.ndarray,
) -> np.ndarray:
    """Queda percentual de NDVI pixel a pixel"""
    with np.errstate(divide="ignore", invalid="ignore"):
        drop = np.where(
            (ndvi_before == 0) | np.isnan(ndvi_before) | np.isnan(ndvi_after),
            np.nan,
            ((ndvi_before - ndvi_after) / ndvi_before) * 100,
        )
    return drop


def get_alert_area_threshold(area_ha: float, settings_obj=None) -> float:
    """Retorna o % mínimo de área afetada para disparar alerta"""
    if area_ha <= 100:
        return 3.0
    elif area_ha <= 500:
        return 2.0
    else:
        return max(1.5, (10.0 / area_ha) * 100)  # mín 10ha absoluto


class TestNDVICalculation:
    def test_healthy_vegetation(self):
        """Vegetação saudável deve ter NDVI próximo de +1"""
        nir = np.array([[8000, 7500]], dtype=float)
        red = np.array([[1000, 1200]], dtype=float)
        ndvi = calculate_ndvi(nir, red)
        assert np.all(ndvi > 0.6), "Vegetação saudável deve ter NDVI > 0.6"

    def test_bare_soil(self):
        """Solo exposto deve ter NDVI próximo de 0"""
        nir = np.array([[3000]], dtype=float)
        red = np.array([[2800]], dtype=float)
        ndvi = calculate_ndvi(nir, red)
        assert abs(ndvi[0][0]) < 0.1, "Solo exposto deve ter NDVI próximo de 0"

    def test_ndvi_range(self):
        """NDVI sempre deve estar entre -1 e +1"""
        nir = np.random.randint(100, 10000, (50, 50)).astype(float)
        red = np.random.randint(100, 10000, (50, 50)).astype(float)
        ndvi = calculate_ndvi(nir, red)
        valid = ndvi[~np.isnan(ndvi)]
        assert np.all(valid >= -1.0) and np.all(valid <= 1.0)

    def test_zero_denominator_returns_nan(self):
        """NIR = RED = 0 deve retornar NaN (não dividir por zero)"""
        nir = np.array([[0]], dtype=float)
        red = np.array([[0]], dtype=float)
        ndvi = calculate_ndvi(nir, red)
        assert np.isnan(ndvi[0][0])


class TestNDVIDropDetection:
    def test_detects_drop_above_threshold(self):
        """Queda de 20% deve ser detectada"""
        before = np.array([[0.80]])
        after  = np.array([[0.64]])  # queda de 20%
        drop = calculate_ndvi_drop(before, after)
        assert drop[0][0] == pytest.approx(20.0, abs=0.1)

    def test_no_drop_returns_zero(self):
        """Sem queda, drop deve ser 0 ou negativo"""
        before = np.array([[0.70]])
        after  = np.array([[0.75]])  # NDVI aumentou
        drop = calculate_ndvi_drop(before, after)
        assert drop[0][0] < 0

    def test_nan_propagation(self):
        """Pixel mascarado (NaN) não deve gerar alerta"""
        before = np.array([[0.80, np.nan]])
        after  = np.array([[0.60, 0.50]])
        drop = calculate_ndvi_drop(before, after)
        assert not np.isnan(drop[0][0])  # pixel válido calculado
        assert np.isnan(drop[0][1])      # pixel NaN propagado


class TestAlertThreshold:
    def test_small_field_threshold(self):
        """Talhão de 80ha → threshold de 3%"""
        assert get_alert_area_threshold(80) == 3.0

    def test_medium_field_threshold(self):
        """Talhão de 300ha → threshold de 2%"""
        assert get_alert_area_threshold(300) == 2.0

    def test_large_field_threshold(self):
        """Talhão de 1000ha → threshold calculado com mín de 10ha"""
        threshold = get_alert_area_threshold(1000)
        min_ha = (threshold / 100) * 1000
        assert min_ha >= 10.0, "Área mínima absoluta deve ser >= 10ha"

    def test_boundary_100ha(self):
        """Exatamente 100ha → threshold de 3% (borda do range)"""
        assert get_alert_area_threshold(100) == 3.0

    def test_boundary_101ha(self):
        """101ha → threshold de 2% (próximo range)"""
        assert get_alert_area_threshold(101) == 2.0
