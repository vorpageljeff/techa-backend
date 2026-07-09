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
    valid = ~np.isnan(ndvi)

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


def generate_ndvi_png(
    b04: np.ndarray,
    b08: np.ndarray,
    field_id,
    bounds: list[float],
) -> str | None:
    """Gera `/data/tiles/{field_id}/ndvi_latest.png` e metadata JSON."""
    try:
        from PIL import Image

        ndvi = calculate_ndvi(b04, b08)
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
