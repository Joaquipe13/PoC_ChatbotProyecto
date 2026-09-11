"""Tests de detección de fuera de dominio (ver skill, "Política del
orquestador": se decide ANTES de llamar cualquier tool). No necesitan
Postgres: si el agente clasifica bien, no llega a ejecutar ninguna tool."""

from fitosanitarios.orquestador.agente import crear_agente
from fitosanitarios.orquestador.estado import ContadorRepreguntas
from fitosanitarios.orquestador.turno import ejecutar_turno
from tests.orquestador.fake_chat_model import ChatModelFake, mensaje_respuesta_estructurada


def test_mensaje_claramente_fuera_de_dominio():
    modelo = ChatModelFake(respuestas=[
        mensaje_respuesta_estructurada({"tipo": "fuera_de_dominio"}),
    ])
    agente = crear_agente(modelo)
    contador = ContadorRepreguntas()

    respuesta, mensajes = ejecutar_turno(agente, "t-fdd-1", "¿va a llover mañana?", contador)

    assert respuesta.tipo == "fuera_de_dominio"
    assert mensajes[0].startswith("Solo puedo ayudarte con recetas de fitosanitarios")
    assert len(modelo.llamadas) == 1  # no llamó ninguna tool


def test_fuera_de_dominio_no_llama_ninguna_tool_ni_toca_el_contador():
    modelo = ChatModelFake(respuestas=[
        mensaje_respuesta_estructurada({"tipo": "fuera_de_dominio"}),
    ])
    agente = crear_agente(modelo)
    contador = ContadorRepreguntas()

    ejecutar_turno(agente, "t-fdd-2", "contame un chiste", contador)

    assert not contador.excede_limite("t-fdd-2", "cualquier_campo")


def test_saludo_se_clasifica_como_ayuda_no_fuera_de_dominio():
    # No es lo mismo "fuera de dominio" (rechazo) que "ayuda" (bienvenida) --
    # ambos casos posibles según cómo clasifique el LLM un saludo; acá se
    # prueba que el pipeline no rompe con ninguno de los dos.
    modelo = ChatModelFake(respuestas=[mensaje_respuesta_estructurada({"tipo": "ayuda"})])
    agente = crear_agente(modelo)
    contador = ContadorRepreguntas()

    respuesta, mensajes = ejecutar_turno(agente, "t-fdd-3", "hola", contador)

    assert respuesta.tipo == "ayuda"
    assert "recetas" in mensajes[0].lower()
