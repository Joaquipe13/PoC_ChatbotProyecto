"""Tope de llamadas a tools por turno (modelo simulado, sin base ni red).

Gemini llegó a llamar cinco veces a la misma tool en un turno, y cada vuelta reenvía los
esquemas de las tools y el prompt. Las tools que cortan el turno (`return_direct`) ya no
pueden encadenarse; el tope cubre las llamadas en paralelo y a `evaluar_riesgo`.
"""

import pytest
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver

from fitosanitarios.dominio.modelos import ResultadoTool
from fitosanitarios.orquestador.agente import LIMITE_TOOLS_POR_TURNO, crear_agente
from fitosanitarios.orquestador.estado import ContadorRepreguntas
from fitosanitarios.orquestador.turno import ejecutar_turno
from fitosanitarios.servicios import recursos
from fitosanitarios.tools.evaluar_viabilidad_legal import tool as modulo
from tests.orquestador.fake_chat_model import ChatModelFake

ARGS = {
    "tipo_aplicacion": "aerea", "cultivo": "soja", "localidad": "El Trébol",
    "productos": [{"nombre": "Flyer 10 Ec", "dosis_valor": 170, "dosis_unidad": "cm3/ha"}],
}


@pytest.fixture
def evaluaciones(monkeypatch):
    llamadas: list[dict] = []

    def logica(args, conn, modelo, tolerancia):
        llamadas.append(args.model_dump())
        return ResultadoTool(
            estado="ok", datos={"dictamen": {"resultado": "APTA", "condiciones": None}}
        )

    monkeypatch.setattr(modulo, "evaluar_viabilidad_legal_logica", logica)
    monkeypatch.setattr(recursos, "con_conexion_y_modelo", lambda f: f(None, None))
    return llamadas


def _turnos(respuestas_del_modelo):
    agente = crear_agente(ChatModelFake(respuestas=respuestas_del_modelo), InMemorySaver())
    contador = ContadorRepreguntas()
    return lambda texto: ejecutar_turno(agente, "t-limite", texto, contador)


def _en_paralelo(n, prefijo):
    """Un solo mensaje del modelo con `n` llamadas a la misma tool."""
    return AIMessage(content="", tool_calls=[
        {"name": "evaluar_viabilidad_legal", "args": ARGS, "id": f"{prefijo}{i}"}
        for i in range(n)
    ])


def test_una_tool_llamada_de_mas_no_pasa_del_tope_y_el_turno_termina(evaluaciones):
    turno = _turnos([_en_paralelo(LIMITE_TOOLS_POR_TURNO + 2, "a")])
    respuesta, mensajes = turno("evaluá esto")

    assert len(evaluaciones) == LIMITE_TOOLS_POR_TURNO
    assert respuesta.tipo == "dictamen" and "APTA" in mensajes[0]


def test_el_tope_es_por_turno_no_por_conversacion(evaluaciones):
    turno = _turnos([_en_paralelo(3, "a"), _en_paralelo(3, "b")])
    turno("primero")
    turno("segundo")
    assert len(evaluaciones) == 6
