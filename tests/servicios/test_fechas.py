from datetime import date, time

import pytest

from fitosanitarios.servicios.fechas import (
    fecha_legible,
    hora_legible,
    resolver_dias,
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


MIERCOLES = date(2026, 9, 23)


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("semanal", [date(2026, 9, d) for d in range(21, 27)]),
        ("Dame la agenda semanal", [date(2026, 9, d) for d in range(21, 27)]),
        ("la semana que viene", [date(2026, 9, 28), date(2026, 9, 29), date(2026, 9, 30),
                                 date(2026, 10, 1), date(2026, 10, 2), date(2026, 10, 3)]),
        ("Y el jueves y viernes?", [date(2026, 9, 24), date(2026, 9, 25)]),
        ("hoy y mañana", [date(2026, 9, 23), date(2026, 9, 24)]),
        ("lunes, martes y jueves", [date(2026, 9, 28), date(2026, 9, 29), date(2026, 10, 1)]),
        ("del lunes al miércoles", [date(2026, 9, 28), date(2026, 9, 29), date(2026, 9, 30)]),
        ("del 24/09 al 26/09", [date(2026, 9, 24), date(2026, 9, 25), date(2026, 9, 26)]),
        ("martes", [date(2026, 9, 29)]),
        ("mañana", [date(2026, 9, 24)]),
    ],
)
def test_resolver_dias(texto, esperado):
    assert resolver_dias(texto, MIERCOLES) == esperado


def test_resolver_dias_el_domingo_la_semana_es_la_que_empieza():
    domingo = date(2026, 9, 27)
    assert resolver_dias("semana", domingo)[0] == date(2026, 9, 28)


def test_resolver_dias_no_entendido():
    assert resolver_dias("cualquier cosa", MIERCOLES) is None
