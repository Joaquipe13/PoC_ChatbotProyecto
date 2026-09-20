"""Wiring de producción del canal WhatsApp: agente real (Gemini + Postgres)
más el cliente Graph, conectados al webhook (ver plandefases.md Fase 8,
tarea 9). Entrypoint para correr el servidor:

    uv run uvicorn fitosanitarios.canales.whatsapp.app_produccion:app

Ver docs/setup-whatsapp.md para la configuración de la app de Meta y el
túnel HTTPS.
"""

import logging
from contextlib import ExitStack

import psycopg

from fitosanitarios.canales.whatsapp import cliente_graph
from fitosanitarios.canales.whatsapp.normalizacion import numero_canonico, numero_para_envio
from fitosanitarios.canales.whatsapp.webhook import (
    MENSAJE_TIPO_NO_SOPORTADO,
    ProcesadorMensaje,
    crear_app,
    texto_e_imagen,
    tipo_soportado,
)
from fitosanitarios.config import Settings, get_settings
from fitosanitarios.orquestador.agente import (
    checkpointer_postgres,
    crear_agente,
    crear_modelo_chat_gemini,
)
from fitosanitarios.orquestador.estado import ContadorRepreguntas
from fitosanitarios.orquestador.turno import ejecutar_turno

logger = logging.getLogger(__name__)


def _responder(settings: Settings, thread_id: str, mensajes: list[str]) -> None:
    numero_envio = numero_para_envio(thread_id, settings.whatsapp_ar_quitar_9)
    try:
        cliente_graph.enviar_mensajes(settings, numero_envio, mensajes)
    except cliente_graph.ErrorEnvioWhatsApp:
        logger.exception(
            "No se pudo enviar la respuesta a %s (thread_id=%s)", numero_envio, thread_id
        )


def construir_procesador(settings: Settings, model, checkpointer, contador) -> ProcesadorMensaje:
    """El agente de solo-texto se arma una única vez y se reusa entre
    turnos; el agente con imagen se arma por turno porque la tool de lectura
    de receta queda ligada a esa imagen puntual (ver
    `orquestador/agente.py::construir_tools`)."""
    agente_default = crear_agente(model, checkpointer=checkpointer)

    def procesar_mensaje(mensaje: dict, numero_from: str) -> None:
        thread_id = numero_canonico(numero_from)
        if not tipo_soportado(mensaje):
            _responder(settings, thread_id, [MENSAJE_TIPO_NO_SOPORTADO])
            return

        try:
            texto, imagen_base64 = texto_e_imagen(
                mensaje, lambda media_id: cliente_graph.descargar_media(settings, media_id)
            )
        except cliente_graph.ErrorMediaWhatsApp:
            logger.exception("No se pudo descargar la imagen del mensaje de %s", thread_id)
            _responder(settings, thread_id, ["No pude descargar la imagen, ¿la volvés a mandar?"])
            return

        agente = (
            agente_default
            if imagen_base64 is None
            else crear_agente(model, checkpointer=checkpointer, imagen_base64=imagen_base64)
        )

        with psycopg.connect(settings.database_url) as conn:
            _, mensajes_salida = ejecutar_turno(agente, thread_id, texto, contador, conn_log=conn)

        _responder(settings, thread_id, mensajes_salida)

    return procesar_mensaje


def crear_app_produccion(pila: ExitStack):
    settings = get_settings()
    if settings.use_fixtures:
        # Ver `canales/web/app_produccion.py::crear_app_produccion` y
        # DIFICULTADES.md: con USE_FIXTURES=true, leer_receta y
        # responder_consulta_normativa usan un LLM fake para sus llamadas
        # internas aunque el agente use Gemini real.
        logger.warning(
            "USE_FIXTURES=true: leer_receta y responder_consulta_normativa van a "
            "usar un LLM fake para sus llamadas internas aunque el agente use "
            "Gemini real. Arrancar con USE_FIXTURES=false para un canal real."
        )
    model = crear_modelo_chat_gemini(settings)
    checkpointer = pila.enter_context(checkpointer_postgres(settings.database_url))
    contador = ContadorRepreguntas()
    procesador = construir_procesador(settings, model, checkpointer, contador)
    return crear_app(settings, procesador)


_pila_recursos = ExitStack()
app = crear_app_produccion(_pila_recursos)
