"""Servicio de eventos de aplicación real (Fase 9): iniciar/finalizar una
aplicación en el campo (RF7 `registrar_evento`) y armar la agenda del día
de un operario (RF9 `consultar_agenda`, numeración propia del usuario).

Distinto del dictamen (`servicios/dictamen.py`): el dictamen evalúa si una
aplicación es viable ANTES de hacerla; esto registra que efectivamente se
hizo. No hay lógica de negocio compartida entre los dos."""

from dataclasses import dataclass
from datetime import date, datetime

from fitosanitarios.dominio.motivos import MotivoNoResuelto
from fitosanitarios.servicios.resolucion_vehiculo import ResolucionVehiculo, VehiculoResuelto


@dataclass
class ResultadoEvento:
    evento_id: int | None = None
    vehiculo: VehiculoResuelto | None = None
    lote: str | None = None
    fecha_inicio: datetime | None = None
    fecha_fin: datetime | None = None
    opciones_ambiguas: list[str] | None = None  # vehículo ambiguo, ver resolucion_vehiculo
    motivo_no_resuelto: MotivoNoResuelto | None = None
    ya_en_curso: bool = False  # "iniciar" pedido con un evento ya abierto: no se duplica


def _evento_en_curso(conn, thread_id: str) -> dict | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, lote, fecha_inicio
            FROM operacion.evento_aplicacion
            WHERE thread_id = %s AND estado = 'en_curso'
            ORDER BY fecha_inicio DESC LIMIT 1
            """,
            (thread_id,),
        )
        fila = cur.fetchone()
    if fila is None:
        return None
    return {"id": fila[0], "lote": fila[1], "fecha_inicio": fila[2]}


def iniciar_evento(
    conn,
    thread_id: str,
    resolucion_vehiculo: ResolucionVehiculo,
    lote: str | None,
    receta_id: int | None,
) -> ResultadoEvento:
    if resolucion_vehiculo.motivo_no_resuelto is not None:
        return ResultadoEvento(motivo_no_resuelto=resolucion_vehiculo.motivo_no_resuelto)
    if resolucion_vehiculo.opciones_ambiguas is not None:
        return ResultadoEvento(opciones_ambiguas=resolucion_vehiculo.opciones_ambiguas)

    existente = _evento_en_curso(conn, thread_id)
    if existente is not None:
        return ResultadoEvento(
            evento_id=existente["id"],
            lote=existente["lote"],
            fecha_inicio=existente["fecha_inicio"],
            ya_en_curso=True,
        )

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO operacion.evento_aplicacion (thread_id, receta_id, vehiculo_id, lote)
            VALUES (%s, %s, %s, %s)
            RETURNING id, fecha_inicio
            """,
            (thread_id, receta_id, resolucion_vehiculo.vehiculo.id, lote),
        )
        evento_id, fecha_inicio = cur.fetchone()
    conn.commit()
    return ResultadoEvento(
        evento_id=evento_id, vehiculo=resolucion_vehiculo.vehiculo, lote=lote,
        fecha_inicio=fecha_inicio,
    )


def finalizar_evento(conn, thread_id: str) -> ResultadoEvento:
    existente = _evento_en_curso(conn, thread_id)
    if existente is None:
        return ResultadoEvento(motivo_no_resuelto=MotivoNoResuelto.SIN_EVENTO_EN_CURSO)

    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE operacion.evento_aplicacion
            SET estado = 'finalizado', fecha_fin = now()
            WHERE id = %s
            RETURNING fecha_inicio, fecha_fin
            """,
            (existente["id"],),
        )
        fecha_inicio, fecha_fin = cur.fetchone()
    conn.commit()
    return ResultadoEvento(
        evento_id=existente["id"], lote=existente["lote"],
        fecha_inicio=fecha_inicio, fecha_fin=fecha_fin,
    )


def consultar_agenda_logica(conn, thread_id: str, fecha: date) -> list[dict]:
    """Combina `operacion.receta` (por `fecha_prevista`, ya existe desde la
    Fase 1) con el último `operacion.evento_aplicacion` de cada una para el
    estado de la tarea: sin evento -> pendiente; con evento en curso ->
    en_curso; con evento finalizado -> finalizada. No hay un concepto de
    "asignación" separado en este dominio -- se reusa `fecha_prevista` en
    vez de inventar uno nuevo (ver DECISIONES.md)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT r.id, r.numero, r.cultivo, r.lote, e.estado, e.fecha_inicio, e.fecha_fin
            FROM operacion.receta r
            LEFT JOIN LATERAL (
                SELECT estado, fecha_inicio, fecha_fin
                FROM operacion.evento_aplicacion
                WHERE receta_id = r.id
                ORDER BY fecha_inicio DESC LIMIT 1
            ) e ON true
            WHERE r.thread_id = %s AND r.fecha_prevista = %s AND r.estado != 'cancelada'
            ORDER BY r.creado_en
            """,
            (thread_id, fecha),
        )
        filas = cur.fetchall()

    tareas = []
    for id_, numero, cultivo, lote, estado_evento, fecha_inicio, fecha_fin in filas:
        if estado_evento == "finalizado":
            estado_tarea = "finalizada"
        elif estado_evento == "en_curso":
            estado_tarea = "en_curso"
        else:
            estado_tarea = "pendiente"
        tareas.append(
            {
                "receta_id": id_,
                "numero": numero,
                "cultivo": cultivo,
                "lote": lote,
                "estado_tarea": estado_tarea,
                "fecha_inicio": fecha_inicio.isoformat() if fecha_inicio else None,
                "fecha_fin": fecha_fin.isoformat() if fecha_fin else None,
            }
        )
    return tareas
