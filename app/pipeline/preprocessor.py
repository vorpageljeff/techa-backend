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
    0,   # No data / outside SCL coverage
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
    transform: object = None  # affine transform of the cropped B04 grid
    crs: object = None        # coordinate reference system of that grid


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
            "EPSG:4326", raster_src.crs, always_xy=True
        )
        return shapely_transform(transformer.transform, clip_geom)

    return clip_geom


def _read_band_grid(path: Path, clip_geom=None):
    """Read data and retain the exact cropped pixel grid (including nodata)."""
    rasterio = _check_rasterio()
    from rasterio.mask import mask as rio_mask

    with rasterio.open(str(path)) as src:
        if src.crs is None:
            raise ValueError(f"Raster sem CRS: {path}")
        if clip_geom is not None:
            geom = _geometry_for_raster(clip_geom, src)
            data, transform = rio_mask(
                src, [geom.__geo_interface__], crop=True,
                filled=False, all_touched=True,
            )
            band = data[0]
        else:
            band = src.read(1, masked=True)
            transform = src.transform
        arr = band.astype(np.float32).filled(np.nan)
        arr[arr == 0] = np.nan
        return arr, transform, src.crs


def _read_band(path: Path, clip_geom=None) -> np.ndarray:
    return _read_band_grid(path, clip_geom)[0]


def _aligned_band(path, shape, transform, crs, *, categorical=False):
    """Align by geographic coordinates, never by array dimensions alone."""
    rasterio = _check_rasterio()
    from rasterio.warp import reproject, Resampling

    dtype = np.uint8 if categorical else np.float32
    nodata = 0 if categorical else np.nan
    destination = np.full(shape, nodata, dtype=dtype)
    with rasterio.open(str(path)) as src:
        if src.crs is None:
            raise ValueError(f"Raster sem CRS: {path}")
        reproject(
            source=rasterio.band(src, 1), destination=destination,
            src_transform=src.transform, src_crs=src.crs,
            src_nodata=src.nodata if src.nodata is not None else 0,
            dst_transform=transform, dst_crs=crs, dst_nodata=nodata,
            resampling=Resampling.nearest,
        )
    return destination


def apply_scl_mask(band_paths: dict[str, Path], clip_geom=None) -> Optional[PreprocessResult]:
    """Align RED, NIR and SCL on B04's grid before masking invalid pixels."""
    try:
        b04, transform, crs = _read_band_grid(band_paths["B04"], clip_geom)
        b08 = _aligned_band(band_paths["B08"], b04.shape, transform, crs)
        footprint = np.isfinite(b04) & np.isfinite(b08)
        b08[~footprint] = np.nan
        b04[~footprint] = np.nan

        if "SCL" not in band_paths:
            logger.warning("SCL não disponível — prosseguindo sem máscara de nuvem")
            return PreprocessResult(b04, b08, 0.0, transform, crs)

        scl = _aligned_band(
            band_paths["SCL"], b04.shape, transform, crs, categorical=True,
        )
        invalid = np.isin(scl, list(SCL_INVALID_CLASSES))
        total = int(footprint.sum())
        if total == 0:
            return None
        invalid_count = int((invalid & footprint).sum())
        cloud_cover_pct = invalid_count / total * 100.0
        logger.info(f"SCL Mask: {invalid_count}/{total} pixels inválidos ({cloud_cover_pct:.1f}%)")
        if cloud_cover_pct > MAX_CLOUD_PCT:
            logger.warning(f"Imagem descartada: {cloud_cover_pct:.1f}% de pixels inválidos")
            return None
        b04[invalid] = np.nan
        b08[invalid] = np.nan
        return PreprocessResult(b04, b08, round(cloud_cover_pct, 2), transform, crs)
    except ImportError:
        raise
    except Exception as exc:
        logger.error(f"Erro na SCL mask: {exc}")
        return None
