"""`loader_meteorologia` contra la base de test (localidades sintéticas de
`tests/fixtures/insumos/`): los CSV se escriben en una carpeta temporal."""

import pytest

from fitosanitarios.datos.retrievers.territorio import centro_de_localidad, reglas_de_viento
from fitosanitarios.insumos.loader_meteorologia import cargar_centros, cargar_reglas_viento


def _escribir(carpeta, nombre, texto):
    (carpeta / nombre).write_text(texto, encoding="utf-8")


def _localidad(conexion, jurisdiccion_id):
    with conexion.cursor() as cur:
        cur.execute(
            "SELECT id, provincia_id FROM territorio.localidad WHERE jurisdiccion_id = %s",
            (jurisdiccion_id,),
        )
        return cur.fetchone()


def test_carga_el_centro_y_la_regla_de_viento(conexion, tmp_path):
    _escribir(tmp_path, "localidades.csv", (
        "provincia,jurisdiccion,centro_lat,centro_lon,fuente\n"
        "santa-fe,san-carlos-centro,-31.73,-61.09,prueba\n"
    ))
    _escribir(tmp_path, "reglas_viento.csv", (
        "provincia,jurisdiccion,viento_max_kmh,norma,articulo,descripcion\n"
        "santa-fe,san-carlos-centro,10,ordenanza-914-2018,8,"
        "no aplicar con viento hacia la escuela\n"
    ))
    assert cargar_centros(conexion, tmp_path) == 1
    assert cargar_reglas_viento(conexion, tmp_path) == 1

    localidad_id, provincia_id = _localidad(conexion, "san-carlos-centro")
    assert centro_de_localidad(conexion, localidad_id) == (-31.73, -61.09)
    (regla,) = reglas_de_viento(conexion, localidad_id, provincia_id)
    assert regla["norma"] == "ordenanza-914-2018"
    assert regla["articulo"] == "8"
    assert regla["viento_max_kmh"] == 10.0

    # Otra localidad no ve la regla municipal de San Carlos Centro.
    vecina_id, vecina_provincia = _localidad(conexion, "colonia-vecina")
    assert reglas_de_viento(conexion, vecina_id, vecina_provincia) == []


def test_una_localidad_no_cargada_es_un_error_explicito(conexion, tmp_path):
    _escribir(tmp_path, "localidades.csv", (
        "provincia,jurisdiccion,centro_lat,centro_lon,fuente\n"
        "santa-fe,no-existe,-31,-61,prueba\n"
    ))
    with pytest.raises(ValueError, match="no-existe"):
        cargar_centros(conexion, tmp_path)
    conexion.rollback()


def test_una_norma_no_cargada_es_un_error_explicito(conexion, tmp_path):
    _escribir(tmp_path, "reglas_viento.csv", (
        "provincia,jurisdiccion,viento_max_kmh,norma,articulo,descripcion\n"
        "santa-fe,san-carlos-centro,8,ordenanza-1-1900,,inventada\n"
    ))
    with pytest.raises(ValueError, match="ordenanza-1-1900"):
        cargar_reglas_viento(conexion, tmp_path)
    conexion.rollback()


def test_sin_los_archivos_no_carga_nada(conexion, tmp_path):
    assert cargar_centros(conexion, tmp_path) == 0
    assert cargar_reglas_viento(conexion, tmp_path) == 0
