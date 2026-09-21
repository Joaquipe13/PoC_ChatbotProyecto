import pytest

from fitosanitarios.servicios.condiciones_aplicacion import (
    banda_de_la_aplicacion,
    calcular_condiciones,
)
from fitosanitarios.servicios.reglas import ReglaCandidata


def _regla(zona="zona_urbana", aplicacion="aerea", bandas=None, metros=500, articulo="6"):
    return ReglaCandidata(
        tipo_zona=zona, tipo_aplicacion=aplicacion, bandas=bandas or ["todas"],
        distancia_min_m=metros, norma="ordenanza-841-2010", articulo=articulo,
        jurisdiccion_id="el-trebol",
    )


# Reglas reales de El Trébol (data/insumos/santa-fe/el-trebol/reglas.csv).
REGLAS_EL_TREBOL = [_regla(), _regla(bandas=["II"], metros=3000, articulo="7")]


def test_banda_de_la_aplicacion_es_la_mas_peligrosa_de_la_mezcla():
    assert banda_de_la_aplicacion(["IV", "II", "III"]) == "II"
    assert banda_de_la_aplicacion(["III", "Ib"]) == "Ib"


def test_banda_ignora_desconocidas_y_devuelve_none_si_no_hay_ninguna():
    assert banda_de_la_aplicacion(["IV", None]) == "IV"
    assert banda_de_la_aplicacion([None]) is None
    assert banda_de_la_aplicacion([]) is None


def test_distancia_de_la_regla_por_banda_gana_la_mas_restrictiva_y_cita_ambas():
    condiciones = calcular_condiciones(
        "El Trébol", "aerea", {"Producto A": "IV", "Producto B": "II"}, REGLAS_EL_TREBOL
    )
    assert condiciones.banda == "II"
    assert condiciones.banda_color == "amarilla"
    (distancia,) = condiciones.distancias_minimas
    assert distancia.tipo_zona == "zona_urbana"
    assert distancia.distancia_min_m == 3000
    assert {c.articulo for c in distancia.citas} == {"6", "7"}


def test_banda_menos_peligrosa_usa_solo_la_regla_general():
    condiciones = calcular_condiciones("El Trébol", "aerea", {"Producto A": "IV"}, REGLAS_EL_TREBOL)
    assert condiciones.distancias_minimas[0].distancia_min_m == 500


def test_tipo_de_aplicacion_sin_regla_avisa_y_no_inventa_distancia():
    condiciones = calcular_condiciones(
        "El Trébol", "terrestre", {"Producto A": "IV"}, REGLAS_EL_TREBOL
    )
    assert condiciones.distancias_minimas == []
    assert any("No hay una distancia mínima cargada" in a for a in condiciones.advertencias)


def test_informa_una_distancia_por_cada_tipo_de_zona():
    reglas = [_regla(zona="zona_urbana", metros=500), _regla(zona="escuela", metros=1000)]
    condiciones = calcular_condiciones("El Trébol", "aerea", {"Producto A": "IV"}, reglas)
    assert {d.tipo_zona: d.distancia_min_m for d in condiciones.distancias_minimas} == {
        "zona_urbana": 500, "escuela": 1000,
    }


def test_producto_sin_banda_no_asume_una_y_queda_marcado():
    condiciones = calcular_condiciones(
        "El Trébol", "aerea", {"Producto A": "IV", "Producto X": None}, REGLAS_EL_TREBOL
    )
    assert condiciones.banda == "IV"
    assert condiciones.productos_sin_banda == ["Producto X"]


def test_sin_ninguna_banda_solo_aplican_reglas_para_todas_las_bandas():
    condiciones = calcular_condiciones("El Trébol", "aerea", {"Producto X": None}, REGLAS_EL_TREBOL)
    assert condiciones.banda is None
    assert condiciones.distancias_minimas[0].distancia_min_m == 500


def test_sin_normativa_municipal_se_aclara_y_se_usa_la_provincial():
    provincial = ReglaCandidata(
        tipo_zona="zona_urbana", tipo_aplicacion="todas", bandas=["todas"],
        distancia_min_m=300, norma="ley-13740-2017", articulo="2", jurisdiccion_id=None,
    )
    condiciones = calcular_condiciones(
        "Rosario", "terrestre", {"Producto A": "IV"}, [provincial], con_normativa_municipal=False
    )
    assert condiciones.sin_normativa_municipal is True
    assert condiciones.advertencias == [
        "No se cuenta con la normativa municipal de Rosario: la distancia se basa en la "
        "normativa provincial"
    ]
    (distancia,) = condiciones.distancias_minimas
    assert distancia.distancia_min_m == 300
    assert distancia.norma_limitante.norma == "ley-13740-2017"


def test_con_normativa_municipal_no_hay_aclaracion():
    condiciones = calcular_condiciones("El Trébol", "aerea", {"Producto A": "IV"}, REGLAS_EL_TREBOL)
    assert condiciones.sin_normativa_municipal is False
    assert condiciones.advertencias == []


def test_una_regla_leida_del_pdf_marca_la_distancia_como_extraida():
    leida = ReglaCandidata(
        tipo_zona="zona_urbana", tipo_aplicacion="aerea", bandas=["Ia", "Ib", "II"],
        distancia_min_m=3000, norma="ley-11273-1995", articulo="33", jurisdiccion_id=None,
        fuente="pdf_extraido",
    )
    condiciones = calcular_condiciones("Rosario", "aerea", {"Producto A": "II"}, [leida])
    (distancia,) = condiciones.distancias_minimas
    assert distancia.extraida_de_pdf is True
    assert distancia.norma_limitante.articulo == "33"


def test_una_regla_de_csv_no_se_marca_como_extraida():
    condiciones = calcular_condiciones("El Trébol", "aerea", {"Producto A": "IV"}, REGLAS_EL_TREBOL)
    assert condiciones.distancias_minimas[0].extraida_de_pdf is False


@pytest.mark.parametrize("escrito", ["aerea", "aérea", "Aérea", "aplicación aérea", "con avión"])
def test_el_tipo_de_aplicacion_se_normaliza_antes_de_buscar_reglas(escrito):
    """Gemini puede mandar "aérea" con tilde: no tiene que dejar sin distancia al dictamen."""
    reglas = [ReglaCandidata(
        tipo_zona="zona_urbana", tipo_aplicacion="aerea", bandas=["todas"], distancia_min_m=1000,
        norma="Ley X", articulo="1", jurisdiccion_id=None,
    )]
    condiciones = calcular_condiciones("El Trébol", escrito, {"Flyer": "II"}, reglas)
    assert condiciones.tipo_aplicacion == "aerea"
    assert [d.distancia_min_m for d in condiciones.distancias_minimas] == [1000]
