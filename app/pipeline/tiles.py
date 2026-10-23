"""Geracao simples de PNG NDVI para o app mobile.

O pipeline calcula NDVI em matriz. Este modulo transforma essa matriz em uma
imagem RGBA georreferenciavel pelo bbox do talhao. Pixels invalidos ficam
transparentes para o satelite aparecer por baixo no app.
"""

from pathlib import Path
import json

import numpy as np
from loguru import logger

from app.core.config import settings
from app.pipeline.ndvi import calculate_ndvi


def _colorize_ndvi(ndvi: np.ndarray) -> np.ndarray:
    """Converte NDVI [-1, 1] em RGBA usando uma escala agronomica simples."""
    rgba = np.zeros((*ndvi.shape, 4), dtype=np.uint8)
    valid = np.isfinite(ndvi)

    bands = [
        (ndvi < 0.15, (120, 72, 32)),      # solo/vegetacao muito baixa
        ((ndvi >= 0.15) & (ndvi < 0.30), (220, 80, 45)),
        ((ndvi >= 0.30) & (ndvi < 0.45), (238, 180, 45)),
        ((ndvi >= 0.45) & (ndvi < 0.60), (142, 202, 67)),
        (ndvi >= 0.60, (32, 132, 65)),
    ]

    for mask, color in bands:
        m = mask & valid
        rgba[m, 0] = color[0]
        rgba[m, 1] = color[1]
        rgba[m, 2] = color[2]
        rgba[m, 3] = 210

    return rgba


def _map_grid(ndvi, transform, crs, clip_geom, bounds):
    """Project measurements onto a north-up Web Mercator image for map overlays.

    Four display pixels per measurement sharpen the polygon mask, without
    interpolating NDVI or inventing measurements in cloud/nodata gaps.
    """
    from math import ceil
    from pyproj import Transformer
    from shapely.ops import transform as shapely_transform
    from rasterio.features import geometry_mask
    from rasterio.transform import array_bounds, from_bounds
    from rasterio.warp import calculate_default_transform, reproject, Resampling

    if transform is None or crs is None or clip_geom is None:
        raise ValueError("Tile NDVI exige transform, CRS e geometria do talhão")
    projector = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
    geom = shapely_transform(projector.transform, clip_geom)
    left, bottom, right, top = geom.bounds
    native_transform, _, _ = calculate_default_transform(
        crs, "EPSG:3857", ndvi.shape[1], ndvi.shape[0],
        *array_bounds(*ndvi.shape, transform),
    )
    resolution = max(abs(native_transform.a), abs(native_transform.e)) / 4
    width = max(1, min(2048, ceil((right - left) / resolution)))
    height = max(1, min(2048, ceil((top - bottom) / resolution)))
    display_transform = from_bounds(left, bottom, right, top, width, height)
    display_ndvi = np.full((height, width), np.nan, dtype=np.float32)
    reproject(
        source=ndvi, destination=display_ndvi,
        src_transform=transform, src_crs=crs, src_nodata=np.nan,
        dst_transform=display_transform, dst_crs="EPSG:3857", dst_nodata=np.nan,
        resampling=Resampling.nearest,
    )
    outside = geometry_mask(
        [geom.__geo_interface__], out_shape=display_ndvi.shape,
        transform=display_transform, all_touched=False,
    )
    display_ndvi[outside] = np.nan
    # Bounds must describe this exact image, not the source raster window.
    inverse = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)
    west, south = inverse.transform(left, bottom)
    east, north = inverse.transform(right, top)
    return display_ndvi, [west, south, east, north]


def generate_ndvi_png(
    b04: np.ndarray,
    b08: np.ndarray,
    field_id,
    bounds: list[float],
    *,
    transform,
    crs,
    clip_geom,
) -> str | None:
    """Gera `/data/tiles/{field_id}/ndvi_latest.png` e metadata JSON."""
    try:
        from PIL import Image

        ndvi = calculate_ndvi(b04, b08)
        ndvi, bounds = _map_grid(ndvi, transform, crs, clip_geom, bounds)
        rgba = _colorize_ndvi(ndvi)

        field_dir = Path(settings.TILES_STORAGE_PATH) / str(field_id)
        field_dir.mkdir(parents=True, exist_ok=True)

        png_path = field_dir / "ndvi_latest.png"
        meta_path = field_dir / "ndvi_latest.json"

        Image.fromarray(rgba, mode="RGBA").save(png_path)
        west, south, east, north = bounds
        meta_path.write_text(
            json.dumps(
                {
                    "render_version": 2,
                    "crs": "EPSG:3857",
                    "bounds": {
                        "west": west,
                        "south": south,
                        "east": east,
                        "north": north,
                    }
                },
                ensure_ascii=True,
            ),
            encoding="utf-8",
        )

        logger.info(f"Tile NDVI gerado: {png_path}")
        return str(png_path)
    except Exception as exc:
        logger.error(f"Falha ao gerar PNG NDVI para field={field_id}: {exc}")
        return None
