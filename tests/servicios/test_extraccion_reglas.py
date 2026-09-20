"""Lectura determinista de reglas de distancia desde el texto de la norma (sin
reglas.csv). Los textos son de la Ley provincial 11.273 de Santa Fe; sin LLM ni
base: el mismo texto tiene que dar siempre las mismas reglas."""

import pytest

from fitosanitarios.servicios.extraccion_reglas import (
    bandas_de_clases,
    extraer_reglas_de_articulo,
)

ART_33 = (
    "Prohíbese la aplicación aérea de productos fitosanitarios de clase toxicológica A y B\n"
    "dentro del radio de 3.000 metros de las plantas urbanas. Excepcionalmente podrán aplicarse\n"
    "productos de clase toxicológica C o D dentro del radio de 500 metros, cuando en la\n"
    "jurisdicción exista ordenanza municipal o comunal que lo autorice, y en los casos que\n"
    "taxativamente establecerá la reglamentación de la presente. Idéntica excepción y con\n"
    "iguales requisitos podrán establecerse con los productos de clase toxicológica B para ser\n"
    "aplicados en el sector comprendido entre los 500 y 3.000 metros."
)
ART_34 = (
    "Prohíbese la aplicación terrestre de productos fitosanitarios de clase toxicológica A y B "
    "dentro del radio de 500 metros de las plantas urbanas. La aplicación por este medio de "
    "productos de clase toxicológica C y D se podrá realizar dentro del radio de los 500 metros "
    "y conforme a la reglamentación."
)
# Decreto reglamentario 101/2003, art. 53: solo un trámite para una excepción.
ART_53 = (
    "A los efectos de la aplicación terrestre excepcional de productos fitosanitarios de "
    "clases toxicológicas C y D dentro del radio de quinientos ( 500 ) metros de las plantas "
    "urbanas, las empresas proveedoras de servicios, como los particulares deberán solicitar "
    "a los municipios y comunas que le sean fijados los límites de dichas plantas."
)


def _resumen(reglas):
    return [(r.tipo_zona, r.tipo_aplicacion, r.bandas, r.distancia_min_m) for r in reglas]


def test_art_33_solo_da_la_prohibicion_firme_y_descarta_excepciones_y_rangos():
    reglas = extraer_reglas_de_articulo("ley-11273-1995", "33", ART_33)
    assert _resumen(reglas) == [("zona_urbana", "aerea", ["Ia", "Ib", "II"], 3000.0)]
    assert "Prohíbese la aplicación aérea" in reglas[0].oracion


def test_art_34_da_la_prohibicion_terrestre_y_no_el_permiso_de_las_clases_c_y_d():
    reglas = extraer_reglas_de_articulo("ley-11273-1995", "34", ART_34)
    assert _resumen(reglas) == [("zona_urbana", "terrestre", ["Ia", "Ib", "II"], 500.0)]


def test_un_articulo_que_solo_regula_un_tramite_no_da_reglas():
    assert extraer_reglas_de_articulo("decreto-101-2003", "53", ART_53) == []


def test_es_determinista():
    primera = extraer_reglas_de_articulo("ley-11273-1995", "33", ART_33)
    assert all(extraer_reglas_de_articulo("ley-11273-1995", "33", ART_33) == primera
               for _ in range(5))


@pytest.mark.parametrize("texto", [
    # excepción o permiso condicionado
    "Prohíbese la aplicación aérea dentro del radio de 500 metros de las plantas urbanas, "
    "salvo que una ordenanza lo autorice.",
    "Excepcionalmente podrán aplicarse productos de clase C dentro de 500 metros de las "
    "plantas urbanas.",
    # sin prohibición
    "La aplicación terrestre se realizará a más de 500 metros de las plantas urbanas.",
    # dos distancias en una misma oración
    "Prohíbese la aplicación aérea dentro de 500 metros de las escuelas y de 1.000 metros de las "
    "plantas urbanas.",
    # un rango
    "Prohíbese la aplicación aérea en el sector comprendido entre los 500 y 3.000 metros de las "
    "plantas urbanas.",
    # dos tipos de zona con una sola distancia: no se sabe si vale para ambas
    "Prohíbese la aplicación dentro de 300 metros de las escuelas y de las plantas urbanas.",
    # sin distancia
    "Prohíbese la aplicación aérea de productos de clase A en las plantas urbanas.",
    # clase que el parser no entiende
    "Prohíbese la aplicación de productos de clase toxicológica Z dentro de 500 metros de las "
    "plantas urbanas.",
    # una distancia que no es de una zona a proteger
    "Prohíbese el almacenamiento de fitosanitarios a menos de 300 metros del depósito.",
])
def test_lo_ambiguo_condicionado_o_incompleto_no_se_extrae(texto):
    assert extraer_reglas_de_articulo("ley-1-2000", "1", texto) == []


def test_sin_clases_la_prohibicion_vale_para_todas_las_bandas():
    (regla,) = extraer_reglas_de_articulo(
        "ordenanza-1-2000", "4",
        "Queda prohibida la aplicación terrestre de fitosanitarios a menos de 100 metros de "
        "las escuelas.",
    )
    assert _resumen([regla]) == [("escuela", "terrestre", ["todas"], 100.0)]


def test_la_distancia_en_km_se_convierte_a_metros():
    (regla,) = extraer_reglas_de_articulo(
        "ordenanza-1-2000", "5",
        "Prohíbese la aplicación aérea a menos de 3 km de las plantas urbanas.",
    )
    assert regla.distancia_min_m == 3000.0


def test_el_numero_escrito_en_letras_y_en_digitos_se_lee_una_vez():
    (regla,) = extraer_reglas_de_articulo(
        "ley-1-2000", "6",
        "Prohíbese la aplicación aérea dentro del radio de quinientos ( 500 ) metros de las "
        "plantas urbanas.",
    )
    assert regla.distancia_min_m == 500.0


def test_las_clases_viejas_se_traducen_a_bandas_con_una_tabla_fija():
    assert bandas_de_clases(["A", "B"]) == ["Ia", "Ib", "II"]
    assert bandas_de_clases(["C", "D"]) == ["III", "IV"]
    assert bandas_de_clases(["amarilla"]) == ["II"]
    assert bandas_de_clases(["Ia", "II"]) == ["Ia", "II"]


def test_una_clase_desconocida_no_se_adivina():
    assert bandas_de_clases(["A", "Z"]) is None
