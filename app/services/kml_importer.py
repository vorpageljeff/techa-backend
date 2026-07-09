# app/services/kml_importer.py
# Conversão mínima de KML exportado do Google Earth para GeoJSON.

from dataclasses import dataclass
import xml.etree.ElementTree as ET


@dataclass(frozen=True)
class KmlPolygon:
    name: str | None
    geometry: dict


def _tag_name(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def _children(element: ET.Element, name: str) -> list[ET.Element]:
    return [child for child in element if _tag_name(child) == name]


def _first_child(element: ET.Element, name: str) -> ET.Element | None:
    for child in element:
        if _tag_name(child) == name:
            return child
    return None


def _text_child(element: ET.Element, name: str) -> str | None:
    child = _first_child(element, name)
    if child is None or child.text is None:
        return None
    value = child.text.strip()
    return value or None


def _parse_coordinates(text: str) -> list[list[float]]:
    coordinates: list[list[float]] = []
    for item in text.split():
        parts = item.split(",")
        if len(parts) < 2:
            continue
        lon = float(parts[0])
        lat = float(parts[1])
        coordinates.append([lon, lat])

    if len(coordinates) < 4:
        raise ValueError("Polígono KML precisa ter pelo menos 4 coordenadas")
    if coordinates[0] != coordinates[-1]:
        coordinates.append(coordinates[0])
    return coordinates


def _parse_linear_ring(parent: ET.Element) -> list[list[float]]:
    ring = _first_child(parent, "LinearRing")
    if ring is None:
        raise ValueError("Polygon KML sem LinearRing")

    coords = _text_child(ring, "coordinates")
    if not coords:
        raise ValueError("LinearRing KML sem coordinates")
    return _parse_coordinates(coords)


def _parse_polygon(polygon: ET.Element) -> list[list[list[float]]]:
    outer = _first_child(polygon, "outerBoundaryIs")
    if outer is None:
        raise ValueError("Polygon KML sem outerBoundaryIs")

    rings = [_parse_linear_ring(outer)]
    for inner in _children(polygon, "innerBoundaryIs"):
        rings.append(_parse_linear_ring(inner))
    return rings


def _iter_descendants(element: ET.Element, name: str):
    for child in element.iter():
        if _tag_name(child) == name:
            yield child


def parse_kml_polygons(kml_text: str) -> list[KmlPolygon]:
    """
    Extrai Polygon/MultiPolygon de um KML.

    Retorna uma lista porque um arquivo pode conter vários Placemarks. Cada
    Placemark vira um talhão no endpoint de importação.
    """
    try:
        root = ET.fromstring(kml_text)
    except ET.ParseError as exc:
        raise ValueError(f"KML inválido: {exc}") from exc

    parsed: list[KmlPolygon] = []
    placemarks = list(_iter_descendants(root, "Placemark"))
    targets = placemarks or [root]

    for target in targets:
        name = _text_child(target, "name")
        polygons = [_parse_polygon(polygon) for polygon in _iter_descendants(target, "Polygon")]
        if not polygons:
            continue

        geometry = (
            {"type": "Polygon", "coordinates": polygons[0]}
            if len(polygons) == 1
            else {"type": "MultiPolygon", "coordinates": polygons}
        )
        parsed.append(KmlPolygon(name=name, geometry=geometry))

    if not parsed:
        raise ValueError("Nenhum polígono encontrado no KML")

    return parsed
