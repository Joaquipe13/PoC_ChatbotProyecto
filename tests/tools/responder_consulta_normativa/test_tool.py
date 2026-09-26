import json

from fitosanitarios.llm.fake import ClienteLLMFake
from fitosanitarios.tools.responder_consulta_normativa import (
    ResponderConsultaNormativaArgs,
    responder_consulta_normativa_logica,
)

UMBRAL_SIMILITUD = 0.3  # bajo a propósito: separa el caso "sin respaldo" del "con respaldo"

# La primera llamada al LLM es la reformulación de la pregunta (ver servicios/reformulacion.py).
REFORMULADA = "aplicación terrestre, escuela, establecimiento educativo, distancia mínima"


def test_pregunta_sin_jurisdiccion_repregunta_con_lista(conexion, modelo_embeddings):
    args = ResponderConsultaNormativaArgs(pregunta="¿a qué distancia de una escuela?")
    fake = ClienteLLMFake()
    resultado = responder_consulta_normativa_logica(
        args, conexion, modelo_embeddings, fake, UMBRAL_SIMILITUD
    )
    assert resultado.estado == "faltan_datos"
    assert resultado.faltantes[0].campo == "jurisdiccion_id"
    assert "san-carlos-centro" in resultado.faltantes[0].opciones


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
        "regla": "La distancia minima a la zona urbana es de 300 metros.",
        "articulos_citados": [{"norma": "ley-13740-2017", "articulo": "2"}],
    })
    args = ResponderConsultaNormativaArgs(
        pregunta="¿a qué distancia de la zona urbana puedo aplicar?",
        jurisdiccion_id="Rosario", provincia="santa-fe",
    )
    resultado = responder_consulta_normativa_logica(
        args, conexion, modelo_embeddings, ClienteLLMFake(respuestas=[REFORMULADA, respuesta_llm]),
        UMBRAL_SIMILITUD,
    )
    assert resultado.estado == "ok"
    assert resultado.citas[0].norma == "ley-13740-2017"
    assert resultado.datos["sin_normativa_municipal"] is True
    assert any("No se cuenta con la normativa municipal de Rosario" in a
               for a in resultado.advertencias)


def test_pregunta_sin_respaldo_por_debajo_del_umbral(conexion, modelo_embeddings):
    # Umbral altísimo: nada llega a superarlo, sin importar la pregunta.
    args = ResponderConsultaNormativaArgs(
        pregunta="¿a qué distancia de una escuela puedo aplicar por tierra?",
        jurisdiccion_id="san-carlos-centro",
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
    respuesta_llm = json.dumps({
        "veredicto": "No",
        "regla": "La distancia minima a una escuela para aplicacion terrestre es de 100 metros.",
        "articulos_citados": [{"norma": "ordenanza-914-2018", "articulo": "8"}],
    })
    fake = ClienteLLMFake(respuestas=[REFORMULADA, respuesta_llm])

    args = ResponderConsultaNormativaArgs(
        pregunta="¿a qué distancia de una escuela puedo aplicar por tierra?",
        jurisdiccion_id="san-carlos-centro",
    )
    resultado = responder_consulta_normativa_logica(
        args, conexion, modelo_embeddings, fake, UMBRAL_SIMILITUD
    )

    assert resultado.estado == "ok"
    assert resultado.datos["veredicto"] == "No"
    assert len(resultado.citas) == 1
    assert resultado.citas[0].norma == "ordenanza-914-2018"
    assert resultado.citas[0].articulo == "8"


def test_solo_cita_alucinada_queda_no_resuelto_con_advertencia(conexion, modelo_embeddings):
    respuesta_llm = json.dumps({
        "veredicto": "Si", "regla": "Se puede sin restricciones.",
        "articulos_citados": [{"norma": "norma-inventada-2099", "articulo": "1"}],
    })
    fake = ClienteLLMFake(respuestas=[REFORMULADA, respuesta_llm])

    args = ResponderConsultaNormativaArgs(
        pregunta="¿a qué distancia de una escuela puedo aplicar por tierra?",
        jurisdiccion_id="san-carlos-centro",
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
        pregunta="¿quién ganó el mundial?", jurisdiccion_id="san-carlos-centro"
    )
    resultado = responder_consulta_normativa_logica(
        args, conexion, modelo_embeddings, fake, UMBRAL_SIMILITUD
    )
    assert resultado.estado == "no_resuelto"
    assert len(fake.llamadas) == 1  # solo la reformulación: no se generó ninguna respuesta
