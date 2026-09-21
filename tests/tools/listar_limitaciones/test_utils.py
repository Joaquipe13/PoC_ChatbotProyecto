"""Filtros de la consulta de limitaciones y opciones a una distancia dada."""

import pytest

from fitosanitarios.servicios.reglas import ReglaCandidata
from fitosanitarios.tools.listar_limitaciones.utils import (
    filtrar_reglas,
    normalizar_bandas,
    normalizar_tipo_aplicacion,
    normalizar_tipo_zona,
    restricciones_a_distancia,
)


def _regla(zona, aplicacion, bandas, distancia, articulo, permitido=False, condiciones=None):
    return ReglaCandidata(
        tipo_zona=zona, tipo_aplicacion=aplicacion, bandas=bandas, distancia_min_m=distancia,
        norma="ley-11273-1995", articulo=articulo, jurisdiccion_id=None, permitido=permitido,
        condiciones=condiciones,
    )


# Las reglas de Santa Fe del reglas.csv (Ley 11.273 y decreto).
AEREA_A_B = _regla("zona_urbana", "aerea", ["Ia", "Ib"], 3000, "33")
AEREA_II = _regla("zona_urbana", "aerea", ["II"], 3000, "33")
AEREA_II_EXC = _regla("zona_urbana", "aerea", ["II"], 500, "51", True, "ordenanza + terreno")
AEREA_CD = _regla("zona_urbana", "aerea", ["III", "IV"], 500, "33")
AEREA_CD_EXC = _regla("zona_urbana", "aerea", ["III", "IV"], 0, "51", True, "ordenanza")
TERRESTRE_AB = _regla("zona_urbana", "terrestre", ["Ia", "Ib", "II"], 500, "34")
PROHIBICIONES = [AEREA_A_B, AEREA_II, AEREA_CD, TERRESTRE_AB]
CONDICIONALES = [AEREA_II_EXC, AEREA_CD_EXC]


def _excepciones(restricciones, prohibicion):
    return next(r.excepciones for r in restricciones if r.prohibicion is prohibicion)


@pytest.mark.parametrize(("texto", "esperado"), [
    ("III", ["III"]), ("iii", ["III"]), ("banda azul", ["III"]), ("roja", ["Ia", "Ib"]),
    ("Amarilla", ["II"]), ("banda II", ["II"]), ("Ia, Ib", ["Ia", "Ib"]), ("verde", ["IV"]),
])
def test_normalizar_bandas(texto, esperado):
    assert normalizar_bandas(texto) == esperado


def test_normalizar_bandas_sin_dato_o_sin_entender():
    assert normalizar_bandas(None) is None and normalizar_bandas("  ") is None
    assert normalizar_bandas("la mas peligrosa") == []


@pytest.mark.parametrize(("texto", "esperado"), [
    ("escuelas", "escuela"), ("una escuela rural", "escuela"), ("zona urbana", "zona_urbana"),
    ("el casco urbano", "zona_urbana"), ("curso de agua", "curso_agua"),
    ("un arroyo", "curso_agua"),
    ("zona_urbana", "zona_urbana"), ("hospital", "hospital"), (None, None),
])
def test_normalizar_tipo_zona(texto, esperado):
    assert normalizar_tipo_zona(texto) == esperado


@pytest.mark.parametrize(("texto", "esperado"), [
    ("aerea", "aerea"), ("aérea", "aerea"), ("con avión", "aerea"), ("terrestre", "terrestre"),
    ("mosquito", "terrestre"), ("dron", "aerea"), ("no sé", None), (None, None),
])
def test_normalizar_tipo_aplicacion(texto, esperado):
    assert normalizar_tipo_aplicacion(texto) == esperado


def test_filtrar_por_aplicacion_banda_y_zona():
    todas = PROHIBICIONES + CONDICIONALES
    assert filtrar_reglas(todas, tipo_aplicacion="terrestre") == [TERRESTRE_AB]
    assert filtrar_reglas(todas, bandas=["III"]) == [AEREA_CD, AEREA_CD_EXC]
    assert filtrar_reglas(todas, tipo_zona="escuela") == []
    # una regla de "todas las bandas" o "todas las aplicaciones" siempre aplica
    general = _regla("zona_urbana", "todas", ["todas"], 300, "2")
    assert filtrar_reglas([general], tipo_aplicacion="aerea", bandas=["II"]) == [general]


def test_a_mil_metros_la_banda_ii_aerea_esta_prohibida_pero_hay_excepcion():
    res = restricciones_a_distancia(PROHIBICIONES, CONDICIONALES, 1000.0, "aerea", ["II"])
    assert _excepciones(res, AEREA_II) == [AEREA_II_EXC]


def test_a_mil_metros_solo_alcanzan_las_prohibiciones_de_mas_de_mil():
    res = restricciones_a_distancia(PROHIBICIONES, CONDICIONALES, 1000.0)
    # C/D aérea (500) y terrestre (500) ya se respetan a 1.000 m.
    assert [r.prohibicion for r in res] == [AEREA_A_B, AEREA_II]


def test_a_300_metros_la_banda_ii_no_tiene_excepcion_pero_c_y_d_si():
    res = restricciones_a_distancia(PROHIBICIONES, CONDICIONALES, 300.0)
    assert _excepciones(res, AEREA_II) == []  # la excepción de clase B empieza a los 500 m
    assert _excepciones(res, AEREA_CD) == [AEREA_CD_EXC]
    assert _excepciones(res, TERRESTRE_AB) == []


def test_la_excepcion_de_una_banda_no_se_ofrece_a_otra():
    res = restricciones_a_distancia(PROHIBICIONES, CONDICIONALES, 1000.0, bandas=["Ia"])
    assert _excepciones(res, AEREA_A_B) == []


def test_a_una_distancia_que_cumple_todo_no_hay_restricciones():
    assert restricciones_a_distancia(PROHIBICIONES, CONDICIONALES, 3000.0) == []


def test_una_prohibicion_para_todas_las_aplicaciones_busca_excepciones_en_ambas():
    general = _regla("escuela", "todas", ["todas"], 100, "8")
    exc_aerea = _regla("escuela", "aerea", ["III"], 20, "9", True, "aviso previo")
    res = restricciones_a_distancia([general], [exc_aerea], 50.0)
    assert res[0].excepciones == [exc_aerea]
    assert restricciones_a_distancia([general], [exc_aerea], 50.0, tipo_aplicacion="terrestre")[
        0
    ].excepciones == []


def test_la_excepcion_provincial_no_levanta_la_prohibicion_de_una_ordenanza():
    # La ley provincial admite la excepción de clase B "por ordenanza"; si la ordenanza
    # de la localidad prohíbe (como la 841/2010), esa excepción no está disponible.
    ordenanza = ReglaCandidata(
        tipo_zona="zona_urbana", tipo_aplicacion="aerea", bandas=["II"], distancia_min_m=3000,
        norma="ordenanza-841-2010", articulo="7", jurisdiccion_id="el-trebol",
    )
    res = restricciones_a_distancia([AEREA_II, ordenanza], [AEREA_II_EXC], 1000.0)
    assert _excepciones(res, AEREA_II) == [AEREA_II_EXC]
    assert _excepciones(res, ordenanza) == []


def test_una_excepcion_municipal_si_levanta_la_prohibicion_provincial():
    autorizacion = ReglaCandidata(
        tipo_zona="zona_urbana", tipo_aplicacion="aerea", bandas=["II"], distancia_min_m=1000,
        norma="ordenanza-1-2020", articulo="4", jurisdiccion_id="pueblo", permitido=True,
        condiciones="con autorización del municipio",
    )
    res = restricciones_a_distancia([AEREA_II], [autorizacion], 1500.0)
    assert _excepciones(res, AEREA_II) == [autorizacion]
