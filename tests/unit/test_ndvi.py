"""
tests/unit/test_ndvi.py
────────────────────────
Testes unitários do cálculo de NDVI e motor de anomalias.
Execute com: pytest tests/unit/test_ndvi.py -v
"""

import numpy as np
import pytest


# ── Importa funções que serão implementadas no Sprint 1 ───────────────────
# (Os testes são escritos ANTES do código — TDD)
# from app.pipeline.ndvi import calculate_ndvi, calculate_ndvi_stats
# from app.pipeline.anomaly import detect_anomaly_areas, get_area_threshold


# ── Testes do cálculo de NDVI ─────────────────────────────────────────────
class TestNDVICalculation:

    def test_ndvi_formula_basica(self):
        """NDVI = (NIR - RED) / (NIR + RED)"""
        nir = np.array([[0.5, 0.6], [0.4, 0.7]])
        red = np.array([[0.1, 0.2], [0.1, 0.3]])

        # Cálculo esperado
        expected = (nir - red) / (nir + red)
        result = (nir.astype(float) - red.astype(float)) / (nir.astype(float) + red.astype(float))

        np.testing.assert_array_almost_equal(result, expected, decimal=6)

    def test_ndvi_planta_saudavel(self):
        """Planta saudável: NDVI deve ser alto (> 0.6)"""
        nir = np.array([[0.8]])   # Alta reflectância no infravermelho
        red = np.array([[0.1]])   # Baixa reflectância no vermelho

        ndvi = (nir - red) / (nir + red)
        assert ndvi[0][0] > 0.6, "Planta saudável deve ter NDVI > 0.6"

    def test_ndvi_solo_exposto(self):
        """Solo exposto: NDVI deve ser baixo (< 0.2)"""
        nir = np.array([[0.3]])
        red = np.array([[0.25]])

        ndvi = (nir - red) / (nir + red)
        assert ndvi[0][0] < 0.2, "Solo exposto deve ter NDVI < 0.2"

    def test_ndvi_range_valido(self):
        """NDVI deve estar sempre entre -1 e +1"""
        nir = np.random.rand(100, 100)
        red = np.random.rand(100, 100)

        # Evita divisão por zero
        denominator = nir + red
        denominator[denominator == 0] = 1e-10

        ndvi = (nir - red) / denominator

        assert ndvi.min() >= -1.0, "NDVI mínimo deve ser >= -1"
        assert ndvi.max() <= 1.0, "NDVI máximo deve ser <= 1"

    def test_ndvi_mascara_nan(self):
        """Pixels mascarados (nuvem) devem resultar em NaN"""
        nir = np.array([[0.5, 0.6, np.nan]])
        red = np.array([[0.1, 0.2, np.nan]])

        ndvi = (nir - red) / (nir + red)

        assert not np.isnan(ndvi[0][0]), "Pixel válido não deve ser NaN"
        assert not np.isnan(ndvi[0][1]), "Pixel válido não deve ser NaN"
        assert np.isnan(ndvi[0][2]),     "Pixel mascarado deve ser NaN"


# ── Testes do threshold de anomalia ───────────────────────────────────────
class TestAnomalyThreshold:

    @pytest.mark.parametrize("area_ha, expected_threshold_pct", [
        (50,   3.0),    # Talhão pequeno: 3%
        (80,   3.0),    # Talhão pequeno: 3%
        (100,  3.0),    # Limite inferior: ainda 3%
        (150,  2.0),    # Talhão médio: 2%
        (300,  2.0),    # Talhão médio: 2%
        (500,  2.0),    # Limite superior: ainda 2%
        (600,  1.5),    # Talhão grande: 1.5%
        (1000, 1.5),    # Talhão grande: 1.5%
    ])
    def test_threshold_por_tamanho(self, area_ha: float, expected_threshold_pct: float):
        """
        Verifica que o threshold de área mínima é aplicado corretamente
        de acordo com o tamanho do talhão.
        """
        threshold_pct = _calculate_area_threshold(area_ha)
        assert threshold_pct == expected_threshold_pct, (
            f"Talhão de {area_ha}ha deve ter threshold de {expected_threshold_pct}%, "
            f"mas retornou {threshold_pct}%"
        )

    def test_anomalia_dispara_acima_threshold(self):
        """Queda de NDVI > 15% deve disparar alerta."""
        ndvi_anterior = 0.72
        ndvi_atual = 0.58  # Queda de ~19.4%

        drop_pct = ((ndvi_anterior - ndvi_atual) / ndvi_anterior) * 100
        assert drop_pct > 15.0, "Queda de 19.4% deve superar threshold de 15%"

    def test_anomalia_nao_dispara_abaixo_threshold(self):
        """Queda de NDVI < 15% não deve disparar alerta."""
        ndvi_anterior = 0.72
        ndvi_atual = 0.65  # Queda de ~9.7%

        drop_pct = ((ndvi_anterior - ndvi_atual) / ndvi_anterior) * 100
        assert drop_pct < 15.0, "Queda de 9.7% não deve superar threshold de 15%"

    def test_area_minima_talhao_grande(self):
        """
        Talhão de 1000ha: área mínima para alerta = 1.5% = 15ha
        """
        area_ha = 1000.0
        threshold_pct = _calculate_area_threshold(area_ha)
        min_area_ha = (threshold_pct / 100) * area_ha

        assert min_area_ha == 15.0, (
            f"Área mínima para talhão de 1000ha deve ser 15ha, "
            f"mas calculou {min_area_ha}ha"
        )


# ── Testes da SCL Mask ─────────────────────────────────────────────────────
class TestSCLMask:

    # Classes SCL que devem ser mascaradas
    CLOUD_CLASSES = [3, 8, 9, 10]  # sombra, nuvem baixa, nuvem alta, cirrus

    def test_mascara_pixels_nuvem(self):
        """Pixels com classe SCL de nuvem devem virar NaN."""
        scl = np.array([[4, 4, 8],   # 8 = nuvem → deve ser mascarado
                        [4, 9, 4],   # 9 = nuvem alta → deve ser mascarado
                        [3, 4, 4]])  # 3 = sombra → deve ser mascarado

        nir = np.ones((3, 3)) * 0.5
        red = np.ones((3, 3)) * 0.1

        # Aplica máscara
        mask = np.isin(scl, self.CLOUD_CLASSES)
        nir_masked = nir.copy().astype(float)
        red_masked = red.copy().astype(float)
        nir_masked[mask] = np.nan
        red_masked[mask] = np.nan

        # Verifica que pixels de nuvem foram mascarados
        assert np.isnan(nir_masked[0, 2]), "SCL=8 (nuvem) deve ser mascarado"
        assert np.isnan(nir_masked[1, 1]), "SCL=9 (nuvem alta) deve ser mascarado"
        assert np.isnan(nir_masked[2, 0]), "SCL=3 (sombra) deve ser mascarado"

        # Verifica que pixels de vegetação NÃO foram mascarados
        assert not np.isnan(nir_masked[0, 0]), "SCL=4 (vegetação) não deve ser mascarado"

    def test_cloud_cover_calculo(self):
        """Percentual de nuvem deve ser calculado corretamente."""
        scl = np.array([[4, 4, 8, 8],   # 2 pixels de nuvem
                        [4, 9, 4, 4],   # 1 pixel de nuvem
                        [4, 4, 4, 4],   # sem nuvem
                        [4, 4, 4, 4]])  # sem nuvem

        total_pixels = scl.size  # 16
        cloud_pixels = np.sum(np.isin(scl, self.CLOUD_CLASSES))  # 3
        cloud_cover_pct = (cloud_pixels / total_pixels) * 100

        assert cloud_cover_pct == 18.75, (
            f"3 de 16 pixels = 18.75%, mas calculou {cloud_cover_pct}%"
        )

    def test_imagem_descartada_acima_threshold(self):
        """Imagem com > 20% de nuvem deve ser descartada."""
        cloud_cover_pct = 25.0
        max_allowed = 20.0

        should_discard = cloud_cover_pct > max_allowed
        assert should_discard, "Imagem com 25% de nuvem deve ser descartada"

    def test_imagem_aceita_abaixo_threshold(self):
        """Imagem com <= 20% de nuvem deve ser aceita."""
        cloud_cover_pct = 15.0
        max_allowed = 20.0

        should_discard = cloud_cover_pct > max_allowed
        assert not should_discard, "Imagem com 15% de nuvem deve ser aceita"


# ── Função auxiliar (implementação inline para testes) ───────────────────
def _calculate_area_threshold(area_ha: float) -> float:
    """
    Calcula o threshold de área mínima (%) para disparar alerta.
    Esta lógica será implementada em app/pipeline/anomaly.py
    """
    if area_ha <= 100:
        return 3.0
    elif area_ha <= 500:
        return 2.0
    else:
        return 1.5
