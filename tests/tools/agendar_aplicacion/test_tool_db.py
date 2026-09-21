"""Persistencia real de `agendar_aplicacion` y su reflejo en la agenda.
Requiere Postgres con la migración 003 al día (columna `hora_prevista`)."""

import uuid
from datetime import date, timedelta

from fitosanitarios.tools.agendar_aplicacion import (
    AgendarAplicacionArgs,
    agendar_aplicacion_logica,
)
from fitosanitarios.tools.consultar_agenda import (
    ConsultarAgendaArgs,
    consultar_agenda_tool_logica,
)


def test_lo_agendado_aparece_en_la_agenda_de_ese_dia_con_su_hora(conexion):
    thread_id = f"t-agendar-{uuid.uuid4()}"
    manana = date.today() + timedelta(days=1)

    resultado = agendar_aplicacion_logica(
        AgendarAplicacionArgs(fecha="mañana", hora="8:30", cultivo="soja", lote="4"),
        conexion, thread_id,
    )
    assert resultado.estado == "ok"

    agenda = consultar_agenda_tool_logica(
        ConsultarAgendaArgs(fecha=manana.isoformat()), conexion, thread_id
    )
    (tarea,) = agenda.datos["tareas"]
    assert tarea["hora"] == "08:30"
    assert tarea["cultivo"] == "soja"
    assert tarea["estado_tarea"] == "pendiente"


def test_pedir_la_hora_muestra_lo_que_ya_estaba_agendado(conexion):
    thread_id = f"t-agendar-{uuid.uuid4()}"
    agendar_aplicacion_logica(
        AgendarAplicacionArgs(fecha="mañana", hora="8", cultivo="trigo"), conexion, thread_id
    )
    resultado = agendar_aplicacion_logica(
        AgendarAplicacionArgs(fecha="mañana"), conexion, thread_id
    )
    assert resultado.estado == "faltan_datos"
    assert [t["cultivo"] for t in resultado.datos["tareas"]] == ["trigo"]


def test_agenda_de_otro_operario_no_se_mezcla(conexion):
    uno, otro = f"t-agendar-{uuid.uuid4()}", f"t-agendar-{uuid.uuid4()}"
    agendar_aplicacion_logica(AgendarAplicacionArgs(fecha="mañana", hora="8"), conexion, uno)
    resultado = agendar_aplicacion_logica(AgendarAplicacionArgs(fecha="mañana"), conexion, otro)
    assert resultado.datos["tareas"] == []
