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
