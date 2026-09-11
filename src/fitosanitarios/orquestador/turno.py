"""Ejecuta un turno de conversación: invoca al agente, extrae la
`RespuestaAgente` estructurada y los artifacts de las tools que corrieron
en el turno, aplica el límite de repreguntas, y devuelve el texto final ya
formateado (ver skill, "Política del orquestador").
"""

import logging

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from fitosanitarios.dominio.modelos import RespuestaAgente, ResultadoTool
from fitosanitarios.dominio.motivos import MotivoNoResuelto
from fitosanitarios.orquestador.estado import (
    LIMITE_INTENTOS_POR_CAMPO,
    ContadorRepreguntas,
    registrar_turno,
)
from fitosanitarios.orquestador.formateador import formatear_respuesta

logger = logging.getLogger(__name__)


def _tool_calls_del_turno(mensajes: list) -> list[dict]:
    llamadas = []
    for m in reversed(mensajes):
        if isinstance(m, HumanMessage):
            break
        if isinstance(m, AIMessage) and m.tool_calls:
            llamadas.extend(
                tc for tc in m.tool_calls if tc.get("name") != "RespuestaAgente"
            )
    return list(reversed(llamadas))


def _artifacts_del_turno(mensajes: list) -> list[ResultadoTool]:
    """Los `ToolMessage` de una tool declarada con
    `response_format="content_and_artifact"` traen el `ResultadoTool` en
    `.artifact` (ver skill, "Contratos"; confirmado interactivamente antes
    de escribir esto, ver DECISIONES.md). Solo los del turno actual: los
    mensajes nuevos desde el último `HumanMessage`."""
    resultados: list[ResultadoTool] = []
    for m in reversed(mensajes):
        if isinstance(m, HumanMessage):
            break
        if isinstance(m, ToolMessage) and isinstance(m.artifact, ResultadoTool):
            resultados.append(m.artifact)
    return list(reversed(resultados))


def ejecutar_turno(
    agente,
    thread_id: str,
    texto_usuario: str,
    contador: ContadorRepreguntas,
    conn_log=None,
) -> tuple[RespuestaAgente, list[str]]:
    """Devuelve (la `RespuestaAgente` que decidió el agente -- o la que la
    reemplazó por límite de repreguntas --, los mensajes de WhatsApp ya
    formateados). `conn_log`: conexión opcional para el log estructurado
    por turno (`operacion.turno`, ver skill "Log por turno"); si es `None`
    no se loguea (los tests no necesitan pasarla)."""
    config = {"configurable": {"thread_id": thread_id}}
    try:
        resultado_grafo = agente.invoke(
            {"messages": [{"role": "user", "content": texto_usuario}]}, config=config
        )
    except Exception:
        # Hallazgo real (Fase 7, evals): un ValueError de validación de
        # argumentos de una tool (p. ej. consultar_productos sin ningún
        # filtro) se propaga sin capturar y rompía el turno entero en vez
        # de degradar a una respuesta de error (ver DECISIONES.md/
        # DIFICULTADES.md). "Las excepciones quedan para bugs" (skill) --
        # siguen logueándose enteras, pero el usuario nunca se queda sin
        # respuesta por una excepción técnica.
        logger.exception("Excepción no controlada ejecutando el turno (thread %s)", thread_id)
        respuesta = RespuestaAgente(tipo="error")
        if conn_log is not None:
            registrar_turno(conn_log, thread_id, texto_usuario, [], respuesta.tipo)
        return respuesta, formatear_respuesta(respuesta, [])

    respuesta: RespuestaAgente | None = resultado_grafo.get("structured_response")
    artifacts = _artifacts_del_turno(resultado_grafo["messages"])
    tool_calls = _tool_calls_del_turno(resultado_grafo["messages"])

    if respuesta is None:
        logger.warning("El agente no devolvió structured_response (thread %s)", thread_id)
        respuesta = RespuestaAgente(tipo="error")
        if conn_log is not None:
            registrar_turno(conn_log, thread_id, texto_usuario, tool_calls, respuesta.tipo)
        return respuesta, formatear_respuesta(respuesta, [])

    if respuesta.tipo == "repregunta" and respuesta.faltantes:
        limite_alcanzado = False
        campo_agotado = ""
        for campo_faltante in respuesta.faltantes:
            intentos = contador.registrar_intento(thread_id, campo_faltante.campo)
            if intentos >= LIMITE_INTENTOS_POR_CAMPO:
                limite_alcanzado = True
                campo_agotado = campo_faltante.campo
                break
        if limite_alcanzado:
            respuesta = RespuestaAgente(tipo="no_resuelto")
            artifacts = [
                ResultadoTool(
                    estado="no_resuelto",
                    motivo=MotivoNoResuelto.LIMITE_REPREGUNTAS,
                    advertencias=[
                        f"no se pudo obtener el dato '{campo_agotado}' tras "
                        f"{LIMITE_INTENTOS_POR_CAMPO} intentos"
                    ],
                )
            ]
    else:
        # El turno no volvió a repreguntar los mismos campos (el usuario
        # contestó, o el agente resolvió algo distinto): se limpia el
        # contador para no arrastrar intentos viejos de otro tema.
        contador.resetear_thread(thread_id)

    if conn_log is not None:
        registrar_turno(conn_log, thread_id, texto_usuario, tool_calls, respuesta.tipo)

    return respuesta, formatear_respuesta(respuesta, artifacts)
