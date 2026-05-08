# app/services/inspection_service.py
# Funções puras de apoio para inspeções de campo.

from typing import Optional


def location_to_wkt(lat: Optional[float], lon: Optional[float]) -> Optional[str]:
    if lat is None or lon is None:
        return None
    return f"POINT({lon} {lat})"


def location_from_wkt(location: Optional[str]) -> tuple[Optional[float], Optional[float]]:
    if not location or not location.startswith("POINT(") or not location.endswith(")"):
        return None, None
    try:
        lon_text, lat_text = location[6:-1].split()
        return float(lat_text), float(lon_text)
    except (ValueError, TypeError):
        return None, None
