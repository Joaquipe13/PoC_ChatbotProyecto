import json

from fitosanitarios.llm.fake import ClienteLLMFake
from fitosanitarios.tools.responder_consulta_normativa import (
    ResponderConsultaNormativaArgs,
    responder_consulta_normativa_logica,
)

UMBRAL_SIMILITUD = 0.3  # bajo a propósito: separa el caso "sin respaldo" del "con respaldo"

# La primera llamada al LLM es la reformulación de la pregunta (ver servicios/reformulacion.py).
REFORMULADA = (
    "vientos, deriva hacia la planta urbana, pulverizaciones, intensidad del viento en km/h"
)
PREGUNTA = "¿puedo fumigar con viento?"
# Ordenanza 841/2010 de El Trébol, art. 4: prohíbe pulverizar con vientos de más de 8 km/h
# que puedan producir derivas hacia la planta urbana.
RESPUESTA_ART_4 = json.dumps({
    "veredicto": "Depende",
    "regla": "Con viento de más de 8 km/h que lleve la deriva hacia la planta urbana, no.",
    "articulos_citados": [{"norma": "ordenanza-841-2010", "articulo": "4"}],
})


def test_pregunta_sin_jurisdiccion_repregunta_con_lista(conexion, modelo_embeddings):
    args = ResponderConsultaNormativaArgs(pregunta="¿a qué distancia de una escuela?")
    fake = ClienteLLMFake()
    resultado = responder_consulta_normativa_logica(
        args, conexion, modelo_embeddings, fake, UMBRAL_SIMILITUD
    )
    assert resultado.estado == "faltan_datos"
    assert resultado.faltantes[0].campo == "jurisdiccion_id"
    assert "el-trebol" in resultado.faltantes[0].opciones


def test_localidad_desconocida_se_vuelve_a_pedir(conexion, modelo_embeddings):
    args = ResponderConsultaNormativaArgs(
        pregunta="¿a qué distancia de una escuela?", jurisdiccion_id="localidad-inexistente"
    )
    fake = ClienteLLMFake()
    resultado = responder_consulta_normativa_logica(
        args, conexion, modelo_embeddings, fake, UMBRAL_SIMILITUD
    )
    assert resultado.estado == "faltan_datos"
    assert resultado.faltantes[0].campo == "localidad"
    assert fake.llamadas == []


def test_provincia_no_cargada_es_jurisdiccion_no_cubierta(conexion, modelo_embeddings):
    args = ResponderConsultaNormativaArgs(
        pregunta="¿a qué distancia de una escuela?", jurisdiccion_id="localidad-inexistente",
        provincia="provincia-que-no-existe",
    )
    resultado = responder_consulta_normativa_logica(
        args, conexion, modelo_embeddings, ClienteLLMFake(), UMBRAL_SIMILITUD
    )
    from fitosanitarios.dominio.motivos import MotivoNoResuelto

    assert resultado.estado == "no_resuelto"
    assert resultado.motivo == MotivoNoResuelto.JURISDICCION_NO_CUBIERTA


def test_localidad_sin_normativa_local_responde_con_la_provincial_y_lo_aclara(
    conexion, modelo_embeddings
):
    respuesta_llm = json.dumps({
        "veredicto": "No",
        "regla": "Con banda amarilla, a menos de 500 metros de la planta urbana no.",
        "articulos_citados": [{"norma": "ley-11273-1995", "articulo": "34"}],
    })
    args = ResponderConsultaNormativaArgs(
        pregunta="¿a qué distancia de la planta urbana puedo aplicar por tierra?",
        jurisdiccion_id="Rosario", provincia="santa-fe",
    )
    resultado = responder_consulta_normativa_logica(
        args, conexion, modelo_embeddings, ClienteLLMFake(respuestas=[REFORMULADA, respuesta_llm]),
        UMBRAL_SIMILITUD,
    )
    assert resultado.estado == "ok"
    assert resultado.citas[0].norma == "ley-11273-1995"
    assert resultado.datos["sin_normativa_municipal"] is True
    assert any("No se cuenta con la normativa municipal de Rosario" in a
               for a in resultado.advertencias)


def test_pregunta_sin_respaldo_por_debajo_del_umbral(conexion, modelo_embeddings):
    # Umbral altísimo: nada llega a superarlo, sin importar la pregunta.
    args = ResponderConsultaNormativaArgs(
        pregunta=PREGUNTA, jurisdiccion_id="el-trebol",
    )
    fake = ClienteLLMFake()  # solo para reformular: no llega a generar una respuesta
    resultado = responder_consulta_normativa_logica(
        args, conexion, modelo_embeddings, fake, umbral_similitud=0.999
    )
    assert resultado.estado == "no_resuelto"

    from fitosanitarios.dominio.motivos import MotivoNoResuelto

    assert resultado.motivo == MotivoNoResuelto.NORMATIVA_SIN_RESPALDO
    from fitosanitarios.tools.responder_consulta_normativa.prompts import PROMPT_REFORMULACION

    assert [ll["system"] for ll in fake.llamadas] == [PROMPT_REFORMULACION]


def test_pregunta_con_respaldo_devuelve_cita_verificada(conexion, modelo_embeddings):
    fake = ClienteLLMFake(respuestas=[REFORMULADA, RESPUESTA_ART_4])
    args = ResponderConsultaNormativaArgs(pregunta=PREGUNTA, jurisdiccion_id="el-trebol")
    resultado = responder_consulta_normativa_logica(
        args, conexion, modelo_embeddings, fake, UMBRAL_SIMILITUD
    )

    assert resultado.estado == "ok"
    assert resultado.datos["veredicto"] == "Depende"
    assert len(resultado.citas) == 1
    assert resultado.citas[0].norma == "ordenanza-841-2010"
    assert resultado.citas[0].articulo == "4"


def test_solo_cita_alucinada_queda_no_resuelto_con_advertencia(conexion, modelo_embeddings):
    respuesta_llm = json.dumps({
        "veredicto": "Si", "regla": "Se puede sin restricciones.",
        "articulos_citados": [{"norma": "norma-inventada-2099", "articulo": "1"}],
    })
    fake = ClienteLLMFake(respuestas=[REFORMULADA, respuesta_llm])

    args = ResponderConsultaNormativaArgs(
        pregunta=PREGUNTA, jurisdiccion_id="el-trebol",
    )
    resultado = responder_consulta_normativa_logica(
        args, conexion, modelo_embeddings, fake, UMBRAL_SIMILITUD
    )

    from fitosanitarios.dominio.motivos import MotivoNoResuelto

    assert resultado.estado == "no_resuelto"
    assert resultado.motivo == MotivoNoResuelto.NORMATIVA_SIN_RESPALDO
    assert resultado.citas == []
    assert len(resultado.advertencias) == 1


def test_una_pregunta_fuera_de_tema_no_se_busca(conexion, modelo_embeddings):
    fake = ClienteLLMFake(respuestas=["FUERA"])
    args = ResponderConsultaNormativaArgs(
        pregunta="¿quién ganó el mundial?", jurisdiccion_id="el-trebol"
    )
    resultado = responder_consulta_normativa_logica(
        args, conexion, modelo_embeddings, fake, UMBRAL_SIMILITUD
    )
    assert resultado.estado == "no_resuelto"
    assert len(fake.llamadas) == 1  # solo la reformulación: no se generó ninguna respuesta


def test_modo_demo_muestra_la_respuesta_con_y_sin_reformular(conexion, modelo_embeddings):
    """Con la pregunta tal cual el LLM cita una norma que no se recuperó (se descarta y no
    hay respuesta); con la reformulada cita el artículo recuperado."""
    from fitosanitarios.dominio.modelos import RespuestaAgente
    from fitosanitarios.orquestador.formateador import formatear_respuesta

    fake = ClienteLLMFake(respuestas=[
        json.dumps({
            "veredicto": "Si", "regla": "Se puede sin restricciones.",
            "articulos_citados": [{"norma": "norma-inventada-2099", "articulo": "1"}],
        }),
        REFORMULADA,
        RESPUESTA_ART_4,
    ])
    args = ResponderConsultaNormativaArgs(pregunta=PREGUNTA, jurisdiccion_id="el-trebol")
    resultado = responder_consulta_normativa_logica(
        args, conexion, modelo_embeddings, fake, UMBRAL_SIMILITUD, modo_demo_reformulacion=True
    )

    assert resultado.estado == "ok"
    assert len(fake.llamadas) == 3
    texto = "\n\n".join(
        formatear_respuesta(RespuestaAgente(tipo="consulta_normativa"), [resultado])
    )
    original, reformulada = texto.split("*Pregunta reformulada (lo que se busca):*")
    assert "No cuento con esa información" in original
    assert REFORMULADA in reformulada
    assert "más de 8 km/h" in reformulada
