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


def test_agenda_de_varios_dias_trae_cada_dia(conexion):
    thread_id = _thread()
    miercoles = date(2026, 9, 23)
    with conexion.cursor() as cur:
        cur.execute(
            """
            INSERT INTO operacion.receta (thread_id, cultivo, lote, fecha_prevista, estado)
            VALUES (%s, 'soja', '8', %s, 'confirmada')
            """,
            (thread_id, date(2026, 9, 25)),
        )
    conexion.commit()

    resultado = consultar_agenda_tool_logica(
        ConsultarAgendaArgs(fecha="jueves y viernes"), conexion, thread_id, hoy=miercoles
    )
    assert [d["fecha"] for d in resultado.datos["dias"]] == ["2026-09-24", "2026-09-25"]
    assert [len(d["tareas"]) for d in resultado.datos["dias"]] == [0, 1]
    assert resultado.datos["total"] == 1


def test_plantilla_de_varios_dias_muestra_tambien_los_dias_sin_tareas():
    from fitosanitarios.dominio.modelos import ResultadoTool
    from fitosanitarios.tools.consultar_agenda.mensajes import plantilla_agenda

    tarea = {"estado_tarea": "pendiente", "hora": "15:00", "cultivo": "Soja", "lote": "8"}
    datos = {"dias": [
        {"fecha": "2026-09-24", "fecha_legible": "jueves 24/09/2026", "tareas": []},
        {"fecha": "2026-09-25", "fecha_legible": "viernes 25/09/2026", "tareas": [tarea]},
    ]}
    texto = plantilla_agenda(None, [ResultadoTool(estado="ok", datos=datos)])
    assert texto == (
        "*Agenda del jueves 24/09/2026 al viernes 25/09/2026* (1)\n"
        "*Jueves 24/09/2026:* sin tareas\n"
        "*Viernes 25/09/2026:*\n"
        "1. ⏳ 15:00 — Soja — lote 8 (pendiente)"
    )
