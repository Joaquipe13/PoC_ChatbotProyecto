"""Deduplicación de mensajes de WhatsApp por `message.id` (Meta reintenta
entregas del mismo mensaje, ver skill). Persistido en Postgres
(`operacion.mensaje_whatsapp`), no en memoria de proceso: un reintento puede
llegar después de un reinicio del webhook (a diferencia del contador de
repreguntas de `orquestador/estado.py`, que sí es aceptable en memoria
porque solo afecta al flujo de la conversación en curso, no la idempotencia
de un efecto ya disparado)."""

import psycopg


def ya_procesado(conn: psycopg.Connection, message_id: str) -> bool:
    """`True` si este `message_id` ya se procesó antes. El `INSERT ... ON
    CONFLICT DO NOTHING` es atómico: no hace falta un `SELECT` previo, que
    dejaría una ventana de carrera entre dos entregas casi simultáneas del
    mismo mensaje."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO operacion.mensaje_whatsapp (message_id) VALUES (%s) "
            "ON CONFLICT DO NOTHING",
            (message_id,),
        )
        ya_existia = cur.rowcount == 0
    conn.commit()
    return ya_existia
