"""Regression tests with real GeoTIFF grids, including shifted SCL origins."""
import json

import numpy as np
import pytest
import rasterio
from PIL import Image
from rasterio.transform import from_origin, from_bounds
from shapely.geometry import Polygon, box

from app.pipeline.preprocessor import apply_scl_mask
from app.pipeline.tiles import _map_grid, _colorize_ndvi, generate_ndvi_png


def write_band(path, data, transform):
    with rasterio.open(
        path, 'w', driver='GTiff', height=data.shape[0], width=data.shape[1],
        count=1, dtype=data.dtype, crs='EPSG:4326', transform=transform, nodata=0,
    ) as dst:
        dst.write(data, 1)
    return path


def test_scl_same_shape_shifted_origin_uses_coordinates(tmp_path):
    red = np.full((8, 8), 1000, dtype=np.uint16)
    scl = np.full((8, 8), 4, dtype=np.uint8)
    scl[2, 1] = 9
    grid = from_origin(0, 0.08, 0.01, 0.01)
    paths = {
        'B04': write_band(tmp_path / 'red.tif', red, grid),
        'B08': write_band(tmp_path / 'nir.tif', red * 7, grid),
        'SCL': write_band(tmp_path / 'scl.tif', scl, from_origin(0.01, 0.08, 0.01, 0.01)),
    }
    result = apply_scl_mask(paths, box(0, 0, 0.08, 0.08))
    assert result is not None
    assert np.isnan(result.b04[2, 2])  # cloud lies in RED column 2, not 1
    assert np.isfinite(result.b04[2, 1])
    assert np.isnan(result.b04[:, 0]).all()  # uncovered SCL is not clear sky
    assert result.cloud_cover_pct == pytest.approx(9 / 64 * 100, abs=0.01)
    assert result.transform == grid


def test_cloud_fraction_excludes_outside_polygon(tmp_path):
    grid = from_origin(0, 0.08, 0.01, 0.01)
    red = np.full((8, 8), 1000, dtype=np.uint16)
    scl = np.full((8, 8), 9, dtype=np.uint8)
    scl[:3, :] = 4
    geom = Polygon([(0, 0.08), (0.08, 0.08), (0, 0)])
    paths = {name: write_band(tmp_path / f'{name}.tif', data, grid)
             for name, data in [('B04', red), ('B08', red * 7), ('SCL', scl)]}
    # Triangle has >20% invalid coverage; outside cells must not dilute it.
    assert apply_scl_mask(paths, geom) is None


def test_overlay_clips_holes_and_keeps_nodata():
    outer = [(-54, -25), (-53.99, -25), (-53.99, -24.99), (-54, -24.99)]
    hole = [(-53.998, -24.998), (-53.996, -24.998), (-53.996, -24.996), (-53.998, -24.996)]
    geom = Polygon(outer, [hole])
    source = np.full((20, 20), 0.7, dtype=np.float32)
    source[3:6, 12:15] = np.nan
    displayed, bounds = _map_grid(
        source, from_bounds(*geom.bounds, 20, 20), 'EPSG:4326', geom, list(geom.bounds),
    )
    assert bounds == pytest.approx(geom.bounds)
    assert displayed.shape[0] > 20  # display mask refined, measurements unchanged
    assert np.isnan(displayed).any()
    assert np.isfinite(displayed).any()
    assert np.unique(displayed[np.isfinite(displayed)]) == pytest.approx([0.7])
    # Point in interior hole: corresponding output pixels remain transparent.
    h, w = displayed.shape
    assert np.isnan(displayed[int(h * 0.7), int(w * 0.3)])
    assert np.isnan(displayed[int(h * 0.22), int(w * 0.67)])
    rgba = _colorize_ndvi(displayed)
    assert (rgba[np.isnan(displayed), 3] == 0).all()


def test_output_reprojects_cropped_grid_without_stretching(tmp_path, monkeypatch):
    from app.pipeline import tiles
    monkeypatch.setattr(tiles.settings, 'TILES_STORAGE_PATH', str(tmp_path))
    # Source extends beyond field and has a known east/west split.
    source = np.ones((10, 10), dtype=np.float32)
    nir = source.copy()
    nir[:, 5:] = 7
    geom = Polygon([(0.025, 0.02), (0.09, 0.02), (0.09, 0.09)])
    path = generate_ndvi_png(
        source, nir, 'field', list(geom.bounds),
        transform=from_origin(0, 0.1, 0.01, 0.01), crs='EPSG:4326', clip_geom=geom,
    )
    assert path is not None
    meta = json.loads((tmp_path / 'field' / 'ndvi_latest.json').read_text())
    assert list(meta['bounds'].values()) == pytest.approx(geom.bounds)
    assert meta['render_version'] == 2
    pixels = np.asarray(Image.open(path))
    # Triangle excludes top-left; right-side NIR vegetation remains green.
    assert pixels[0, 0, 3] == 0
    assert tuple(pixels[-3, -3, :3]) == (32, 132, 65)


def test_nonfinite_values_are_transparent():
    rgba = _colorize_ndvi(np.array([[np.inf, -np.inf, np.nan, 0.7]]))
    assert list(rgba[0, :, 3]) == [0, 0, 0, 210]
