"""La guarda de confirmación con el agente completo (modelo simulado, sin base ni red).

Reproduce el hallazgo H2 de la evaluación conversacional: tras mostrar la receta de una foto,
el usuario contesta solo la localidad y el LLM llama a `evaluar_viabilidad_legal`. La tool no
tiene que evaluar; el operario recibe la pregunta de confirmación con sus botones.
"""

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from fitosanitarios.dominio.modelos import ResultadoTool
from fitosanitarios.orquestador.agente import crear_agente
from fitosanitarios.orquestador.estado import ContadorRepreguntas
from fitosanitarios.orquestador.turno import ejecutar_turno
from fitosanitarios.servicios import recursos
from fitosanitarios.tools.evaluar_viabilidad_legal import tool as modulo
from tests.orquestador.fake_chat_model import (
    ChatModelFake,
    mensaje_llama_tool,
    mensaje_respuesta_estructurada,
)

ARGS_EVALUAR = {
    "tipo_aplicacion": "aerea", "cultivo": "soja", "localidad": "El Trébol",
    "productos": [{"nombre": "Flyer 10 Ec", "dosis_valor": 170, "dosis_unidad": "cm3/ha"}],
}


@pytest.fixture
def evaluaciones(monkeypatch):
    """Las veces que la tool llegó a evaluar de verdad."""
    llamadas: list[dict] = []

    def logica(args, conn, modelo, tolerancia):
        llamadas.append(args.model_dump())
        return ResultadoTool(
            estado="ok", datos={"dictamen": {"resultado": "APTA", "condiciones": None}}
        )

    monkeypatch.setattr(modulo, "evaluar_viabilidad_legal_logica", logica)
    monkeypatch.setattr(recursos, "con_conexion_y_modelo", lambda f: f(None, None))
    return llamadas


def _conversacion(respuestas_del_modelo):
    modelo = ChatModelFake(respuestas=respuestas_del_modelo)
    agente = crear_agente(modelo, checkpointer=InMemorySaver())
    contador = ContadorRepreguntas()

    def turno(texto):
        return ejecutar_turno(agente, "t-confirmacion", texto, contador)

    return turno


def test_si_el_usuario_solo_contesta_la_localidad_no_se_evalua_y_se_pide_confirmar(evaluaciones):
    turno = _conversacion([
        # t1: se mostró la receta leída de la foto para confirmar
        mensaje_respuesta_estructurada({"tipo": "confirmacion_receta"}),
        # t2: el usuario dijo "el trebol" y el LLM evalúa sin confirmación
        mensaje_llama_tool("evaluar_viabilidad_legal", ARGS_EVALUAR),
        mensaje_respuesta_estructurada({"tipo": "dictamen"}),
    ])
    turno("Te mando la foto de mi receta.")
    respuesta, mensajes = turno("el trebol")

    assert evaluaciones == []  # nunca llegó a evaluar
    assert respuesta.tipo == "dictamen"  # lo que eligió el LLM
    assert mensajes == [
        "Antes de evaluar: ¿confirmás que los datos de la receta son correctos?\n"
        "[Confirmar] [Corregir]"
    ]


def test_despues_de_confirmar_si_evalua(evaluaciones):
    turno = _conversacion([
        mensaje_respuesta_estructurada({"tipo": "confirmacion_receta"}),
        mensaje_llama_tool("evaluar_viabilidad_legal", ARGS_EVALUAR, "c1"),
        mensaje_respuesta_estructurada({"tipo": "dictamen"}, "r1"),
        mensaje_llama_tool("evaluar_viabilidad_legal", ARGS_EVALUAR, "c2"),
        mensaje_respuesta_estructurada({"tipo": "dictamen"}, "r2"),
    ])
    turno("Te mando la foto de mi receta.")
    turno("el trebol")  # bloqueado
    respuesta, mensajes = turno("Confirmar")

    assert len(evaluaciones) == 1
    assert respuesta.tipo == "dictamen" and "APTA" in mensajes[0]


def test_una_evaluacion_sin_receta_de_foto_no_pide_confirmacion(evaluaciones):
    turno = _conversacion([
        mensaje_llama_tool("evaluar_viabilidad_legal", ARGS_EVALUAR),
        mensaje_respuesta_estructurada({"tipo": "dictamen"}),
    ])
    respuesta, mensajes = turno("quiero evaluar Flyer 10 Ec en soja por aire en El Trébol")
    assert len(evaluaciones) == 1 and "APTA" in mensajes[0]


def test_el_schema_que_ve_el_llm_no_incluye_al_runtime():
    from fitosanitarios.tools.evaluar_viabilidad_legal import evaluar_viabilidad_legal

    esquema = evaluar_viabilidad_legal.args_schema.model_json_schema()
    assert "runtime" not in esquema["properties"]
