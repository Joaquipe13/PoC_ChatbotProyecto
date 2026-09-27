"""Con una foto en el turno, la primera llamada al modelo solo puede leerla
(`LeerLaFotoPrimero`). Plan de pruebas del 26/09/2026: Gemini a veces no llamaba a
`leer_receta` y contestaba "mandame la foto" aunque la foto hubiera llegado."""

import base64

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from pydantic import Field

from fitosanitarios.orquestador.agente import crear_agente, es_primera_llamada_del_turno
from tests.orquestador.fake_chat_model import (
    ChatModelFake,
    mensaje_llama_tool,
    mensaje_respuesta_estructurada,
)

IMAGEN = base64.b64encode(b"no es una foto de verdad").decode()


class ChatModelQueRegistraLasTools(ChatModelFake):
    """Anota con qué tools y qué `tool_choice` lo prepara el agente en cada llamada."""

    enlaces: list[tuple[list[str], object]] = Field(default_factory=list)

    def bind_tools(self, tools, **kwargs):
        nombres = [getattr(t, "name", None) or getattr(t, "__name__", str(t)) for t in tools]
        self.enlaces.append((nombres, kwargs.get("tool_choice")))
        return self


def _correr(modelo, imagen):
    agente = crear_agente(modelo, imagen_base64=imagen)
    return agente.invoke({"messages": [{"role": "user", "content": "te paso la receta"}]})


def test_con_foto_la_primera_llamada_solo_puede_leerla():
    modelo = ChatModelQueRegistraLasTools(respuestas=[mensaje_llama_tool("leer_receta", {})])
    resultado = _correr(modelo, IMAGEN)
    nombres, eleccion = modelo.enlaces[0]
    assert nombres == ["leer_receta"]
    assert eleccion == "leer_receta"
    llamadas = [tc["name"] for m in resultado["messages"] if isinstance(m, AIMessage)
                for tc in m.tool_calls]
    assert llamadas == ["leer_receta"]  # y el turno termina ahí (`return_direct`)


def test_sin_foto_el_modelo_elige_entre_todas_las_tools():
    modelo = ChatModelQueRegistraLasTools(
        respuestas=[mensaje_respuesta_estructurada({"tipo": "ayuda"})]
    )
    _correr(modelo, None)
    nombres, eleccion = modelo.enlaces[0]
    assert "leer_receta" in nombres and len(nombres) > 5
    assert eleccion == "any"  # la salida estructurada de siempre


def test_primera_llamada_del_turno():
    assert es_primera_llamada_del_turno([HumanMessage("hola")])
    assert es_primera_llamada_del_turno([AIMessage("antes"), HumanMessage("hola")])
    assert not es_primera_llamada_del_turno([
        HumanMessage("hola"), AIMessage("", tool_calls=[
            {"name": "leer_receta", "args": {}, "id": "c1"}
        ]), ToolMessage("ok", tool_call_id="c1"),
    ])
