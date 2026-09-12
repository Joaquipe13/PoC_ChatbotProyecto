"""Tests de iniciar/finalizar evento y agenda (Fase 9, RF7/RF9) contra
Postgres real. `thread_id` único por test (`uuid4`): son filas reales sin
rollback entre tests, un thread_id fijo se contamina entre corridas de la
suite completa (mismo hallazgo que Fase 8, ver DIFICULTADES.md)."""

import uuid
from datetime import date, timedelta

from fitosanitarios.dominio.motivos import MotivoNoResuelto
from fitosanitarios.servicios.eventos import (
    consultar_agenda_logica,
    finalizar_evento,
    iniciar_evento,
)
from fitosanitarios.servicios.resolucion_vehiculo import resolver_vehiculo


def _thread() -> str:
    return f"t-evento-test-{uuid.uuid4()}"


def test_iniciar_y_finalizar_evento(conexion):
    thread_id = _thread()
    resolucion = resolver_vehiculo(conexion, "mochila")

    iniciado = iniciar_evento(conexion, thread_id, resolucion, "lote 7", None)
    assert iniciado.evento_id is not None
    assert iniciado.ya_en_curso is False
    assert iniciado.vehiculo.nombre == "mochila"

    finalizado = finalizar_evento(conexion, thread_id)
    assert finalizado.evento_id == iniciado.evento_id
    assert finalizado.fecha_fin is not None


def test_iniciar_con_evento_ya_en_curso_no_duplica(conexion):
    thread_id = _thread()
    resolucion = resolver_vehiculo(conexion, "dron")

    primero = iniciar_evento(conexion, thread_id, resolucion, "lote 1", None)
    segundo = iniciar_evento(conexion, thread_id, resolucion, "lote 2", None)

    assert segundo.ya_en_curso is True
    assert segundo.evento_id == primero.evento_id
    assert segundo.lote == "lote 1"  # no se pisó con "lote 2"


def test_finalizar_sin_evento_en_curso(conexion):
    thread_id = _thread()
    resultado = finalizar_evento(conexion, thread_id)
    assert resultado.motivo_no_resuelto == MotivoNoResuelto.SIN_EVENTO_EN_CURSO


def test_iniciar_con_vehiculo_no_resuelto_propaga_opciones(conexion):
    thread_id = _thread()
    resolucion = resolver_vehiculo(conexion, "algo que no matchea zzz")
    resultado = iniciar_evento(conexion, thread_id, resolucion, "lote 1", None)
    assert resultado.opciones_ambiguas is not None


def test_agenda_vacia_sin_recetas_para_la_fecha(conexion):
    thread_id = _thread()
    tareas = consultar_agenda_logica(conexion, thread_id, date.today())
    assert tareas == []


def test_agenda_con_receta_pendiente_y_receta_en_curso(conexion):
    thread_id = _thread()
    hoy = date.today()
    with conexion.cursor() as cur:
        cur.execute(
            """
            INSERT INTO operacion.receta (thread_id, cultivo, lote, fecha_prevista, estado)
            VALUES (%s, 'soja', 'lote A', %s, 'confirmada') RETURNING id
            """,
            (thread_id, hoy),
        )
        (receta_pendiente_id,) = cur.fetchone()
        cur.execute(
            """
            INSERT INTO operacion.receta (thread_id, cultivo, lote, fecha_prevista, estado)
            VALUES (%s, 'maiz', 'lote B', %s, 'confirmada') RETURNING id
            """,
            (thread_id, hoy),
        )
        (receta_en_curso_id,) = cur.fetchone()
    conexion.commit()

    resolucion = resolver_vehiculo(conexion, "mochila")
    iniciar_evento(conexion, thread_id, resolucion, "lote B", receta_en_curso_id)

    tareas = consultar_agenda_logica(conexion, thread_id, hoy)
    por_receta = {t["receta_id"]: t for t in tareas}
    assert por_receta[receta_pendiente_id]["estado_tarea"] == "pendiente"
    assert por_receta[receta_en_curso_id]["estado_tarea"] == "en_curso"


def test_agenda_no_incluye_recetas_de_otra_fecha(conexion):
    thread_id = _thread()
    ayer = date.today() - timedelta(days=1)
    with conexion.cursor() as cur:
        cur.execute(
            """
            INSERT INTO operacion.receta (thread_id, cultivo, lote, fecha_prevista, estado)
            VALUES (%s, 'soja', 'lote viejo', %s, 'confirmada')
            """,
            (thread_id, ayer),
        )
    conexion.commit()

    tareas = consultar_agenda_logica(conexion, thread_id, date.today())
    assert tareas == []
