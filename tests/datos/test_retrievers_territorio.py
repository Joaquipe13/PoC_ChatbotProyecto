"""Tests de integración de datos/retrievers/territorio.py contra Postgres
real (Docker), sobre las localidades sintéticas cargadas en la Fase 3
(san-carlos-centro, colonia-vecina)."""

from fitosanitarios.datos.retrievers.territorio import (
    localidades_candidatas_por_punto,
    radio_metros_a_grados,
    reglas_candidatas,
    zonas_protegidas_en_radio,
)

# Punto real dentro de san-carlos-centro (ver tests/fixtures/insumos/.../localidad.geojson)
LAT_SAN_CARLOS, LON_SAN_CARLOS = -32.9288, -60.6505


def test_localidades_candidatas_por_punto_dentro_de_san_carlos(conexion):
    candidatas = localidades_candidatas_por_punto(conexion, LAT_SAN_CARLOS, LON_SAN_CARLOS)
    jurisdicciones = {c.jurisdiccion_id for c in candidatas}
    assert "san-carlos-centro" in jurisdicciones


def test_localidades_candidatas_por_punto_lejano_no_devuelve_nada(conexion):
    candidatas = localidades_candidatas_por_punto(conexion, -50.0, -70.0)
    assert candidatas == []


def test_zonas_protegidas_en_radio_encuentra_la_escuela_real(conexion):
    zonas = zonas_protegidas_en_radio(conexion, LAT_SAN_CARLOS, LON_SAN_CARLOS, radio_m=2000)
    nombres = {z.nombre for z in zonas}
    assert "Escuela N 12" in nombres


def test_zonas_protegidas_radio_chico_no_encuentra_zonas_lejanas(conexion):
    # Con un radio de 1 m, no debería entrar nada salvo estar exactamente encima.
    zonas = zonas_protegidas_en_radio(conexion, -50.0, -70.0, radio_m=1)
    assert zonas == []


def test_radio_metros_a_grados_da_un_valor_positivo_razonable():
    grados = radio_metros_a_grados(2000, lat=-32.9)
    assert 0 < grados < 1  # 2 km son bastante menos que un grado


def test_reglas_candidatas_de_san_carlos_incluye_la_ordenanza(conexion):
    with conexion.cursor() as cur:
        cur.execute(
            "SELECT id, provincia_id FROM territorio.localidad WHERE jurisdiccion_id = %s",
            ("san-carlos-centro",),
        )
        localidad_id, provincia_id = cur.fetchone()

    reglas = reglas_candidatas(conexion, localidad_id, provincia_id)
    normas = {r.norma for r in reglas}
    assert "ordenanza-914-2018" in normas
    # También trae la provincial de Santa Fe (sin localidad_id asociada)
    assert "ley-13740-2017" in normas


def test_reglas_candidatas_no_mezcla_reglas_de_otra_localidad(conexion):
    with conexion.cursor() as cur:
        cur.execute(
            "SELECT id, provincia_id FROM territorio.localidad WHERE jurisdiccion_id = %s",
            ("san-carlos-centro",),
        )
        localidad_id, provincia_id = cur.fetchone()

    reglas = reglas_candidatas(conexion, localidad_id, provincia_id)
    normas = {r.norma for r in reglas}
    assert "ordenanza-45-2019" not in normas  # esa es de colonia-vecina


def test_reglas_candidatas_sin_localidad_ni_provincia_solo_trae_nacionales(conexion):
    reglas = reglas_candidatas(conexion, localidad_id=None, provincia_id=None)
    # ley-27302-2016 (nacional) no tiene reglas.csv (ver Fase 3), así que la
    # lista puede quedar vacía; lo que sí hay que garantizar es que no
    # aparezca nada de san-carlos-centro ni colonia-vecina.
    normas = {r.norma for r in reglas}
    assert "ordenanza-914-2018" not in normas
    assert "ordenanza-45-2019" not in normas
