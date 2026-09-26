"""Agendar una aplicación (fecha + horario) en la agenda del operario.

La agenda reutiliza `operacion.receta` (`fecha_prevista` + `hora_prevista`),
igual que `consultar_agenda_logica`: no hay una entidad de "asignación"
separada (ver DECISIONES.md). Cada agendado inserta una receta ya evaluada,
así no se mezcla con la receta en curso del operario.
"""

import json
from datetime import date, time

from fitosanitarios.servicios.eventos import consultar_agenda_logica


def agendar_aplicacion(
    conn,
    thread_id: str,
    fecha: date,
    hora: time,
    datos_receta: dict,
) -> tuple[int, list[dict]]:
    """Devuelve (id de la receta agendada, tareas que el operario ya tenía a
    esa misma hora ese día -- para avisar de un posible choque, sin bloquear)."""
    choques = [
        t for t in consultar_agenda_logica(conn, thread_id, fecha)
        if t["hora"] == hora.strftime("%H:%M")
    ]
    descriptivos = {k: v for k, v in datos_receta.items() if v is not None}
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO operacion.receta
                (thread_id, numero, cultivo, lote, superficie_ha, tipo_aplicacion,
                 fecha_prevista, hora_prevista, datos_extraidos, estado)
            VALUES (%(thread_id)s, %(numero)s, %(cultivo)s, %(lote)s, %(superficie_ha)s,
                    %(tipo_aplicacion)s, %(fecha)s, %(hora)s, %(datos)s::jsonb, 'evaluada')
            RETURNING id
            """,
            {
                "thread_id": thread_id, "numero": datos_receta.get("numero"),
                "cultivo": datos_receta.get("cultivo"), "lote": datos_receta.get("lote"),
                "superficie_ha": datos_receta.get("superficie_ha"),
                "tipo_aplicacion": datos_receta.get("tipo_aplicacion"),
                "fecha": fecha, "hora": hora, "datos": json.dumps(descriptivos),
            },
        )
        receta_id = cur.fetchone()[0]
    conn.commit()
    return receta_id, choques


def guardar_pronostico(conn, receta_id: int, pronostico: dict) -> None:
    """El pronóstico que se mostró al agendar, para que quede registrado qué se sabía."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE operacion.receta SET pronostico = %s::jsonb WHERE id = %s",
            (json.dumps(pronostico), receta_id),
        )
    conn.commit()
