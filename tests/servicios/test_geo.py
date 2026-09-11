"""Tests de servicios/geo.py usando la geometría real de la fixture de San
Carlos Centro (tests/fixtures/insumos/localidades/san-carlos-centro/), la
misma localidad y escuela de los ejemplos de referencia de la skill."""

from fitosanitarios.servicios.geo import (
    LocalidadCandidata,
    ZonaCandidata,
    calcular_distancias,
    resolver_jurisdiccion,
)

# Límite real de la fixture san-carlos-centro (ver tests/fixtures/insumos/.../localidad.geojson)
LIMITE_SAN_CARLOS = {
    "type": "Polygon",
    "coordinates": [[
        [-60.660, -32.930], [-60.640, -32.930],
        [-60.640, -32.910], [-60.660, -32.910],
        [-60.660, -32.930],
    ]],
}

# Escuela N 12 real de la fixture: [-60.6505, -32.9295]
ESCUELA_LON, ESCUELA_LAT = -60.6505, -32.9295

# Puntos calculados con pyproj.Geod (WGS84) exactamente al norte de la escuela,
# a la distancia indicada (ver DECISIONES.md para cómo se calcularon).
PUNTO_A_80M = (-32.92877865019107, -60.6505)
PUNTO_A_100M = (-32.9285983127258, -60.6505)
PUNTO_A_150M = (-32.92814746903985, -60.6505)


def _localidad_san_carlos() -> LocalidadCandidata:
    return LocalidadCandidata(
        id=1, jurisdiccion_id="san-carlos-centro", nombre="San Carlos Centro",
        provincia_id=1, limite=LIMITE_SAN_CARLOS,
    )


def _escuela() -> ZonaCandidata:
    return ZonaCandidata(
        id=1, tipo="escuela", nombre="Escuela N 12", jurisdiccion_id="san-carlos-centro",
        geometria={"type": "Point", "coordinates": [ESCUELA_LON, ESCUELA_LAT]},
    )


# --- resolver_jurisdiccion ---


def test_punto_dentro_del_limite_resuelve_la_localidad():
    lat, lon = PUNTO_A_80M
    resultado = resolver_jurisdiccion(lat, lon, [_localidad_san_carlos()])
    assert resultado is not None
    assert resultado.jurisdiccion_id == "san-carlos-centro"


def test_punto_fuera_de_todas_las_localidades_devuelve_none():
    # Muy lejos de San Carlos Centro (varios grados de distancia)
    resultado = resolver_jurisdiccion(-30.0, -55.0, [_localidad_san_carlos()])
    assert resultado is None


def test_punto_sin_localidades_candidatas_devuelve_none():
    lat, lon = PUNTO_A_80M
    assert resolver_jurisdiccion(lat, lon, []) is None


def test_punto_sobre_el_borde_del_limite_resuelve_la_localidad():
    # Exactamente sobre el vértice del polígono (caso borde: ni claramente
    # dentro ni claramente afuera).
    resultado = resolver_jurisdiccion(-32.930, -60.660, [_localidad_san_carlos()])
    assert resultado is not None


# --- calcular_distancias ---


def test_punto_a_80m_de_la_escuela_da_80_metros_aprox():
    lat, lon = PUNTO_A_80M
    resultados = calcular_distancias(lat, lon, [_escuela()])
    assert len(resultados) == 1
    # Tolerancia de 1 m: la reproyección UTM introduce un error mínimo, no
    # geodésico exacto, pero tiene que ser prácticamente 80.
    assert abs(resultados[0].distancia_m - 80.0) < 1.0


def test_punto_a_100m_de_la_escuela():
    lat, lon = PUNTO_A_100M
    resultados = calcular_distancias(lat, lon, [_escuela()])
    assert abs(resultados[0].distancia_m - 100.0) < 1.0


def test_punto_dentro_de_una_zona_da_0_metros():
    # El punto coincide exactamente con la geometría de la zona (un Point).
    resultados = calcular_distancias(ESCUELA_LAT, ESCUELA_LON, [_escuela()])
    assert resultados[0].distancia_m == 0.0


def test_sin_zonas_candidatas_devuelve_lista_vacia():
    lat, lon = PUNTO_A_80M
    assert calcular_distancias(lat, lon, []) == []


def test_zona_como_poligono_distancia_correcta():
    # Zona urbana real de la fixture (polígono, no punto)
    zona_urbana = ZonaCandidata(
        id=2, tipo="zona_urbana", nombre="Casco urbano", jurisdiccion_id="san-carlos-centro",
        geometria={
            "type": "Polygon",
            "coordinates": [[
                [-60.652, -32.922], [-60.648, -32.922],
                [-60.648, -32.918], [-60.652, -32.918],
                [-60.652, -32.922],
            ]],
        },
    )
    # Un punto claramente adentro del polígono
    resultados = calcular_distancias(-32.920, -60.650, [zona_urbana])
    assert resultados[0].distancia_m == 0.0


def test_zona_como_linestring():
    # Arroyo real de la fixture (LineString, no punto ni polígono)
    curso_agua = ZonaCandidata(
        id=3, tipo="curso_agua", nombre="Arroyo del Medio", jurisdiccion_id="san-carlos-centro",
        geometria={
            "type": "LineString",
            "coordinates": [[-60.660, -32.920], [-60.640, -32.918]],
        },
    )
    resultados = calcular_distancias(-32.925, -60.650, [curso_agua])
    assert resultados[0].distancia_m > 0  # el punto no está sobre la línea
    assert resultados[0].tipo == "curso_agua"


def test_varias_zonas_devuelve_una_distancia_por_cada_una():
    lat, lon = PUNTO_A_80M
    otra_escuela = ZonaCandidata(
        id=4, tipo="escuela", nombre="Otra escuela", jurisdiccion_id="colonia-vecina",
        geometria={"type": "Point", "coordinates": [-60.620, -32.920]},
    )
    resultados = calcular_distancias(lat, lon, [_escuela(), otra_escuela])
    assert len(resultados) == 2
    assert {r.jurisdiccion_id for r in resultados} == {"san-carlos-centro", "colonia-vecina"}
