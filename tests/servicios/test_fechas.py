from datetime import date, time

import pytest

from fitosanitarios.servicios.fechas import (
    fecha_legible,
    hora_legible,
    resolver_fecha,
    resolver_hora,
)

HOY = date(2026, 9, 19)  # sábado


@pytest.mark.parametrize(
    ("texto", "esperada"),
    [
        ("hoy", date(2026, 9, 19)),
        ("mañana", date(2026, 9, 20)),
        ("pasado mañana", date(2026, 9, 21)),
        ("martes", date(2026, 9, 22)),
        ("el martes", date(2026, 9, 22)),
        ("el próximo Martes", date(2026, 9, 22)),
        ("miércoles", date(2026, 9, 23)),
        ("2026-10-05", date(2026, 10, 5)),
        ("25/09", date(2026, 9, 25)),
        ("25/09/2026", date(2026, 9, 25)),
        ("5-10-26", date(2026, 10, 5)),
    ],
)
def test_resolver_fecha(texto, esperada):
    assert resolver_fecha(texto, HOY) == esperada


def test_el_mismo_dia_de_la_semana_es_el_proximo_no_hoy():
    assert resolver_fecha("sábado", HOY) == date(2026, 9, 26)


def test_dia_y_mes_ya_pasados_pasan_al_año_siguiente():
    assert resolver_fecha("10/03", HOY) == date(2027, 3, 10)


@pytest.mark.parametrize("texto", [None, "", "  ", "cuando puedas", "31/02", "99/99"])
def test_fecha_no_entendida_devuelve_none(texto):
    assert resolver_fecha(texto, HOY) is None


@pytest.mark.parametrize(
    ("texto", "esperada"),
    [
        ("8", time(8, 0)),
        ("8:30", time(8, 30)),
        ("08.30", time(8, 30)),
        ("a las 14", time(14, 0)),
        ("8hs", time(8, 0)),
        ("3 de la tarde", time(15, 0)),
        ("9am", time(9, 0)),
        ("5 pm", time(17, 0)),
        ("12 de la mañana", time(0, 0)),
    ],
)
def test_resolver_hora(texto, esperada):
    assert resolver_hora(texto) == esperada


@pytest.mark.parametrize("texto", [None, "", "temprano", "25:00", "8:75"])
def test_hora_no_entendida_devuelve_none(texto):
    assert resolver_hora(texto) is None


def test_formatos_legibles():
    assert fecha_legible(date(2026, 9, 22)) == "martes 22/09/2026"
    assert hora_legible(time(8, 5)) == "08:05"
