"""Estado de la conversación: receta en curso (persistida en
`operacion.receta`, ver docs/modelo-datos.md) y contador de repreguntas
fallidas por campo (ver skill, "Reglas de repregunta": "Tras 2 intentos
fallidos por el mismo dato, no_resuelto con LIMITE_REPREGUNTAS").

El contador de repreguntas es en memoria de proceso, no persistido en
Postgres -- ver DECISIONES.md: simplificación aceptada para esta fase. La
memoria de conversación real (los mensajes) sí persiste vía el checkpointer
de LangGraph en Postgres (`orquestador/agente.py`), que es lo que importa
para que el LLM tenga contexto entre turnos; el contador es solo
bookkeeping auxiliar del orquestador.
"""

import json
from collections import defaultdict

import psycopg

LIMITE_INTENTOS_POR_CAMPO = 2


class ContadorRepreguntas:
    """Cuenta cuántas veces se repreguntó el mismo campo en un thread sin
    que el usuario lo haya contestado."""

    def __init__(self) -> None:
        self._conteos: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    def registrar_intento(self, thread_id: str, campo: str) -> int:
        self._conteos[thread_id][campo] += 1
        return self._conteos[thread_id][campo]

    def resetear_campo(self, thread_id: str, campo: str) -> None:
        self._conteos[thread_id].pop(campo, None)

    def resetear_thread(self, thread_id: str) -> None:
        self._conteos.pop(thread_id, None)

    def excede_limite(self, thread_id: str, campo: str) -> bool:
        return self._conteos[thread_id][campo] >= LIMITE_INTENTOS_POR_CAMPO


_COLUMNAS_RECETA = [
    "id", "numero", "cultivo", "lote", "adversidad", "superficie_ha",
    "tipo_aplicacion", "fecha_prevista", "estado", "datos_extraidos", "ubicacion",
]


def obtener_receta_en_curso(conn: psycopg.Connection, thread_id: str) -> dict | None:
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT {", ".join(_COLUMNAS_RECETA)}
            FROM operacion.receta
            WHERE thread_id = %s AND estado IN ('borrador', 'confirmada')
            ORDER BY creado_en DESC LIMIT 1
            """,
            (thread_id,),
        )
        fila = cur.fetchone()
    if fila is None:
        return None
    return dict(zip(_COLUMNAS_RECETA, fila, strict=True))


def guardar_receta_en_curso(
    conn: psycopg.Connection, thread_id: str, campos: dict, estado: str = "borrador"
) -> int:
    """Upsert manual (no hay UNIQUE en thread_id porque puede haber varias
    recetas históricas del mismo número): actualiza la receta en curso si
    existe, si no crea una nueva."""
    existente = obtener_receta_en_curso(conn, thread_id)
    with conn.cursor() as cur:
        if existente is not None:
            cur.execute(
                """
                UPDATE operacion.receta SET
                    numero = COALESCE(%(numero)s, numero),
                    cultivo = COALESCE(%(cultivo)s, cultivo),
                    lote = COALESCE(%(lote)s, lote),
                    adversidad = COALESCE(%(adversidad)s, adversidad),
                    superficie_ha = COALESCE(%(superficie_ha)s, superficie_ha),
                    tipo_aplicacion = COALESCE(%(tipo_aplicacion)s, tipo_aplicacion),
                    fecha_prevista = COALESCE(%(fecha_prevista)s, fecha_prevista),
                    datos_extraidos = datos_extraidos || %(datos_extraidos)s::jsonb,
                    estado = %(estado)s,
                    actualizado_en = now()
                WHERE id = %(id)s
                RETURNING id
                """,
                {
                    "id": existente["id"],
                    "numero": campos.get("numero"), "cultivo": campos.get("cultivo"),
                    "lote": campos.get("lote"), "adversidad": campos.get("adversidad"),
                    "superficie_ha": campos.get("superficie_ha"),
                    "tipo_aplicacion": campos.get("tipo_aplicacion"),
                    "fecha_prevista": campos.get("fecha_prevista"),
                    "datos_extraidos": json.dumps(campos.get("datos_extraidos", {})),
                    "estado": estado,
                },
            )
        else:
            cur.execute(
                """
                INSERT INTO operacion.receta
                    (thread_id, numero, cultivo, lote, adversidad, superficie_ha,
                     tipo_aplicacion, fecha_prevista, datos_extraidos, estado)
                VALUES (%(thread_id)s, %(numero)s, %(cultivo)s, %(lote)s, %(adversidad)s,
                        %(superficie_ha)s, %(tipo_aplicacion)s, %(fecha_prevista)s,
                        %(datos_extraidos)s::jsonb, %(estado)s)
                RETURNING id
                """,
                {
                    "thread_id": thread_id,
                    "numero": campos.get("numero"), "cultivo": campos.get("cultivo"),
                    "lote": campos.get("lote"), "adversidad": campos.get("adversidad"),
                    "superficie_ha": campos.get("superficie_ha"),
                    "tipo_aplicacion": campos.get("tipo_aplicacion"),
                    "fecha_prevista": campos.get("fecha_prevista"),
                    "datos_extraidos": json.dumps(campos.get("datos_extraidos", {})),
                    "estado": estado,
                },
            )
        receta_id = cur.fetchone()[0]
        conn.commit()
    return receta_id


_CAMPOS_A_NO_LOGUEAR = {"imagen_base64"}


def _sanear_args_tool(args: dict) -> dict:
    """Nunca loguear imágenes ni datos pesados de una tool (ver skill,
    "Log por turno": "Nunca loguear tokens de API ni imágenes")."""
    return {k: ("<omitido>" if k in _CAMPOS_A_NO_LOGUEAR else v) for k, v in args.items()}


def registrar_turno(
    conn: psycopg.Connection,
    thread_id: str,
    texto_entrada: str,
    tool_calls: list[dict],
    tipo_salida: str,
) -> None:
    """Log estructurado por turno (ver skill, "Log por turno"): intención
    (aproximada por `tipo_salida`), tool calls con args (saneados) y estado
    de cada resultado. No incluye latencia ni tokens en esta sesión
    (pendiente, ver DECISIONES.md)."""
    tool_calls_saneados = [
        {"nombre": tc.get("name"), "args": _sanear_args_tool(tc.get("args", {}))}
        for tc in tool_calls
    ]
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO operacion.turno (thread_id, entrada, tool_calls, salida)
            VALUES (%s, %s, %s, %s)
            """,
            (
                thread_id,
                json.dumps({"texto": texto_entrada}),
                json.dumps(tool_calls_saneados),
                json.dumps({"tipo": tipo_salida}),
            ),
        )
    conn.commit()


def cancelar_receta_en_curso(conn: psycopg.Connection, thread_id: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE operacion.receta SET estado = 'cancelada', actualizado_en = now() "
            "WHERE thread_id = %s AND estado IN ('borrador', 'confirmada')",
            (thread_id,),
        )
    conn.commit()
