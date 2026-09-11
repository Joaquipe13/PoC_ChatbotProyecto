"""Chat model fake para testear el agente sin llamar a ningún LLM real.

Los fakes genéricos de `langchain_core` (p. ej. `GenericFakeChatModel`) no
simulan tool-calling de forma controlable; este devuelve, en orden, los
mensajes que se le precargan -- típicamente un `AIMessage` con `tool_calls`
para simular que el LLM decidió llamar una tool, seguido de otro `AIMessage`
con `tool_calls` hacia el nombre de la clase de `response_format` para
simular la respuesta estructurada final (ver DECISIONES.md, Fase 7, sobre
por qué hace falta ese último tool_call explícito).
"""

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field


class ChatModelFake(BaseChatModel):
    respuestas: list[AIMessage] = Field(default_factory=list)
    llamadas: list[list[BaseMessage]] = Field(default_factory=list)

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        self.llamadas.append(list(messages))
        if not self.respuestas:
            raise AssertionError(
                "ChatModelFake se quedó sin respuestas precargadas -- el agente pidió "
                "más turnos de los que el test anticipó"
            )
        respuesta = self.respuestas.pop(0)
        return ChatResult(generations=[ChatGeneration(message=respuesta)])

    def bind_tools(self, tools, **kwargs):
        return self

    @property
    def _llm_type(self) -> str:
        return "fake-chat-model"


def mensaje_llama_tool(nombre_tool: str, args: dict, id_llamada: str = "call_1") -> AIMessage:
    return AIMessage(
        content="", tool_calls=[{"name": nombre_tool, "args": args, "id": id_llamada}]
    )


def mensaje_respuesta_estructurada(datos: dict, id_llamada: str = "call_resp") -> AIMessage:
    """`datos` tiene que ser un dict serializable con las claves de
    `RespuestaAgente` (tipo, intro, faltantes)."""
    return AIMessage(
        content="",
        tool_calls=[{"name": "RespuestaAgente", "args": datos, "id": id_llamada}],
    )
