"""Flujo de `agendar_aplicacion` sin base: la agenda y el INSERT se reemplazan
por dobles (la persistencia real la cubre `test_agendar_aplicacion_db.py`).

Hoy fijo = sábado 19/09/2026."""

from datetime import date, time

import pytest

from fitosanitarios.tools.agendar_aplicacion import (
    AgendarAplicacionArgs,
    agendar_aplicacion_logica,
)
from fitosanitarios.tools.agendar_aplicacion import tool as modulo

HOY = date(2026, 9, 19)


@pytest.fixture
def agenda(monkeypatch):
    """Tareas ya agendadas por fecha ISO, y registro de lo que se agendó."""
    estado = {"tareas": {}, "agendado": []}

    def consultar(conn, thread_id, fecha):
        return estado["tareas"].get(fecha.isoformat(), [])

    def agendar(conn, thread_id, fecha, hora, datos_receta):
        estado["agendado"].append((fecha, hora, datos_receta))
        en_esa_hora = hora.strftime("%H:%M")
        choques = [t for t in consultar(conn, thread_id, fecha) if t["hora"] == en_esa_hora]
        return 77, choques

    monkeypatch.setattr(modulo, "consultar_agenda_logica", consultar)
    monkeypatch.setattr(modulo, "agendar", agendar)
    return estado


def _logica(**kwargs):
    return agendar_aplicacion_logica(AgendarAplicacionArgs(**kwargs), None, "t-1", hoy=HOY)


def test_si_agendala_sin_fecha_pregunta_la_fecha(agenda):
    resultado = _logica()
    assert resultado.estado == "faltan_datos"
    assert resultado.faltantes[0].campo == "fecha"
    assert agenda["agendado"] == []


def test_agendala_para_el_martes_muestra_la_agenda_de_ese_dia_y_pregunta_la_hora(agenda):
    agenda["tareas"]["2026-09-22"] = [
        {"cultivo": "soja", "lote": "4", "hora": "08:00", "estado_tarea": "pendiente"}
    ]
    resultado = _logica(fecha="martes")
    assert resultado.estado == "faltan_datos"
    assert resultado.datos["fecha"] == "2026-09-22"  # el próximo martes, resuelto en código
    assert resultado.datos["fecha_legible"] == "martes 22/09/2026"
    assert resultado.datos["tareas"] == agenda["tareas"]["2026-09-22"]
    assert resultado.faltantes[0].campo == "hora"
    assert agenda["agendado"] == []


def test_con_fecha_y_hora_agenda_con_los_datos_de_la_receta(agenda):
    resultado = _logica(fecha="2026-09-22", hora="8:30", cultivo="soja", lote="4")
    assert resultado.estado == "ok"
    assert resultado.datos["hora"] == "08:30"
    assert resultado.datos["receta_id"] == 77
    (fecha, hora, datos_receta), = agenda["agendado"]
    assert (fecha, hora) == (date(2026, 9, 22), time(8, 30))
    assert datos_receta["cultivo"] == "soja" and datos_receta["lote"] == "4"


def test_avisa_si_ya_hay_una_tarea_a_esa_hora_pero_agenda(agenda):
    agenda["tareas"]["2026-09-22"] = [
        {"cultivo": "trigo", "lote": "2", "hora": "08:30", "estado_tarea": "pendiente"}
    ]
    resultado = _logica(fecha="martes", hora="8:30")
    assert resultado.estado == "ok"
    assert any("trigo" in a and "08:30" in a for a in resultado.advertencias)


def test_fecha_pasada_repregunta_la_fecha(agenda):
    resultado = _logica(fecha="14/09/2026")
    assert resultado.estado == "faltan_datos"
    assert resultado.faltantes[0].campo == "fecha"
    assert "ya pasó" in resultado.faltantes[0].motivo


def test_fecha_no_entendida_repregunta_la_fecha(agenda):
    resultado = _logica(fecha="cuando puedas")
    assert resultado.faltantes[0].campo == "fecha"
    assert "no entendí" in resultado.faltantes[0].motivo


def test_hora_no_entendida_vuelve_a_preguntar_el_horario_sin_agendar(agenda):
    resultado = _logica(fecha="martes", hora="temprano")
    assert resultado.faltantes[0].campo == "hora"
    assert "no entendí" in resultado.faltantes[0].motivo
    assert agenda["agendado"] == []


def test_agendar_para_hoy_es_valido(agenda):
    resultado = _logica(fecha="hoy", hora="15")
    assert resultado.estado == "ok"
    assert resultado.datos["fecha"] == "2026-09-19"
