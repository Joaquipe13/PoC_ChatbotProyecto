"""Nombres de normas, número de artículo pedido y texto de un artículo."""

import pytest

from fitosanitarios.servicios.normas import (
    filtrar_normas,
    limpiar_texto_articulo,
    norma_legible,
    numero_de_articulo,
)

ARCHIVOS = ["ley-11273-1995", "ley-055297-2017", "ordenanza-841-2010", "decreto-12-2020"]


def test_norma_legible():
    assert norma_legible("ordenanza-841-2010") == "Ordenanza 841/2010"
    assert norma_legible("resolucion-350-1999") == "Resolución 350/1999"
    assert norma_legible("cualquier-cosa") == "cualquier-cosa"


@pytest.mark.parametrize(("texto", "esperado"), [
    ("33", "33"), ("art. 33", "33"), ("artículo 33", "33"), ("Art 33°", "33"),
    ("el 033", "33"), ("5 bis", "5 bis"), ("art 5° bis", "5 bis"), ("articulo 12 ter", "12 ter"),
    ("q dice el art 6", "6"),
])
def test_numero_de_articulo_entiende_como_lo_escribe_la_gente(texto, esperado):
    assert numero_de_articulo(texto) == esperado


@pytest.mark.parametrize("texto", [None, "", "   ", "el de las escuelas", "art"])
def test_numero_de_articulo_sin_numero(texto):
    assert numero_de_articulo(texto) is None


@pytest.mark.parametrize(("texto", "esperado"), [
    ("ley 11273", ["ley-11273-1995"]),
    ("Ley 11.273", ["ley-11273-1995"]),
    ("la ley 11273/1995", ["ley-11273-1995"]),
    ("Ley 11273/1995 (santa-fe)", ["ley-11273-1995"]),  # así se ofrece al repreguntar
    ("ordenanza 841", ["ordenanza-841-2010"]),
    ("ordenanza 841/2010", ["ordenanza-841-2010"]),
    ("la ordenanza n° 841", ["ordenanza-841-2010"]),
    ("ley 55297", ["ley-055297-2017"]),  # ceros a la izquierda
    ("11273", ["ley-11273-1995"]),  # sin el tipo alcanza el número
])
def test_filtrar_normas_por_como_la_nombra_el_usuario(texto, esperado):
    assert filtrar_normas(ARCHIVOS, texto) == esperado


def test_filtrar_normas_respeta_el_tipo_y_el_anio():
    assert filtrar_normas(ARCHIVOS, "decreto 11273") == []  # ese número es una ley
    assert filtrar_normas(ARCHIVOS, "ley 11273/2001") == []  # otro año
    assert filtrar_normas(ARCHIVOS, "ordenanza 12") == []  # el 12 es un decreto


def test_filtrar_normas_sin_texto_no_filtra_y_sin_coincidencia_no_devuelve_nada():
    assert filtrar_normas(ARCHIVOS, None) == ARCHIVOS
    assert filtrar_normas(ARCHIVOS, "  ") == ARCHIVOS
    assert filtrar_normas(ARCHIVOS, "ley 999") == []
    assert filtrar_normas(ARCHIVOS, "la ley de fitosanitarios") == []


def test_limpiar_texto_une_lineas_cortadas_y_saca_el_simbolo_suelto():
    crudo = "\xad Prohíbese la aplicación aérea de\nproductos dentro del radio de\n3.000 metros."
    assert limpiar_texto_articulo(crudo) == (
        "Prohíbese la aplicación aérea de productos dentro del radio de 3.000 metros."
    )


def test_limpiar_texto_deja_un_renglon_por_inciso():
    crudo = (
        "Las excepciones podrán establecerse en los siguientes casos:\n"
        "a) La aplicación aérea de clases C y D podrá\nrealizarse dentro de 500 m.\n"
        "b) La de clase B solo entre 500 y\n3.000 m."
    )
    assert limpiar_texto_articulo(crudo).split("\n") == [
        "Las excepciones podrán establecerse en los siguientes casos:",
        "a) La aplicación aérea de clases C y D podrá realizarse dentro de 500 m.",
        "b) La de clase B solo entre 500 y 3.000 m.",
    ]
