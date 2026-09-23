"""Wiring de producción del canal web: mismo agente real (Gemini + Postgres)
que `canales/whatsapp/app_produccion.py`, expuesto por una página de chat en
vez del Graph API de Meta (ver plandefases.md Fase 11 y DECISIONES.md: el
canal WhatsApp queda intacto como implementación futura, este es el canal
usado para desarrollo, pruebas y demo mientras tanto).

Entrypoint para correr el servidor:

    uv run uvicorn fitosanitarios.canales.web.app_produccion:app --port 8001

Cada sesión de navegador tiene su propio `session_id` (generado client-side,
ver `pagina.py`); el `thread_id` real que ve el checkpointer es
`web:<session_id>`, para no chocar con los números de teléfono del canal
WhatsApp en la misma base.
"""

import logging
from contextlib import ExitStack

import psycopg

from fitosanitarios.canales.chequeo_credenciales import chequear_al_arrancar
from fitosanitarios.canales.web.canal import crear_app
from fitosanitarios.config import Settings, get_settings
from fitosanitarios.orquestador.agente import (
    checkpointer_postgres,
    crear_agente,
    crear_modelo_chat_gemini,
)
from fitosanitarios.orquestador.estado import ContadorRepreguntas
from fitosanitarios.orquestador.turno import ejecutar_turno

logger = logging.getLogger(__name__)


def construir_procesador(settings: Settings, model, checkpointer, contador):
    """El agente de solo-texto se arma una única vez y se reusa entre
    turnos; con imagen se arma por turno, igual que en el canal WhatsApp
    (ver `orquestador/agente.py::construir_tools`)."""
    agente_default = crear_agente(model, checkpointer=checkpointer)

    def procesar_mensaje(session_id: str, texto: str, imagen_base64: str | None) -> list[str]:
        thread_id = f"web:{session_id}"
        agente = (
            agente_default
            if imagen_base64 is None
            else crear_agente(model, checkpointer=checkpointer, imagen_base64=imagen_base64)
        )
        with psycopg.connect(settings.database_url) as conn:
            _, mensajes_salida = ejecutar_turno(agente, thread_id, texto, contador, conn_log=conn)
        return mensajes_salida

    return procesar_mensaje


def crear_app_produccion(pila: ExitStack):
    settings = get_settings()
    if settings.use_fixtures:
        # `leer_receta` y `responder_consulta_normativa` resuelven su LLM
        # interno con `crear_cliente_llm(get_settings())`, que devuelve el
        # fake determinista si USE_FIXTURES=true -- a diferencia del modelo
        # del agente (`crear_modelo_chat_gemini`), que siempre es real. Con
        # el flag en true, esas dos tools van a fallar/degradar en
        # silencio (ver DIFICULTADES.md: "no pude leer la imagen" con
        # cualquier foto). Para un canal de verdad: `USE_FIXTURES=false`.
        logger.warning(
            "USE_FIXTURES=true: leer_receta y responder_consulta_normativa van a "
            "usar un LLM fake para sus llamadas internas aunque el agente use "
            "Gemini real. Arrancar con USE_FIXTURES=false para un canal real."
        )
    chequear_al_arrancar(settings, whatsapp=False)
    model = crear_modelo_chat_gemini(settings)
    checkpointer = pila.enter_context(checkpointer_postgres(settings.database_url))
    contador = ContadorRepreguntas()
    procesador = construir_procesador(settings, model, checkpointer, contador)
    return crear_app(settings, procesador)


_pila_recursos = ExitStack()
app = crear_app_produccion(_pila_recursos)
