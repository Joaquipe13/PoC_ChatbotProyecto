"""Agente orquestador: `create_agent` (LangGraph) con las tools del núcleo
más las de la Fase 9, `response_format=RespuestaAgente` y checkpointer en
Postgres (ver skill, "Arquitectura" y "Política del orquestador").

Nota de API (verificar antes de la demo si cambia `langchain`/`langgraph`):
`create_agent` viene de `langchain.agents` (`langchain==1.4.0` al escribir
esto). `response_format` se pasa explícitamente como
`ToolStrategy(RespuestaAgente)` en vez de la clase pydantic pelada: con la
clase sola, un modelo que no declara soporte nativo de structured output
(como el fake usado en los tests) nunca dispara la extracción y
`structured_response` queda `None` -- confirmado interactivamente antes de
escribir este módulo, ver DECISIONES.md.
"""

import logging
from contextlib import contextmanager

from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware, ToolCallLimitMiddleware
from langchain.agents.structured_output import ToolStrategy
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from fitosanitarios.config import Settings
from fitosanitarios.dominio.modelos import RespuestaAgente
from fitosanitarios.dominio.motivos import MotivoNoResuelto
from fitosanitarios.orquestador.prompt_sistema import PROMPT_SISTEMA
from fitosanitarios.tools.agendar_aplicacion import agendar_aplicacion
from fitosanitarios.tools.completar_receta import completar_receta
from fitosanitarios.tools.consultar_agenda import consultar_agenda
from fitosanitarios.tools.consultar_articulo import consultar_articulo
from fitosanitarios.tools.consultar_marbete import consultar_marbete
from fitosanitarios.tools.consultar_productos import consultar_productos
from fitosanitarios.tools.evaluar_riesgo import evaluar_riesgo
from fitosanitarios.tools.evaluar_viabilidad_legal import evaluar_viabilidad_legal
from fitosanitarios.tools.leer_receta import crear_tool_leer_receta_ligada, leer_receta
from fitosanitarios.tools.listar_limitaciones import listar_limitaciones
from fitosanitarios.tools.registrar_evento import registrar_evento
from fitosanitarios.tools.resolver_vehiculo import resolver_vehiculo
from fitosanitarios.tools.responder_consulta_normativa import responder_consulta_normativa
from fitosanitarios.tools.validar_producto_registro import validar_producto_registro

logger = logging.getLogger(__name__)

# Tope de llamadas a tools en un mismo turno. Un turno normal usa una o dos (un mensaje con
# varias preguntas, una por pregunta); en la evaluación conversacional Gemini llegó a llamar
# cinco veces a `listar_limitaciones` con los mismos argumentos, y cada vuelta reenvía los
# ~4k tokens de tools y prompt. Pasado el tope, las llamadas reciben un aviso y el modelo
# responde con lo que ya tiene.
LIMITE_TOOLS_POR_TURNO = 4

TOOLS = [
    leer_receta,
    completar_receta,
    validar_producto_registro,
    consultar_productos,
    consultar_marbete,
    evaluar_riesgo,
    evaluar_viabilidad_legal,
    responder_consulta_normativa,
    consultar_articulo,
    listar_limitaciones,
    # Fase 9 (extensiones):
    resolver_vehiculo,
    registrar_evento,
    consultar_agenda,
    agendar_aplicacion,
]


def crear_modelo_chat_gemini(
    settings: Settings, temperature: float | None = None, indice_key: int = 0
) -> BaseChatModel:
    """Modelo de chat real para el agente (Gemini, multimodal, ver skill).
    No reutiliza `llm/client.py::ClienteGemini` -- ese cliente es para
    llamadas de texto/imagen sueltas (extracción, RAG), no implementa el
    protocolo de tool-calling que `create_agent` necesita. Usa la primera
    key configurada; la rotación ante 429 para el agente completo queda
    pendiente (ver DECISIONES.md).

    `temperature` e `indice_key` son para las evaluaciones (`evals/chat.py`): fijar la
    temperatura más baja y repartir los turnos entre las keys. Con los valores por
    defecto el comportamiento no cambia."""
    from langchain_google_genai import ChatGoogleGenerativeAI

    if not settings.gemini_api_keys:
        raise ValueError("Se necesita al menos una GEMINI_API_KEY_* para el agente real")
    keys = settings.gemini_api_keys
    opciones = {} if temperature is None else {"temperature": temperature}
    return ChatGoogleGenerativeAI(
        model=settings.gemini_model, google_api_key=keys[indice_key % len(keys)], **opciones
    )


def construir_tools(imagen_base64: str | None = None) -> list:
    """`TOOLS` con `leer_receta` reemplazada por la variante ligada a la
    imagen del turno cuando el canal (WhatsApp, Fase 8) ya la descargó -- ver
    `tools/leer_receta/tool.py::crear_tool_leer_receta_ligada`. Sin imagen (turnos
    de solo texto, y todos los tests existentes) se usa la `leer_receta`
    original."""
    if imagen_base64 is None:
        return TOOLS
    return [
        crear_tool_leer_receta_ligada(imagen_base64) if t is leer_receta else t for t in TOOLS
    ]


def es_primera_llamada_del_turno(mensajes: list) -> bool:
    """Todavía no hubo respuesta del modelo después del último mensaje del usuario."""
    for m in reversed(mensajes):
        if isinstance(m, HumanMessage):
            return True
        if isinstance(m, AIMessage):
            return False
    return True


class LeerLaFotoPrimero(AgentMiddleware):
    """Si el mensaje trae una foto, lo primero del turno es leerla (`leer_receta`).

    Antes lo decidía el modelo y a veces no la leía: contestaba "mandame la foto" aunque
    la foto hubiera llegado, y a la segunda vez cortaba por límite de repreguntas (plan de
    pruebas, 26/09/2026; ver también DIFICULTADES.md, "repregunta por la foto"). En la
    primera llamada del turno quedan solo la tool de lectura y `tool_choice` con su
    nombre; se saca la salida estructurada porque, con ella, `create_agent` fuerza
    `tool_choice="any"` e ignora este. `leer_receta` corta el turno (`return_direct`)."""

    def wrap_model_call(self, request, handler):
        if es_primera_llamada_del_turno(request.messages):
            lectura = [t for t in request.tools if getattr(t, "name", None) == "leer_receta"]
            if lectura:
                request = request.override(
                    tools=lectura, tool_choice="leer_receta", response_format=None
                )
        return handler(request)


def crear_agente(model: BaseChatModel, checkpointer=None, imagen_base64: str | None = None):
    """`checkpointer=None` es válido (sin memoria entre invocaciones, útil
    para tests); en producción pasar un `PostgresSaver` (ver
    `checkpointer_postgres` acá abajo). `imagen_base64`: ver `construir_tools`
    -- arma un agente nuevo (barato, no reabre el checkpointer) con la tool
    de lectura de receta ligada a esta imagen puntual."""
    return create_agent(
        model=model,
        tools=construir_tools(imagen_base64),
        system_prompt=PROMPT_SISTEMA,
        response_format=ToolStrategy(RespuestaAgente),
        middleware=[ToolCallLimitMiddleware(run_limit=LIMITE_TOOLS_POR_TURNO)]
        + ([LeerLaFotoPrimero()] if imagen_base64 is not None else []),
        checkpointer=checkpointer,
    )


# Los tipos propios que quedan en el checkpoint (la respuesta estructurada del agente y
# su motivo). LangGraph los deserializa hoy con un warning y anuncia que en una versión
# futura los va a bloquear si no están permitidos de forma explícita: sin esto, el
# historial de la conversación dejaría de recuperarse. Relevado sobre ~1.700 checkpoints
# reales (27/09/2026): no hay otros.
TIPOS_DEL_CHECKPOINT = (RespuestaAgente, MotivoNoResuelto)


def serializador_checkpoint() -> JsonPlusSerializer:
    return JsonPlusSerializer(
        allowed_msgpack_modules=[(t.__module__, t.__name__) for t in TIPOS_DEL_CHECKPOINT]
    )


@contextmanager
def checkpointer_postgres(database_url: str):
    """Context manager: `PostgresSaver.setup()` crea sus propias tablas la
    primera vez (ver skill: "Más las tablas propias del checkpointer de
    LangGraph"), no están en las migraciones de `datos/migraciones/`."""
    with PostgresSaver.from_conn_string(database_url) as saver:
        saver.serde = serializador_checkpoint()
        saver.setup()
        yield saver
