"""`loader_meteorologia` contra la base de test, con los insumos reales congelados en
`tests/fixtures/insumos/` (`localidades.csv` y `reglas_viento.csv`). Los casos de error
escriben su propio CSV en una carpeta temporal; al final se recargan los de las
fixtures, porque la base es compartida con los demás archivos."""

from pathlib import Path

import pytest

from fitosanitarios.datos.retrievers.territorio import centro_de_localidad, reglas_de_viento
from fitosanitarios.insumos.loader_meteorologia import cargar_centros, cargar_reglas_viento

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "insumos"


@pytest.fixture
def restaurar(conexion):
    yield
    conexion.rollback()
    cargar_centros(conexion, FIXTURES)
    cargar_reglas_viento(conexion, FIXTURES)


def _escribir(carpeta, nombre, texto):
    (carpeta / nombre).write_text(texto, encoding="utf-8")


def _localidad(conexion, jurisdiccion_id):
    with conexion.cursor() as cur:
        cur.execute(
            "SELECT id, provincia_id FROM territorio.localidad WHERE jurisdiccion_id = %s",
            (jurisdiccion_id,),
        )
        return cur.fetchone()


def test_carga_el_centro_y_la_regla_de_viento_de_el_trebol(conexion, restaurar):
    assert cargar_centros(conexion, FIXTURES) == 3
    assert cargar_reglas_viento(conexion, FIXTURES) == 1

    localidad_id, provincia_id = _localidad(conexion, "el-trebol")
    assert centro_de_localidad(conexion, localidad_id) == (-32.19857, -61.70208)
    (regla,) = reglas_de_viento(conexion, localidad_id, provincia_id)
    assert (regla["norma"], regla["articulo"], regla["viento_max_kmh"]) == (
        "ordenanza-841-2010", "4", 8.0
    )

    # Sastre no ve la regla municipal de El Trébol.
    sastre_id, sastre_provincia = _localidad(conexion, "sastre")
    assert centro_de_localidad(conexion, sastre_id) == (-31.76672, -61.82872)
    assert reglas_de_viento(conexion, sastre_id, sastre_provincia) == []


def test_una_localidad_no_cargada_es_un_error_explicito(conexion, restaurar, tmp_path):
    _escribir(tmp_path, "localidades.csv", (
        "provincia,jurisdiccion,centro_lat,centro_lon,fuente\n"
        "santa-fe,no-existe,-31,-61,prueba\n"
    ))
    with pytest.raises(ValueError, match="no-existe"):
        cargar_centros(conexion, tmp_path)


def test_una_norma_no_cargada_es_un_error_explicito(conexion, restaurar, tmp_path):
    _escribir(tmp_path, "reglas_viento.csv", (
        "provincia,jurisdiccion,viento_max_kmh,norma,articulo,descripcion\n"
        "santa-fe,el-trebol,8,ordenanza-1-1900,,no existe\n"
    ))
    with pytest.raises(ValueError, match="ordenanza-1-1900"):
        cargar_reglas_viento(conexion, tmp_path)


def test_sin_los_archivos_no_carga_nada(conexion, restaurar, tmp_path):
    assert cargar_centros(conexion, tmp_path) == 0
    assert cargar_reglas_viento(conexion, tmp_path) == 0
