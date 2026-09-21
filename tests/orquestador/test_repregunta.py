"""Tests de repregunta y límite de repreguntas (ver skill, "Reglas de
repregunta"). No llaman ninguna tool -- el agente repregunta antes de
llamarlas -- así que no necesitan Postgres."""

from fitosanitarios.orquestador.agente import crear_agente
from fitosanitarios.orquestador.estado import LIMITE_INTENTOS_POR_CAMPO, ContadorRepreguntas
from fitosanitarios.orquestador.turno import ejecutar_turno
from tests.orquestador.fake_chat_model import ChatModelFake, mensaje_respuesta_estructurada

FALTANTE_TIPO_APLICACION = {
    "campo": "tipo_aplicacion", "motivo": "no informado",
    "pregunta_sugerida": "¿Terrestre o aérea?", "tipo_entrada": "botones",
    "opciones": ["Terrestre", "Aérea"],
}
FALTANTE_UBICACION = {
    "campo": "ubicacion_lote", "motivo": "no informada",
    "pregunta_sugerida": "Mandá la ubicación del lote", "tipo_entrada": "ubicacion",
}


def test_repregunta_agrupada_no_llama_ninguna_tool():
    modelo = ChatModelFake(respuestas=[
        mensaje_respuesta_estructurada({
            "tipo": "repregunta", "faltantes": [FALTANTE_UBICACION, FALTANTE_TIPO_APLICACION],
        }),
    ])
    agente = crear_agente(modelo)
    contador = ContadorRepreguntas()

    respuesta, mensajes = ejecutar_turno(
        agente, "t-repregunta-1", "quiero evaluar mi receta", contador
    )

    assert respuesta.tipo == "repregunta"
    assert len(respuesta.faltantes) == 2
    assert "1. Mandá la ubicación del lote" in mensajes[0]
    assert "2. ¿Terrestre o aérea?" in mensajes[0]
    assert len(modelo.llamadas) == 1  # una sola llamada al modelo: no hubo tool-calling


def test_primera_repregunta_no_alcanza_el_limite():
    modelo = ChatModelFake(respuestas=[
        mensaje_respuesta_estructurada({"tipo": "repregunta", "faltantes": [FALTANTE_UBICACION]}),
    ])
    agente = crear_agente(modelo)
    contador = ContadorRepreguntas()

    respuesta, _ = ejecutar_turno(agente, "t-repregunta-2", "mensaje ambiguo", contador)

    assert respuesta.tipo == "repregunta"
    assert not contador.excede_limite("t-repregunta-2", "ubicacion_lote")


def test_segunda_repregunta_del_mismo_campo_corta_con_limite_repreguntas():
    thread_id = "t-repregunta-3"
    modelo = ChatModelFake(respuestas=[
        mensaje_respuesta_estructurada({"tipo": "repregunta", "faltantes": [FALTANTE_UBICACION]})
        for _ in range(LIMITE_INTENTOS_POR_CAMPO)
    ])
    agente = crear_agente(modelo)
    contador = ContadorRepreguntas()

    for _ in range(LIMITE_INTENTOS_POR_CAMPO - 1):
        respuesta, _ = ejecutar_turno(agente, thread_id, "sigo sin mandar la ubicacion", contador)
        assert respuesta.tipo == "repregunta"

    respuesta_final, mensajes_final = ejecutar_turno(
        agente, thread_id, "sigo sin mandar la ubicacion", contador
    )
    assert respuesta_final.tipo == "no_resuelto"
    assert "LIMITE_REPREGUNTAS" in mensajes_final[0] or "ubicacion_lote" in mensajes_final[0]


def test_contestar_resetea_el_contador():
    thread_id = "t-repregunta-4"
    # 1er turno: repregunta ubicacion_lote (1er intento). 2do turno: el
    # agente ya no repregunta (el usuario contestó) -> ejecutar_turno
    # resetea el contador del thread completo.
    modelo = ChatModelFake(respuestas=[
        mensaje_respuesta_estructurada({"tipo": "repregunta", "faltantes": [FALTANTE_UBICACION]}),
        mensaje_respuesta_estructurada({"tipo": "confirmacion_receta"}),
    ])
    agente = crear_agente(modelo)
    contador = ContadorRepreguntas()

    respuesta_1, _ = ejecutar_turno(agente, thread_id, "quiero evaluar", contador)
    assert respuesta_1.tipo == "repregunta"
    assert contador.excede_limite(thread_id, "ubicacion_lote") is False

    respuesta_2, _ = ejecutar_turno(agente, thread_id, "-32.9, -60.65", contador)
    assert respuesta_2.tipo == "confirmacion_receta"

    # Si el mismo campo se repreguntara de nuevo después de esto, tendría
    # que contar como 1er intento otra vez, no como 3ro.
    assert contador.registrar_intento(thread_id, "ubicacion_lote") == 1
