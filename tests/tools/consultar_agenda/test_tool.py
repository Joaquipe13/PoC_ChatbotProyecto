import uuid
from datetime import date

from fitosanitarios.tools.consultar_agenda import (
    ConsultarAgendaArgs,
    consultar_agenda_tool_logica,
)


def _thread() -> str:
    return f"t-tool-agenda-{uuid.uuid4()}"


def test_agenda_vacia(conexion):
    resultado = consultar_agenda_tool_logica(ConsultarAgendaArgs(), conexion, _thread())
    assert resultado.estado == "ok"
    assert resultado.datos["total"] == 0
    assert resultado.datos["tareas"] == []


def test_agenda_default_es_hoy(conexion):
    resultado = consultar_agenda_tool_logica(ConsultarAgendaArgs(), conexion, _thread())
    assert resultado.datos["fecha"] == date.today().isoformat()


def test_agenda_con_receta_pendiente(conexion):
    thread_id = _thread()
    hoy = date.today()
    with conexion.cursor() as cur:
        cur.execute(
            """
            INSERT INTO operacion.receta (thread_id, cultivo, lote, fecha_prevista, estado)
            VALUES (%s, 'soja', 'lote A', %s, 'confirmada')
            """,
            (thread_id, hoy),
        )
    conexion.commit()

    resultado = consultar_agenda_tool_logica(ConsultarAgendaArgs(), conexion, thread_id)
    assert resultado.datos["total"] == 1
    assert resultado.datos["tareas"][0]["estado_tarea"] == "pendiente"
