"""Tests de integración de datos/retrievers/territorio.py contra Postgres
real (Docker), sobre los insumos reales congelados en `tests/fixtures/insumos/`
(El Trébol con su límite, Sastre y San Jorge sin geometría)."""

from fitosanitarios.datos.retrievers.territorio import (
    localidades_candidatas_por_punto,
    radio_metros_a_grados,
    reglas_candidatas,
    zonas_protegidas_en_radio,
)

# Centro de El Trébol (GeoNames 3856436, ver tests/fixtures/insumos/localidades.csv):
# cae dentro de su límite y de su zona urbana.
LAT_EL_TREBOL, LON_EL_TREBOL = -32.19857, -61.70208


def _localidad(conexion, jurisdiccion_id):
    with conexion.cursor() as cur:
        cur.execute(
            "SELECT id, provincia_id FROM territorio.localidad WHERE jurisdiccion_id = %s",
            (jurisdiccion_id,),
        )
        return cur.fetchone()


def test_localidades_candidatas_por_punto_dentro_de_el_trebol(conexion):
    candidatas = localidades_candidatas_por_punto(conexion, LAT_EL_TREBOL, LON_EL_TREBOL)
    assert "el-trebol" in {c.jurisdiccion_id for c in candidatas}


def test_localidades_candidatas_por_punto_lejano_no_devuelve_nada(conexion):
    candidatas = localidades_candidatas_por_punto(conexion, -50.0, -70.0)
    assert candidatas == []


def test_zonas_protegidas_en_radio_encuentra_la_zona_urbana_real(conexion):
    zonas = zonas_protegidas_en_radio(conexion, LAT_EL_TREBOL, LON_EL_TREBOL, radio_m=2000)
    assert any(z.tipo == "zona_urbana" and z.nombre.startswith("Limite Agronomico") for z in zonas)


def test_zonas_protegidas_radio_chico_no_encuentra_zonas_lejanas(conexion):
    # Con un radio de 1 m, no debería entrar nada salvo estar exactamente encima.
    zonas = zonas_protegidas_en_radio(conexion, -50.0, -70.0, radio_m=1)
    assert zonas == []


def test_radio_metros_a_grados_da_un_valor_positivo_razonable():
    grados = radio_metros_a_grados(2000, lat=-32.2)
    assert 0 < grados < 1  # 2 km son bastante menos que un grado


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
