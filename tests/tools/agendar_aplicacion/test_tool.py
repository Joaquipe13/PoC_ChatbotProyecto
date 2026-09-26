"""Flujo de `agendar_aplicacion` sin base: la agenda y el INSERT se reemplazan
por dobles (la persistencia real la cubre `test_agendar_aplicacion_db.py`).

Hoy fijo = sábado 19/09/2026."""

from datetime import date, datetime, time

import pytest

from fitosanitarios.dominio.modelos import RespuestaAgente
from fitosanitarios.orquestador.formateador import formatear_respuesta
from fitosanitarios.servicios.localidad import Jurisdiccion
from fitosanitarios.servicios.meteorologia import HoraPronostico
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


# --- pronóstico del tiempo: información, nunca bloquea el agendado ---


EL_TREBOL = Jurisdiccion(id=1, jurisdiccion_id="el-trebol", nombre="El Trébol", provincia_id=10)
ART_4 = {
    "norma": "ordenanza-841-2010", "articulo": "4", "jurisdiccion_id": "el-trebol",
    "viento_max_kmh": 8.0,
    "descripcion": "prohíbe pulverizar con vientos de más de 8 km/h que puedan producir "
                   "derivas hacia la planta urbana",
}


class ClienteFalso:
    def __init__(self, viento=14.0, falla=False):
        self.viento, self.falla, self.pedidos = viento, falla, []

    def horas_del_dia(self, lat, lon, dia):
        self.pedidos.append((lat, lon, dia))
        if self.falla:
            return None
        return [
            HoraPronostico(datetime.combine(dia, time(h)), self.viento, 0, 25.0, 0.0, 10, 20.0, 55)
            for h in range(24)
        ]


@pytest.fixture
def territorio(agenda, monkeypatch):
    guardados = []
    monkeypatch.setattr(modulo, "listar_localidades", lambda c: [EL_TREBOL])
    monkeypatch.setattr(modulo, "centro_de_localidad", lambda c, i: (-32.2, -61.7))
    monkeypatch.setattr(modulo, "reglas_de_viento", lambda c, loc, prov: [ART_4])
    monkeypatch.setattr(modulo, "guardar_pronostico", lambda c, r, p: guardados.append((r, p)))
    return guardados


def _agendar(cliente, **kwargs):
    return agendar_aplicacion_logica(
        AgendarAplicacionArgs(fecha="martes", hora="8:30", **kwargs), None, "t-1",
        hoy=HOY, cliente_meteo=cliente, horizonte_dias=5,
    )


def test_al_agendar_muestra_el_pronostico_y_la_norma_de_viento(territorio):
    cliente = ClienteFalso(viento=14.0)
    r = _agendar(cliente, localidad="el trebol")
    assert r.estado == "ok"
    p = r.datos["pronostico"]
    assert p["estado"] == "ok"
    assert (p["desde"], p["hasta"]) == ("07:00", "10:00")  # 8:30 ± 2 h, en horas enteras
    assert p["viene_de"] == "norte" and p["empuja_hacia"] == "sur"
    assert p["normas"] == [ART_4]
    assert cliente.pedidos == [(-32.2, -61.7, date(2026, 9, 22))]
    assert territorio[0][0] == 77  # se guarda en la receta agendada

    texto = "\n\n".join(
        formatear_respuesta(RespuestaAgente(tipo="agendar_aplicacion"), [r])
    )
    assert "*Pronóstico en El Trébol, de 07:00 a 10:00*" in texto
    assert "- Viento del norte (empuja hacia el sur), 14 km/h, ráfagas de hasta 25 km/h" in texto
    assert "📋 Ordenanza 841/2010, art. 4: prohíbe pulverizar con vientos de más de 8 km/h" in texto
    assert "verificá el viento en el lote" in texto


def test_sin_viento_por_encima_del_umbral_no_se_menciona_la_norma(territorio):
    r = _agendar(ClienteFalso(viento=5.0), localidad="El Trébol")
    assert r.datos["pronostico"]["normas"] == []


def test_mas_alla_del_horizonte_avisa_que_no_hay_pronostico(territorio):
    cliente = ClienteFalso()
    r = agendar_aplicacion_logica(
        AgendarAplicacionArgs(fecha="30/09", hora="8", localidad="El Trébol"), None, "t-1",
        hoy=HOY, cliente_meteo=cliente, horizonte_dias=5,
    )
    assert r.estado == "ok"
    assert r.datos["pronostico"]["estado"] == "lejano"
    assert cliente.pedidos == []
    texto = formatear_respuesta(RespuestaAgente(tipo="agendar_aplicacion"), [r])[0]
    assert "Todavía no hay un pronóstico confiable" in texto


def test_si_la_api_falla_se_agenda_igual_y_se_avisa(territorio):
    r = _agendar(ClienteFalso(falla=True), localidad="El Trébol")
    assert r.estado == "ok"
    assert r.datos["pronostico"]["estado"] == "sin_datos"
    assert territorio == []
    texto = formatear_respuesta(RespuestaAgente(tipo="agendar_aplicacion"), [r])[0]
    assert "No pude consultar el pronóstico" in texto


def test_sin_localidad_o_sin_cliente_no_hay_seccion_de_pronostico(territorio):
    assert _agendar(ClienteFalso()).datos["pronostico"] is None
    assert _agendar(None, localidad="El Trébol").datos["pronostico"] is None
    assert _agendar(ClienteFalso(), localidad="Rosario").datos["pronostico"] is None
