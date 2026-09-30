"""Tests de integración de datos/retrievers/territorio.py contra Postgres
real (Docker), sobre los insumos reales congelados en `tests/fixtures/insumos/`
(El Trébol, Sastre y San Jorge)."""

from fitosanitarios.datos.retrievers.territorio import reglas_candidatas


def _localidad(conexion, jurisdiccion_id):
    with conexion.cursor() as cur:
        cur.execute(
            "SELECT id, provincia_id FROM territorio.localidad WHERE jurisdiccion_id = %s",
            (jurisdiccion_id,),
        )
        return cur.fetchone()

def test_reglas_candidatas_de_el_trebol_incluye_la_ordenanza_y_la_ley(conexion):
    localidad_id, provincia_id = _localidad(conexion, "el-trebol")
    normas = {r.norma for r in reglas_candidatas(conexion, localidad_id, provincia_id)}
    assert "ordenanza-841-2010" in normas
    # También trae la provincial de Santa Fe (sin localidad_id asociada)
    assert "ley-11273-1995" in normas

def test_reglas_candidatas_no_mezcla_reglas_de_otra_localidad(conexion):
    localidad_id, provincia_id = _localidad(conexion, "el-trebol")
    normas = {r.norma for r in reglas_candidatas(conexion, localidad_id, provincia_id)}
    assert "ordenanza-1174-2019" not in normas  # esa es de Sastre
    assert "fallo-san-jorge-2009" not in normas

def test_reglas_candidatas_sin_localidad_ni_provincia_no_trae_municipales(conexion):
    # Sin localidad ni provincia solo entrarían las nacionales, y los insumos no tienen
    # normativa nacional: la lista queda vacía.
    assert reglas_candidatas(conexion, localidad_id=None, provincia_id=None) == []

def test_reglas_candidatas_solo_trae_prohibiciones_salvo_que_se_pidan_las_condicionales(conexion):
    localidad_id, provincia_id = _localidad(conexion, "el-trebol")

    prohibiciones = reglas_candidatas(conexion, localidad_id, provincia_id)
    assert prohibiciones and not any(r.permitido for r in prohibiciones)

    condicionales = reglas_candidatas(conexion, localidad_id, provincia_id, permitido=True)
    assert condicionales and all(r.permitido for r in condicionales)
    assert all(r.condiciones for r in condicionales)
