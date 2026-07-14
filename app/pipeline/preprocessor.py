# ─────────────────────────────────────────────────────────────────
# app/pipeline/preprocessor.py
# Pré-processamento de imagens Sentinel-2:
#   - Aplicação da SCL Mask (Scene Classification Layer)
#   - Cálculo de cobertura de nuvens sobre o talhão
#   - Recorte do raster ao polígono do talhão (clip)
# ─────────────────────────────────────────────────────────────────

from pathlib import Path
from typing import Optional, NamedTuple

import numpy as np
from loguru import logger

# Classes SCL que representam pixels inválidos (nuvem, sombra, neve, etc.)
# Referência: Sen2Cor SCL classes
SCL_INVALID_CLASSES = {
    1,   # Saturated / Defective
    2,   # Dark Area Pixels
    3,   # Cloud Shadows
    8,   # Cloud Medium Probability
    9,   # Cloud High Probability
    10,  # Thin Cirrus
    11,  # Snow / Ice
}

MAX_CLOUD_PCT = 20.0   # máximo de cobertura de nuvem aceito (%)


class PreprocessResult(NamedTuple):
    """Resultado do pré-processamento de uma cena Sentinel-2."""
    b04: np.ndarray          # banda RED sem nuvens (float32, NaN onde inválido)
    b08: np.ndarray          # banda NIR sem nuvens (float32, NaN onde inválido)
    cloud_cover_pct: float   # percentual de pixels mascarados sobre o talhão


def _check_rasterio():
    """Verifica disponibilidade do rasterio com mensagem clara."""
    try:
        import rasterio
        return rasterio
    except ImportError:
        raise ImportError(
            "rasterio não está instalado. "
            "No Docker (Python 3.11) instale via: pip install rasterio==1.3.10\n"
            "Em sistemas com GDAL: apt-get install gdal-bin libgdal-dev"
        )


def _geometry_for_raster(clip_geom, raster_src):
    if clip_geom is None:
        return None

    if raster_src.crs and raster_src.crs.to_epsg() != 4326:
        from pyproj import Transformer
        from shapely.ops import transform as shapely_transform

        transformer = Transformer.from_crs(
            "EPSG:4326", raster_src.crs.to_epsg(), always_xy=True
        )
        return shapely_transform(transformer.transform, clip_geom)

    return clip_geom


def _read_band(path: Path, clip_geom=None) -> np.ndarray:
    """
    Lê uma banda raster e opcionalmente recorta ao polígono do talhão.

    Args:
        path:      caminho para o arquivo .tif ou .jp2
        clip_geom: geometria Shapely para recorte (opcional)

    Returns:
        Array float32 com valores da banda.
    """
    rasterio = _check_rasterio()
    from rasterio.mask import mask as rio_mask

    with rasterio.open(str(path)) as src:
        if clip_geom is not None:
            # Reprojecta geometria para o CRS do raster se necessário
            clip_geom = _geometry_for_raster(clip_geom, src)

            # Usa nodata=0 para compatibilidade com uint16 (jp2 Sentinel-2)
            # Depois converte para float32 e substitui 0 por NaN
            out_image, _ = rio_mask(
                src,
                [clip_geom.__geo_interface__],
                crop=True,
                nodata=0,
                all_touched=True,
            )
            arr = out_image[0].astype(np.float32)
            arr[arr == 0] = np.nan  # pixels fora da máscara → NaN
            return arr
        else:
            return src.read(1).astype(np.float32)


def apply_scl_mask(
    band_paths: dict[str, Path],
    clip_geom=None,
) -> Optional[PreprocessResult]:
    """
    Aplica a SCL mask nas bandas B04 e B08.

    Pixels das classes SCL inválidas são substituídos por NaN.
    Se a cobertura de nuvem for > MAX_CLOUD_PCT, retorna None
    (imagem descartada).

    Args:
        band_paths: dict com chaves 'B04', 'B08', 'SCL' e paths locais
        clip_geom:  Shapely geometry do talhão para recorte (opcional)

    Returns:
        PreprocessResult com arrays limpos ou None se imagem inválida.
    """
    if "SCL" not in band_paths:
        logger.warning("SCL não disponível — prosseguindo sem máscara de nuvem")
        cloud_cover_pct = 0.0
        b04 = _read_band(band_paths["B04"], clip_geom)
        b08 = _read_band(band_paths["B08"], clip_geom)
        return PreprocessResult(b04=b04, b08=b08, cloud_cover_pct=cloud_cover_pct)

    try:
        # Lê SCL (resolução 20m — pode ter dimensões diferentes das bandas 10m)
        rasterio = _check_rasterio()
        from rasterio.enums import Resampling

        b04_raw = _read_band(band_paths["B04"], clip_geom)
        b08_raw = _read_band(band_paths["B08"], clip_geom)

        with rasterio.open(str(band_paths["SCL"])) as scl_src:
            if clip_geom is not None:
                from rasterio.mask import mask as rio_mask
                scl_clip_geom = _geometry_for_raster(clip_geom, scl_src)
                scl_clipped, _ = rio_mask(
                    scl_src,
                    [scl_clip_geom.__geo_interface__],
                    crop=True,
                    nodata=0,
                    all_touched=True,
                )
                scl_raw = scl_clipped[0]
            else:
                scl_raw = scl_src.read(1)

        # Reamostrar SCL para o tamanho das bandas 10m (se necessário)
        if scl_raw.shape != b04_raw.shape:
            from PIL import Image
            scl_img = Image.fromarray(scl_raw.astype(np.uint8))
            scl_img = scl_img.resize(
                (b04_raw.shape[1], b04_raw.shape[0]),
                resample=Image.NEAREST,
            )
            scl_arr = np.array(scl_img, dtype=np.uint8)
        else:
            scl_arr = scl_raw.astype(np.uint8)

        # Calcula cobertura de nuvem (% de pixels inválidos)
        total_pixels = scl_arr.size
        invalid_mask = np.isin(scl_arr, list(SCL_INVALID_CLASSES))
        cloud_pixels = int(np.sum(invalid_mask))
        cloud_cover_pct = (cloud_pixels / total_pixels) * 100.0

        logger.info(
            f"SCL Mask: {cloud_pixels}/{total_pixels} pixels inválidos "
            f"({cloud_cover_pct:.1f}% cobertura de nuvem)"
        )

        # Descarta imagem se cobertura excede o limiar
        if cloud_cover_pct > MAX_CLOUD_PCT:
            logger.warning(
                f"Imagem descartada: {cloud_cover_pct:.1f}% > {MAX_CLOUD_PCT}% de nuvem"
            )
            return None

        # Aplica máscara: pixels inválidos → NaN
        b04 = b04_raw.copy()
        b08 = b08_raw.copy()
        b04[invalid_mask] = np.nan
        b08[invalid_mask] = np.nan

        return PreprocessResult(b04=b04, b08=b08, cloud_cover_pct=round(cloud_cover_pct, 2))

    except ImportError as exc:
        raise exc
    except Exception as exc:
        # "do not overlap" → SCL não cobre o talhão (tile parcial ou borda)
        # Fallback: processa sem máscara de nuvem em vez de descartar a imagem
        err_msg = str(exc).lower()
        if "overlap" in err_msg or "no overlap" in err_msg:
            logger.warning(
                f"SCL não sobrepõe a área do talhão (tile parcial?) — "
                f"prosseguindo sem máscara de nuvem: {exc}"
            )
            try:
                b04 = _read_band(band_paths["B04"], clip_geom)
                b08 = _read_band(band_paths["B08"], clip_geom)
                return PreprocessResult(b04=b04, b08=b08, cloud_cover_pct=0.0)
            except Exception as exc2:
                logger.error(f"Fallback também falhou: {exc2}")
                return None
        logger.error(f"Erro na SCL mask: {exc}")
        return None
