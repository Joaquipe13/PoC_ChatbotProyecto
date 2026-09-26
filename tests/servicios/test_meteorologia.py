"""Cliente de Open-Meteo, con una respuesta real guardada (El Trébol, 26/09/2026): sin red."""

import json
from datetime import date, datetime
from pathlib import Path

import httpx

from fitosanitarios.servicios import meteorologia
from fitosanitarios.servicios.meteorologia import (
    ClienteOpenMeteo,
    franja,
    horas_de_la_respuesta,
)

RESPUESTA = json.loads(
    (Path(__file__).parents[1] / "fixtures" / "meteo" / "open_meteo_el_trebol_2026-09-26.json")
    .read_text(encoding="utf-8")
)


def test_la_respuesta_se_lee_hora_por_hora():
    horas = horas_de_la_respuesta(RESPUESTA)
    assert len(horas) == 24
    ocho = horas[8]
    assert ocho.hora == datetime(2026, 9, 26, 8, 0)
    assert ocho.viento_kmh == 18.2
    assert ocho.direccion_grados == 110
    assert ocho.rafagas_kmh == 30.6
    assert ocho.lluvia_mm == 0.0


def test_la_franja_es_la_hora_agendada_mas_menos_dos_horas():
    horas = franja(horas_de_la_respuesta(RESPUESTA), datetime(2026, 9, 26, 8, 30))
    assert [h.hora.hour for h in horas] == [7, 8, 9, 10]


def test_una_respuesta_sin_horas_no_rompe():
    assert horas_de_la_respuesta({}) == []


class _Respuesta:
    def raise_for_status(self):
        pass

    def json(self):
        return RESPUESTA


def test_el_cliente_pide_el_dia_y_reutiliza_la_respuesta(monkeypatch):
    pedidos = []

    def get(url, params, timeout):
        pedidos.append(params)
        return _Respuesta()

    monkeypatch.setattr(meteorologia.httpx, "get", get)
    cliente = ClienteOpenMeteo("https://ejemplo")
    assert len(cliente.horas_del_dia(-32.2, -61.7, date(2026, 9, 26))) == 24
    assert len(cliente.horas_del_dia(-32.2, -61.7, date(2026, 9, 26))) == 24
    assert len(pedidos) == 1  # la segunda vez sale del caché
    assert pedidos[0]["start_date"] == pedidos[0]["end_date"] == "2026-09-26"
    assert pedidos[0]["timezone"] == "America/Argentina/Buenos_Aires"


def test_si_la_api_falla_no_hay_pronostico(monkeypatch):
    def get(url, params, timeout):
        raise httpx.ConnectError("sin red")

    monkeypatch.setattr(meteorologia.httpx, "get", get)
    cliente = ClienteOpenMeteo("https://ejemplo")
    assert cliente.horas_del_dia(-32.2, -61.7, date(2026, 9, 26)) is None
