# app/services/map_renderer.py
# Gera imagem composta: basemap OSM + overlay NDVI + contorno do polígono + legenda
from __future__ import annotations

import io
import json
import math
import os
from typing import Optional

from app.core.config import settings

try:
    from PIL import Image, ImageDraw, ImageFont
    _PIL_OK = True
except ImportError:
    _PIL_OK = False

try:
    import requests as _requests
    _REQUESTS_OK = True
except ImportError:
    _REQUESTS_OK = False

# ── Configurações ─────────────────────────────────────────────────────────────
_TILE_SERVER   = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
_USER_AGENT    = "TechaApp/1.0 (agro monitoring)"
_MAP_SIZE      = (520, 360)   # pixels do mapa composto
_ZOOM_DEFAULT  = 14
_DATA_DIR      = settings.TILES_STORAGE_PATH

# ── Paleta NDVI ───────────────────────────────────────────────────────────────
_NDVI_LEGEND = [
    (-1.0, 0.2, (220,  38,  38, 200), "Critico  (< 0.2)"),
    ( 0.2, 0.4, (245, 158,  11, 200), "Alerta   (0.2-0.4)"),
    ( 0.4, 0.6, (132, 204,  22, 200), "Normal   (0.4-0.6)"),
    ( 0.6, 1.0, ( 22, 163,  74, 200), "Excelente(> 0.6)"),
]


# ── Helpers tile/geo ──────────────────────────────────────────────────────────

def _deg2tile(lat_deg: float, lon_deg: float, zoom: int):
    lat_r = math.radians(lat_deg)
    n = 2 ** zoom
    x = int((lon_deg + 180) / 360 * n)
    y = int((1 - math.log(math.tan(lat_r) + 1 / math.cos(lat_r)) / math.pi) / 2 * n)
    return x, y


def _tile2deg(xtile: int, ytile: int, zoom: int):
    n = 2 ** zoom
    lon = xtile / n * 360 - 180
    lat_r = math.atan(math.sinh(math.pi * (1 - 2 * ytile / n)))
    lat = math.degrees(lat_r)
    return lat, lon


def _latlon_to_pixel(lat: float, lon: float,
                     tile_x0: int, tile_y0: int,
                     zoom: int, tile_px: int = 256) -> tuple[int, int]:
    tx, ty = _deg2tile(lat, lon, zoom)
    lat_nw, lon_nw = _tile2deg(tile_x0, tile_y0, zoom)
    lat_se, lon_se = _tile2deg(tile_x0 + 1, tile_y0 + 1, zoom)

    # fração dentro do mosaico de tiles
    tiles_wide = (_MAP_SIZE[0] + tile_px - 1) // tile_px + 1
    tiles_tall = (_MAP_SIZE[1] + tile_px - 1) // tile_px + 1
    lat_top, lon_left   = _tile2deg(tile_x0, tile_y0, zoom)
    lat_bot, lon_right  = _tile2deg(tile_x0 + tiles_wide, tile_y0 + tiles_tall, zoom)

    px = int((lon - lon_left)  / (lon_right - lon_left)  * _MAP_SIZE[0])
    py = int((lat - lat_top)   / (lat_bot   - lat_top)   * _MAP_SIZE[1])
    return px, py


# ── Fetch OSM basemap ─────────────────────────────────────────────────────────

def _fetch_basemap(
    center_lat: float, center_lon: float, zoom: int
) -> Optional[tuple["Image.Image", int, int]]:
    if not _REQUESTS_OK or not _PIL_OK:
        return None

    tile_px = 256
    cx, cy = _deg2tile(center_lat, center_lon, zoom)

    tiles_wide = math.ceil(_MAP_SIZE[0] / tile_px) + 1
    tiles_tall = math.ceil(_MAP_SIZE[1] / tile_px) + 1

    # tile superior-esquerdo
    x0 = cx - tiles_wide // 2
    y0 = cy - tiles_tall // 2

    canvas = Image.new("RGBA", (tiles_wide * tile_px, tiles_tall * tile_px))

    for dx in range(tiles_wide):
        for dy in range(tiles_tall):
            url = _TILE_SERVER.format(z=zoom, x=x0 + dx, y=y0 + dy)
            try:
                r = _requests.get(url, timeout=6,
                                  headers={"User-Agent": _USER_AGENT})
                if r.status_code == 200:
                    tile = Image.open(io.BytesIO(r.content)).convert("RGBA")
                    canvas.paste(tile, (dx * tile_px, dy * tile_px))
            except Exception:
                pass

    # recorta e centraliza
    offset_x = (cx - x0) * tile_px - _MAP_SIZE[0] // 2
    offset_y = (cy - y0) * tile_px - _MAP_SIZE[1] // 2
    basemap = canvas.crop((offset_x, offset_y,
                           offset_x + _MAP_SIZE[0],
                           offset_y + _MAP_SIZE[1]))
    return basemap, x0, y0


# ── Overlay NDVI ──────────────────────────────────────────────────────────────

def _overlay_ndvi(basemap: Image.Image,
                  ndvi_png_path: str,
                  bounds: dict,
                  center_lat: float, center_lon: float,
                  zoom: int, x0: int, y0: int) -> Image.Image:
    """Cola o PNG NDVI sobre o basemap alinhado por bounds geográficos."""
    if not _PIL_OK or not os.path.exists(ndvi_png_path):
        return basemap

    try:
        ndvi_img = Image.open(ndvi_png_path).convert("RGBA")
    except Exception:
        return basemap

    north = bounds.get("north", center_lat + 0.01)
    south = bounds.get("south", center_lat - 0.01)
    east  = bounds.get("east",  center_lon + 0.01)
    west  = bounds.get("west",  center_lon - 0.01)

    tile_px = 256
    tiles_wide = math.ceil(_MAP_SIZE[0] / tile_px) + 1
    tiles_tall = math.ceil(_MAP_SIZE[1] / tile_px) + 1

    lat_top,  lon_left  = _tile2deg(x0, y0, zoom)
    lat_bot,  lon_right = _tile2deg(x0 + tiles_wide, y0 + tiles_tall, zoom)

    # offset do canvas recortado
    cx, cy = _deg2tile(center_lat, center_lon, zoom)
    off_x = (cx - x0) * tile_px - _MAP_SIZE[0] // 2
    off_y = (cy - y0) * tile_px - _MAP_SIZE[1] // 2

    # converte bounds NDVI para pixels na imagem final
    def geo2px(lat, lon):
        raw_x = (lon - lon_left) / (lon_right - lon_left) * (tiles_wide * tile_px) - off_x
        raw_y = (lat - lat_top)  / (lat_bot   - lat_top)  * (tiles_tall * tile_px) - off_y
        return int(raw_x), int(raw_y)

    px_west, py_north = geo2px(north, west)
    px_east, py_south = geo2px(south, east)

    w = max(px_east - px_west, 1)
    h = max(py_south - py_north, 1)

    # coloca NDVI com transparência parcial
    ndvi_resized = ndvi_img.resize((w, h), Image.LANCZOS)

    # Aplica alpha de 70% sobre pixels não-transparentes
    r, g, b, a = ndvi_resized.split()
    a = a.point(lambda v: int(v * 0.75))
    ndvi_resized = Image.merge("RGBA", (r, g, b, a))

    result = basemap.copy()
    result.paste(ndvi_resized, (px_west, py_north), ndvi_resized)
    return result


# ── Contorno do polígono ──────────────────────────────────────────────────────

def _draw_polygon(img: Image.Image,
                  geojson_coords: list,
                  center_lat: float, center_lon: float,
                  zoom: int, x0: int, y0: int) -> Image.Image:
    if not _PIL_OK or not geojson_coords:
        return img

    tile_px = 256
    tiles_wide = math.ceil(_MAP_SIZE[0] / tile_px) + 1
    tiles_tall = math.ceil(_MAP_SIZE[1] / tile_px) + 1
    lat_top,  lon_left  = _tile2deg(x0, y0, zoom)
    lat_bot,  lon_right = _tile2deg(x0 + tiles_wide, y0 + tiles_tall, zoom)
    cx, cy = _deg2tile(center_lat, center_lon, zoom)
    off_x = (cx - x0) * tile_px - _MAP_SIZE[0] // 2
    off_y = (cy - y0) * tile_px - _MAP_SIZE[1] // 2

    def geo2px(lon, lat):
        raw_x = (lon - lon_left) / (lon_right - lon_left) * (tiles_wide * tile_px) - off_x
        raw_y = (lat - lat_top)  / (lat_bot   - lat_top)  * (tiles_tall * tile_px) - off_y
        return int(raw_x), int(raw_y)

    draw = ImageDraw.Draw(img)
    try:
        ring = geojson_coords[0] if isinstance(geojson_coords[0][0], list) else geojson_coords
        pts = [geo2px(c[0], c[1]) for c in ring]
        if len(pts) >= 2:
            draw.line(pts + [pts[0]], fill=(255, 255, 0, 255), width=2)
    except Exception:
        pass
    return img


# ── Legenda NDVI ──────────────────────────────────────────────────────────────

def _draw_legend(img: Image.Image) -> Image.Image:
    if not _PIL_OK:
        return img

    draw = ImageDraw.Draw(img, "RGBA")
    margin = 8
    box_w, box_h = 160, 90
    x0l = margin
    y0l = _MAP_SIZE[1] - margin - box_h

    # fundo semi-transparente
    draw.rectangle([x0l, y0l, x0l + box_w, y0l + box_h],
                   fill=(0, 0, 0, 160))

    try:
        font = ImageFont.load_default()
    except Exception:
        font = None

    y = y0l + 6
    for lo, hi, color, label in _NDVI_LEGEND:
        draw.rectangle([x0l + 6, y, x0l + 18, y + 10], fill=color)
        draw.text((x0l + 24, y), label, fill=(255, 255, 255, 255), font=font)
        y += 18

    return img


# ── Rosa dos Ventos ───────────────────────────────────────────────────────────

def _draw_compass_rose(img: Image.Image) -> Image.Image:
    """Desenha uma rosa dos ventos (N/S/L/O) no canto superior direito."""
    if not _PIL_OK:
        return img

    draw = ImageDraw.Draw(img, "RGBA")

    # Centro da rosa
    cx = _MAP_SIZE[0] - 38
    cy = 42
    r  = 18   # raio das pontas

    # Fundo semi-transparente circular
    draw.ellipse([cx - r - 4, cy - r - 4, cx + r + 4, cy + r + 4],
                 fill=(0, 0, 0, 140))

    # Seta Norte (branca) — seta dupla: metade superior branca, metade inferior cinza
    # Norte: ponta em cima
    north_tip  = (cx, cy - r)
    south_tip  = (cx, cy + r)
    east_tip   = (cx + r, cy)
    west_tip   = (cx - r, cy)
    center     = (cx, cy)
    half_w     = 5  # meia-largura da seta

    # Seta Norte — branca
    draw.polygon([north_tip,
                  (cx - half_w, cy),
                  center,
                  (cx + half_w, cy)],
                 fill=(255, 255, 255, 240))

    # Seta Sul — cinza claro
    draw.polygon([south_tip,
                  (cx + half_w, cy),
                  center,
                  (cx - half_w, cy)],
                 fill=(180, 180, 180, 200))

    # Seta Leste — branca
    draw.polygon([east_tip,
                  (cx, cy - half_w),
                  center,
                  (cx, cy + half_w)],
                 fill=(255, 255, 255, 200))

    # Seta Oeste — cinza claro
    draw.polygon([west_tip,
                  (cx, cy + half_w),
                  center,
                  (cx, cy - half_w)],
                 fill=(180, 180, 180, 180))

    # Ponto central
    dot_r = 3
    draw.ellipse([cx - dot_r, cy - dot_r, cx + dot_r, cy + dot_r],
                 fill=(60, 60, 60, 255))

    # Labels N / S / L / O
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None

    labels = [
        ("N", cx - 4, cy - r - 12, (255, 255, 255, 255)),
        ("S", cx - 3, cy + r +  3, (220, 220, 220, 255)),
        ("L", cx + r + 3, cy - 5, (255, 255, 255, 255)),
        ("O", cx - r - 11, cy - 5, (220, 220, 220, 255)),
    ]
    for text, tx, ty, color in labels:
        draw.text((tx, ty), text, fill=color, font=font)

    return img


# ── Ponto central ─────────────────────────────────────────────────────────────

def _draw_center_dot(img: Image.Image) -> Image.Image:
    if not _PIL_OK:
        return img
    draw = ImageDraw.Draw(img)
    cx, cy = _MAP_SIZE[0] // 2, _MAP_SIZE[1] // 2
    r = 5
    draw.ellipse([cx - r, cy - r, cx + r, cy + r],
                 fill=(22, 163, 74, 230), outline=(255, 255, 255, 255))
    return img


# ── Função principal ──────────────────────────────────────────────────────────

def generate_ndvi_map(field_id: str) -> Optional[str]:
    """
    Gera mapa composto (OSM + NDVI + polígono + legenda) para o talhão.
    Salva no storage de tiles configurado e retorna o caminho.
    Retorna None se não conseguir gerar.
    """
    if not _PIL_OK or not _REQUESTS_OK:
        return None

    field_dir  = os.path.join(_DATA_DIR, field_id)
    meta_path  = os.path.join(field_dir, "ndvi_latest.json")
    ndvi_path  = os.path.join(field_dir, "ndvi_latest.png")
    out_path   = os.path.join(field_dir, "map_report.png")

    if not os.path.exists(meta_path):
        return None

    try:
        meta = json.loads(open(meta_path).read())
    except Exception:
        return None

    bounds = meta.get("bounds", {})
    north = bounds.get("north")
    south = bounds.get("south")
    east  = bounds.get("east")
    west  = bounds.get("west")

    if None in (north, south, east, west):
        return None

    center_lat = (north + south) / 2
    center_lon = (east  + west)  / 2

    zoom = _ZOOM_DEFAULT

    # 1. Basemap OSM
    result = _fetch_basemap(center_lat, center_lon, zoom)
    if result is None:
        return None
    basemap, x0, y0 = result

    # 2. Overlay NDVI
    img = _overlay_ndvi(basemap, ndvi_path, bounds, center_lat, center_lon, zoom, x0, y0)

    # 3. Contorno do polígono
    geojson_path = os.path.join(field_dir, "polygon.geojson")
    if os.path.exists(geojson_path):
        try:
            gj = json.loads(open(geojson_path).read())
            coords = (gj.get("geometry") or gj).get("coordinates", [])
            img = _draw_polygon(img, coords, center_lat, center_lon, zoom, x0, y0)
        except Exception:
            pass

    # 4. Legenda NDVI
    img = _draw_legend(img)

    # 5. Rosa dos ventos
    img = _draw_compass_rose(img)

    # 6. Ponto central
    img = _draw_center_dot(img)

    # Salva
    try:
        os.makedirs(field_dir, exist_ok=True)
        img.convert("RGB").save(out_path, "PNG", optimize=True)
        return out_path
    except Exception:
        return None
