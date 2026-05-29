# app/services/report_service.py
# Geração de relatório PDF do talhão com dados NDVI e anomalias
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from typing import Any

from fpdf import FPDF

from app.core.config import settings


# ── Paleta de cores Techá ─────────────────────────────────────────
_GREEN_DARK  = (26,  71, 49)   # #1a4731
_GREEN       = (22, 163, 74)   # #16A34A
_GREEN_LIGHT = (240, 253, 244) # #F0FDF4
_RED         = (220,  38, 38)  # #DC2626
_AMBER       = (245, 158, 11)  # #F59E0B
_GRAY        = (107, 114, 128) # #6B7280
_DARK        = (26,  32, 44)   # #1A202C
_WHITE       = (255, 255, 255)
_LIGHT_GRAY  = (229, 231, 235) # #E5E7EB

# ── Labels de tipo de anomalia ────────────────────────────────────
_ANOMALY_TYPE = {
    "hidrico":     "Estresse Hidrico",
    "praga":       "Praga / Doenca",
    "nutricional": "Deficiencia Nutricional",
    "unknown":     "A Identificar",
}

_NDVI_LABEL = [
    (-1.0, 0.2,  _RED,            "Critico"),
    ( 0.2, 0.4,  _AMBER,          "Alerta"),
    ( 0.4, 0.6,  (132, 204,  22), "Normal"),
    ( 0.6, 1.0,  _GREEN,          "Excelente"),
]


def _ndvi_color_label(ndvi: float | None):
    if ndvi is None:
        return _GRAY, "Sem dados"
    for lo, hi, color, label in _NDVI_LABEL:
        if lo <= ndvi < hi:
            return color, label
    return _GRAY, "Sem dados"


def _fmt_date(dt: Any) -> str:
    if dt is None:
        return "-"
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt)
        except Exception:
            return dt
    return dt.strftime("%d/%m/%Y")


def _fmt_datetime(dt: Any) -> str:
    if dt is None:
        return "-"
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        except Exception:
            return dt
    return dt.strftime("%d/%m/%Y %H:%M")


def _storage_file(field_id: Any, filename: str) -> str:
    return os.path.join(settings.TILES_STORAGE_PATH, str(field_id), filename)


def _fallback_ndvi_image(ndvi: float | None) -> str | None:
    try:
        from PIL import Image, ImageDraw
    except Exception:
        return None

    if ndvi is None:
        color = _GRAY
    else:
        color, _ = _ndvi_color_label(ndvi)

    img = Image.new("RGBA", (520, 360), (*color, 185))
    draw = ImageDraw.Draw(img, "RGBA")
    for y in range(0, 360, 30):
        alpha = 24 if (y // 30) % 2 == 0 else 10
        draw.rectangle((0, y, 520, y + 14), fill=(255, 255, 255, alpha))

    tmp = tempfile.NamedTemporaryFile(prefix="techa_ndvi_", suffix=".png", delete=False)
    tmp.close()
    img.save(tmp.name)
    return tmp.name


class _PDF(FPDF):
    """PDF customizado com header e footer Techá."""

    def header(self):
        self.set_fill_color(*_GREEN_DARK)
        self.rect(0, 0, 210, 18, "F")
        self.set_text_color(*_WHITE)
        self.set_font("Helvetica", "B", 13)
        self.set_xy(10, 4)
        self.cell(130, 10, "Techa - Monitoramento NDVI", ln=False)
        self.set_font("Helvetica", "", 9)
        self.set_x(140)
        self.cell(60, 10, f"Gerado em {datetime.now().strftime('%d/%m/%Y %H:%M')}", align="R", ln=True)
        self.set_text_color(*_DARK)
        self.ln(6)

    def footer(self):
        self.set_y(-12)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*_GRAY)
        self.cell(0, 8, f"Techa by InnovAgro  |  Pagina {self.page_no()}", align="C")

    def section_title(self, title: str):
        self.set_fill_color(*_GREEN_DARK)
        self.set_text_color(*_WHITE)
        self.set_font("Helvetica", "B", 10)
        self.cell(0, 8, f"  {title}", ln=True, fill=True)
        self.set_text_color(*_DARK)
        self.ln(2)

    def kv_row(self, key: str, value: str, fill: bool = False):
        if fill:
            self.set_fill_color(*_GREEN_LIGHT)
        self.set_font("Helvetica", "B", 9)
        self.cell(55, 7, key, border="B", fill=fill)
        self.set_font("Helvetica", "", 9)
        self.cell(0, 7, value, border="B", fill=fill, ln=True)


def generate_field_report(
    field_name: str,
    farm_name: str,
    crop: str | None,
    area_ha: float | None,
    planting_date: Any,
    analyses: list[dict],   # lista: {image_date, processed_at, ndvi_mean, ndvi_min, ndvi_max, status}
    anomalies: list[dict],  # lista: {detected_at, ndvi_drop_pct, affected_area_ha, suspected_type, status}
    latest: dict | None,    # análise mais recente
    field_id=None,
) -> bytes:
    """Gera o relatório PDF em memória e retorna como bytes."""

    pdf = _PDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()

    # ── 1. Identificação do Talhão ────────────────────────────────
    pdf.section_title("1. Identificacao do Talhao")
    pdf.kv_row("Talhao:",    field_name,                                          fill=True)
    pdf.kv_row("Fazenda:",   farm_name,                                           fill=False)
    pdf.kv_row("Cultura:",   crop or "Nao informada",                             fill=True)
    pdf.kv_row("Area:",      f"{area_ha:.1f} ha" if area_ha else "Nao calculada", fill=False)
    pdf.kv_row("Plantio:",   _fmt_date(planting_date),                            fill=True)
    pdf.ln(6)

    # ── 2. Mapa + Ficha Técnica ───────────────────────────────────
    pdf.section_title("2. Mapa de Localizacao e Vigor Vegetativo")

    # Gera mapa composto OSM + NDVI
    map_img = None
    if field_id is not None:
        try:
            from app.services.map_renderer import generate_ndvi_map
            map_img = generate_ndvi_map(str(field_id))
        except Exception:
            pass

    # Fallback: tile NDVI bruto
    img_to_embed = map_img
    if img_to_embed is None and field_id is not None:
        _raw = _storage_file(field_id, "ndvi_latest.png")
        if os.path.exists(_raw):
            img_to_embed = _raw

    # Lê centro geográfico do meta
    center_lat, center_lon = None, None
    bounds_info = ""
    if field_id is not None:
        try:
            _meta_path = _storage_file(field_id, "ndvi_latest.json")
            if os.path.exists(_meta_path):
                _meta = json.loads(open(_meta_path).read())
                _b = _meta.get("bounds", {})
                _n, _s = _b.get("north", 0), _b.get("south", 0)
                _e, _w = _b.get("east", 0),  _b.get("west", 0)
                center_lat = (_n + _s) / 2
                center_lon = (_e + _w) / 2
                _dlat = abs(_n - _s) * 111  # km aprox
                _dlon = abs(_e - _w) * 111 * abs(center_lat * 3.14159 / 180)
                bounds_info = f"{_dlat:.1f} x {_dlon:.1f} km"
        except Exception:
            pass

    img_date_str = _fmt_date(latest.get("image_date")) if latest else "-"
    processed_at_str = _fmt_datetime(latest.get("processed_at")) if latest else "-"
    ndvi_v  = latest.get("ndvi_mean")  if latest else None
    ndvi_lo = latest.get("ndvi_min")   if latest else None
    ndvi_hi = latest.get("ndvi_max")   if latest else None
    _, ndvi_lbl = _ndvi_color_label(ndvi_v)

    # Layout: tabela técnica (esq) | mapa thumbnail (dir)
    y_section_start = pdf.get_y()
    map_w   = 75                             # mm
    gap     = 4                              # mm entre tabela e mapa
    left_w  = 190 - map_w - gap             # ~111 mm
    x_map   = pdf.l_margin + left_w + gap   # posição X do mapa

    # Tabela técnica à esquerda
    tech_rows = [
        ("Satelite:",     "Sentinel-2 (ESA/Copernicus)"),
        ("Resolucao:",    "10 metros/pixel"),
        ("Revisita:",     "~5 dias"),
        ("Data imagem:",  img_date_str),
        ("Processado:",   processed_at_str),
        ("Lat / Lon:",    f"{center_lat:.5f}N, {center_lon:.5f}E" if center_lat else "-"),
        ("Extensao:",     bounds_info if bounds_info else "-"),
        ("Area talhao:",  f"{area_ha:.1f} ha" if area_ha else "-"),
        ("NDVI medio:",   f"{ndvi_v:.3f}  ({ndvi_lbl})" if ndvi_v is not None else "-"),
        ("NDVI min/max:", f"{ndvi_lo:.3f} / {ndvi_hi:.3f}" if ndvi_lo is not None else "-"),
    ]

    key_col = 34   # mm
    val_col = left_w - key_col

    for i, (k, v) in enumerate(tech_rows):
        fill = i % 2 == 0
        if fill:
            pdf.set_fill_color(*_GREEN_LIGHT)
        pdf.set_xy(pdf.l_margin, pdf.get_y())
        pdf.set_font("Helvetica", "B", 8)
        pdf.cell(key_col, 6, k, border="B", fill=fill)
        pdf.set_font("Helvetica", "", 8)
        pdf.cell(val_col, 6, v, border="B", fill=fill, ln=True)

    y_after_table = pdf.get_y()

    # Mapa à direita (alinhado ao topo da seção)
    if img_to_embed is None and latest:
        img_to_embed = _fallback_ndvi_image(ndvi_v)

    if img_to_embed:
        map_h_approx = map_w * 0.70   # proporção 4:3 aprox
        pdf.image(img_to_embed, x=x_map, y=y_section_start, w=map_w)
        y_after_map = y_section_start + map_h_approx + 4
        pdf.set_y(max(y_after_table, y_after_map))
        pdf.set_font("Helvetica", "I", 7)
        pdf.set_text_color(*_GRAY)
        pdf.cell(0, 5,
                 "Imagem Sentinel-2 processada pelo sistema Techa  |  (c) OpenStreetMap contributors",
                 align="C", ln=True)
        pdf.set_text_color(*_DARK)
    else:
        pdf.set_y(y_after_table + 2)
        pdf.set_font("Helvetica", "I", 9)
        pdf.set_text_color(*_GRAY)
        pdf.cell(0, 8, "Mapa NDVI indisponivel para este talhao.", ln=True)
        pdf.set_text_color(*_DARK)

    pdf.ln(5)

    # ── 3. Situação NDVI Atual ────────────────────────────────────
    pdf.section_title("3. Situacao NDVI Atual (Sentinel-2)")

    if latest:
        color, label = _ndvi_color_label(ndvi_v)
        pdf.set_fill_color(*color)
        pdf.set_text_color(*_WHITE)
        pdf.set_font("Helvetica", "B", 14)
        pdf.cell(60, 12, f"  NDVI: {ndvi_v:.3f}" if ndvi_v is not None else "  Sem dados", fill=True)
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(40, 12, f"  {label}", fill=True)
        pdf.set_text_color(*_DARK)
        pdf.ln(14)

        pdf.set_font("Helvetica", "", 9)
        pdf.set_fill_color(*_GREEN_LIGHT)
        pdf.cell(55, 7, "Data da imagem:", border="B", fill=True)
        pdf.cell(0,  7, img_date_str,      border="B", fill=False, ln=True)
        pdf.cell(55, 7, "Processado em:",  border="B", fill=True)
        pdf.cell(0,  7, processed_at_str,  border="B", fill=False, ln=True)
        pdf.cell(55, 7, "NDVI Minimo:",    border="B", fill=True)
        pdf.cell(0,  7, f"{ndvi_lo:.3f}" if ndvi_lo is not None else "-", border="B", ln=True)
        pdf.cell(55, 7, "NDVI Maximo:",   border="B", fill=True)
        pdf.cell(0,  7, f"{ndvi_hi:.3f}" if ndvi_hi is not None else "-", border="B", ln=True)
    else:
        pdf.set_font("Helvetica", "I", 10)
        pdf.set_text_color(*_GRAY)
        pdf.cell(0, 8, "Nenhuma analise disponivel ainda.", ln=True)
        pdf.set_text_color(*_DARK)

    pdf.ln(6)

    # ── 4. Distribuição de Área por Índice NDVI ───────────────────
    pdf.section_title("4. Distribuicao de Area por Indice NDVI")

    # Tenta ler distribuição do raster (se disponível)
    ndvi_dist: dict | None = None
    if field_id is not None:
        try:
            _dist_path = _storage_file(field_id, "ndvi_distribution.json")
            if os.path.exists(_dist_path):
                ndvi_dist = json.loads(open(_dist_path).read())
        except Exception:
            pass

    # Cabeçalho da tabela
    pdf.set_fill_color(*_GREEN_DARK)
    pdf.set_text_color(*_WHITE)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(10,  7, "",            fill=True)          # cor
    pdf.cell(45,  7, "Indice",      fill=True)
    pdf.cell(40,  7, "Faixa NDVI",  fill=True, align="C")
    pdf.cell(40,  7, "% da Area",   fill=True, align="C")
    pdf.cell(0,   7, "Situacao",    fill=True, align="C", ln=True)
    pdf.set_text_color(*_DARK)

    _DIST_LABELS = [
        (-1.0, 0.2, _RED,            "Critico",    "Intervencao urgente"),
        ( 0.2, 0.4, _AMBER,          "Alerta",     "Monitorar de perto"),
        ( 0.4, 0.6, (132, 204,  22), "Normal",     "Vigor adequado"),
        ( 0.6, 1.0, _GREEN,          "Excelente",  "Vigor elevado"),
    ]

    for i, (lo, hi, color, lbl, sit) in enumerate(_DIST_LABELS):
        fill = i % 2 == 0
        if fill:
            pdf.set_fill_color(*_GREEN_LIGHT)
        # quadrado colorido
        pdf.set_fill_color(*color)
        pdf.rect(pdf.get_x() + 1, pdf.get_y() + 1.5, 8, 4.5, "F")
        pdf.cell(10, 7, "", fill=False)
        if fill:
            pdf.set_fill_color(*_GREEN_LIGHT)
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(45, 7, f"  {lbl}", border="B", fill=fill)
        pdf.set_font("Helvetica", "", 9)
        pdf.cell(40, 7, f"NDVI {lo:.1f} a {hi:.1f}", border="B", fill=fill, align="C")

        # % da área — do JSON se disponível, senão "-"
        if ndvi_dist:
            pct = ndvi_dist.get(lbl.lower(), ndvi_dist.get(lbl, None))
            pct_str = f"{pct:.1f}%" if pct is not None else "-"
        elif ndvi_v is not None:
            # Estimativa simples a partir do NDVI médio se não há distribuição real
            # Curva normal centrada no NDVI médio com desvio estimado
            import math as _math
            sigma = (ndvi_hi - ndvi_lo) / 4 if (ndvi_hi and ndvi_lo) else 0.15
            mu = ndvi_v
            # integral da gaussiana de lo a hi
            def _gauss_cdf(x, mu, sigma):
                return (1 + _math.erf((x - mu) / (sigma * _math.sqrt(2)))) / 2
            _lo2 = max(lo, -1.0)
            _hi2 = min(hi,  1.0)
            pct_val = (_gauss_cdf(_hi2, mu, sigma) - _gauss_cdf(_lo2, mu, sigma)) * 100
            pct_str = f"~{pct_val:.1f}%"
        else:
            pct_str = "-"

        pdf.cell(40, 7, pct_str, border="B", fill=fill, align="C")
        pdf.cell(0,  7, sit,    border="B", fill=fill, align="C", ln=True)

    pdf.set_font("Helvetica", "I", 7)
    pdf.set_text_color(*_GRAY)
    pdf.cell(0, 5,
             "(*) Distribuicao estimada a partir do NDVI medio. "
             "Valores exatos disponiveis apos processamento completo do raster.",
             ln=True)
    pdf.set_text_color(*_DARK)
    pdf.ln(3)

    # ── Legenda visual de cores (2 colunas × 2 linhas, centralizada) ──
    # Largura útil: 190mm | 2 colunas | box=8 + gap=3 + texto=62 + sep=10 → total=164mm
    _LEG = [
        (_RED,            "Critico:    < 0.2"),
        (_AMBER,          "Alerta:   0.2 - 0.4"),
        ((132, 204,  22), "Normal:   0.4 - 0.6"),
        (_GREEN,          "Excelente:  > 0.6"),
    ]
    box_w      = 8    # quadrado colorido
    gap_inner  = 3    # entre box e texto
    col_w      = 62   # largura do texto
    gap_cols   = 10   # separação entre as duas colunas
    row_h      = 7
    total_w    = 2 * (box_w + gap_inner + col_w) + gap_cols   # = 164mm
    x_start    = pdf.l_margin + (190 - total_w) / 2           # centraliza

    pdf.set_font("Helvetica", "", 8)
    for row in range(2):                           # 2 linhas
        y_row = pdf.get_y()
        for col in range(2):                       # 2 colunas
            idx        = row * 2 + col
            color, label = _LEG[idx]
            x_item     = x_start + col * (box_w + gap_inner + col_w + gap_cols)
            # quadrado colorido
            pdf.set_fill_color(*color)
            pdf.rect(x_item, y_row + 1.5, box_w, row_h - 2, "F")
            # texto
            pdf.set_xy(x_item + box_w + gap_inner, y_row)
            pdf.set_text_color(*_DARK)
            pdf.cell(col_w, row_h, label, ln=False)
        pdf.ln(row_h)

    pdf.ln(2)

    # ── 5. Histórico de Análises ──────────────────────────────────
    pdf.section_title("5. Historico de Analises Sentinel-2")

    if analyses:
        pdf.set_fill_color(*_GREEN_DARK)
        pdf.set_text_color(*_WHITE)
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(32, 7, "  Imagem",     fill=True)
        pdf.cell(38, 7, "Processado",  fill=True, align="C")
        pdf.cell(26, 7, "NDVI Medio",  fill=True, align="C")
        pdf.cell(28, 7, "Min / Max",   fill=True, align="C")
        pdf.cell(0,  7, "Status",      fill=True, align="C", ln=True)
        pdf.set_text_color(*_DARK)

        for i, a in enumerate(analyses[:20]):
            fill = i % 2 == 0
            if fill:
                pdf.set_fill_color(*_GREEN_LIGHT)
            am  = a.get("ndvi_mean")
            alo = a.get("ndvi_min")
            ahi = a.get("ndvi_max")
            st  = "Valida" if a.get("status") == "valid" else "Nuvem"
            pdf.set_font("Helvetica", "", 8)
            pdf.cell(32, 6, f"  {_fmt_date(a.get('image_date'))}", fill=fill)
            pdf.cell(38, 6, _fmt_datetime(a.get("processed_at")), fill=fill, align="C")
            pdf.cell(26, 6, f"{am:.3f}"  if am  is not None else "-", fill=fill, align="C")
            pdf.cell(28, 6, f"{alo:.2f} / {ahi:.2f}" if alo is not None else "-", fill=fill, align="C")
            pdf.cell(0,  6, st, fill=fill, align="C", ln=True)
    else:
        pdf.set_font("Helvetica", "I", 9)
        pdf.set_text_color(*_GRAY)
        pdf.cell(0, 7, "Sem historico de analises.", ln=True)
        pdf.set_text_color(*_DARK)

    pdf.ln(6)

    # ── 6. Anomalias Detectadas ───────────────────────────────────
    pdf.section_title("6. Anomalias Detectadas")

    active   = [a for a in anomalies if a.get("status") == "active"]
    resolved = [a for a in anomalies if a.get("status") != "active"]

    if anomalies:
        pdf.set_fill_color(*_GREEN_DARK)
        pdf.set_text_color(*_WHITE)
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(35, 7, "  Deteccao",   fill=True)
        pdf.cell(28, 7, "Queda NDVI",  fill=True, align="C")
        pdf.cell(28, 7, "Area (ha)",   fill=True, align="C")
        pdf.cell(50, 7, "Tipo",        fill=True, align="C")
        pdf.cell(0,  7, "Status",      fill=True, align="C", ln=True)
        pdf.set_text_color(*_DARK)

        for i, a in enumerate(anomalies[:15]):
            fill = i % 2 == 0
            if fill:
                pdf.set_fill_color(254, 242, 242)
            tipo = _ANOMALY_TYPE.get(a.get("suspected_type", "unknown"), "A Identificar")
            pdf.set_font("Helvetica", "", 8)
            pdf.cell(35, 6, f"  {_fmt_date(a.get('detected_at'))}", fill=fill)
            pdf.cell(28, 6, f"v {a.get('ndvi_drop_pct', 0):.1f}%", fill=fill, align="C")
            pdf.cell(28, 6, f"{a.get('affected_area_ha', 0):.1f}",  fill=fill, align="C")
            pdf.cell(50, 6, tipo, fill=fill, align="C")
            pdf.cell(0,  6, a.get("status", "active").capitalize(), fill=fill, align="C", ln=True)

        pdf.ln(4)
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(0, 6,
                 f"Total: {len(anomalies)} anomalia(s)  |  Ativas: {len(active)}  |  Resolvidas: {len(resolved)}",
                 ln=True)
    else:
        pdf.set_fill_color(*_GREEN_LIGHT)
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(22, 101, 52)
        pdf.cell(0, 10, "  Nenhuma anomalia detectada - talhao saudavel!", fill=True, ln=True)
        pdf.set_text_color(*_DARK)

    pdf.ln(8)

    # ── 7. Recomendações Agronômicas ──────────────────────────────
    pdf.section_title("7. Recomendacoes Agronomicas")
    pdf.set_font("Helvetica", "", 9)

    if not latest:
        recs = ["Aguardar processamento da primeira imagem Sentinel-2 (2 a 5 dias)."]
    elif (ndvi_v or 0.5) < 0.2:
        recs = [
            "URGENTE: Vigor critico detectado. Realizar vistoria imediata.",
            "Verificar disponibilidade hidrica e estresse severo.",
            "Coletar amostras de solo e foliar para diagnostico.",
            "Consultar engenheiro agronomo antes da proxima aplicacao.",
        ]
    elif (ndvi_v or 0.5) < 0.4:
        recs = [
            "Vistoriar as areas de alerta identificadas no mapa.",
            "Verificar umidade do solo e historico de chuvas.",
            "Avaliar necessidade de fertirrigacao ou aplicacao foliar.",
        ]
    else:
        recs = [
            "Lavoura com vigor adequado para o estagio fenologico.",
            "Manter monitoramento quinzenal via satelite.",
            "Registrar observacoes de campo para calibrar alertas futuros.",
        ]

    if active:
        recs.append(f"Priorizar inspecao das {len(active)} anomalia(s) ativa(s) pelo app Techa.")

    for r in recs:
        pdf.cell(5, 6, chr(149))
        pdf.cell(0, 6, r, ln=True)

    pdf.ln(6)

    # ── Nota de rodapé ────────────────────────────────────────────
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(*_GRAY)
    pdf.multi_cell(
        0, 5,
        "Dados provenientes do satelite Sentinel-2 (ESA/Copernicus). "
        "Resolucao espacial de 10 metros. "
        "Este relatorio e gerado automaticamente pelo sistema Techa e nao substitui "
        "a avaliacao tecnica de um profissional habilitado.",
    )

    return bytes(pdf.output())
