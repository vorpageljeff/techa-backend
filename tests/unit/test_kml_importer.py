from app.services.kml_importer import parse_kml_polygons


def test_parse_google_earth_kml_polygon():
    kml = """<?xml version="1.0" encoding="UTF-8"?>
    <kml xmlns="http://www.opengis.net/kml/2.2">
      <Document>
        <Placemark>
          <name>Talhao Real</name>
          <Polygon>
            <outerBoundaryIs>
              <LinearRing>
                <coordinates>
                  -54.7589,-25.4036,0 -54.7615,-25.4059,0
                  -54.7623,-25.4084,0 -54.7589,-25.4036,0
                </coordinates>
              </LinearRing>
            </outerBoundaryIs>
          </Polygon>
        </Placemark>
      </Document>
    </kml>
    """

    fields = parse_kml_polygons(kml)

    assert len(fields) == 1
    assert fields[0].name == "Talhao Real"
    assert fields[0].geometry["type"] == "Polygon"
    assert fields[0].geometry["coordinates"][0][0] == [-54.7589, -25.4036]


def test_parse_kml_closes_open_ring():
    kml = """<kml xmlns="http://www.opengis.net/kml/2.2">
      <Placemark>
        <Polygon>
          <outerBoundaryIs>
            <LinearRing>
              <coordinates>
                -54,-25,0 -55,-25,0 -55,-26,0 -54,-26,0
              </coordinates>
            </LinearRing>
          </outerBoundaryIs>
        </Polygon>
      </Placemark>
    </kml>
    """

    [field] = parse_kml_polygons(kml)
    ring = field.geometry["coordinates"][0]

    assert ring[0] == ring[-1]


def test_parse_kml_rejects_file_without_polygon():
    kml = """<kml xmlns="http://www.opengis.net/kml/2.2"><Document /></kml>"""

    try:
        parse_kml_polygons(kml)
        assert False, "parse_kml_polygons deveria rejeitar KML sem polígono"
    except ValueError as exc:
        assert "Nenhum polígono" in str(exc)
