import json

from fitosanitarios.llm.fake import ClienteLLMFake
from fitosanitarios.servicios.rag_normativa import (
    FragmentoNormativa,
    filtrar_por_umbral,
    responder_con_fragmentos,
)


def _fragmento_escuela() -> FragmentoNormativa:
    return FragmentoNormativa(
        articulo_id=1, numero="8",
        texto="Prohibese la aplicacion terrestre a menos de 100 metros de escuelas.",
        norma="ordenanza-914-2018", ambito="municipal",
        jurisdiccion_id="san-carlos-centro", score=0.9,
    )


# --- filtrar_por_umbral ---


def test_filtrar_por_umbral_descarta_los_que_no_llegan():
    fragmentos = [
        FragmentoNormativa(1, "1", "x", "norma-a", "municipal", "x", score=0.9),
        FragmentoNormativa(2, "2", "y", "norma-b", "municipal", "x", score=0.5),
    ]
    resultado = filtrar_por_umbral(fragmentos, umbral=0.75)
    assert len(resultado) == 1
    assert resultado[0].numero == "1"


def test_filtrar_por_umbral_todos_por_debajo_devuelve_vacio():
    fragmentos = [FragmentoNormativa(1, "1", "x", "norma-a", "municipal", "x", score=0.3)]
    assert filtrar_por_umbral(fragmentos, umbral=0.75) == []


# --- responder_con_fragmentos ---


def test_respuesta_con_cita_verificada():
    respuesta_llm = json.dumps({
        "veredicto": "No",
        "regla": "La distancia minima a una escuela es de 100 metros para aplicacion terrestre.",
        "articulos_citados": [{"norma": "ordenanza-914-2018", "articulo": "8"}],
    })
    fake = ClienteLLMFake(respuestas=[respuesta_llm])

    resultado = responder_con_fragmentos("¿puedo aplicar a 80m?", [_fragmento_escuela()], fake)

    assert resultado.veredicto == "No"
    assert len(resultado.citas) == 1
    assert resultado.citas[0].norma == "ordenanza-914-2018"
    assert resultado.citas[0].articulo == "8"
    assert resultado.citas[0].jurisdiccion_id == "san-carlos-centro"
    assert resultado.advertencias == []


def test_cita_alucinada_no_presente_en_fragmentos_se_descarta():
    # Caso exigido por plandefases.md, Fase 6: el LLM "alucina" un artículo
    # no recuperado -> la cita se descarta y aparece en advertencias, no en
    # citas.
    respuesta_llm = json.dumps({
        "veredicto": "Si",
        "regla": "Se puede aplicar sin restricciones.",
        "articulos_citados": [{"norma": "ordenanza-inventada-2099", "articulo": "99"}],
    })
    fake = ClienteLLMFake(respuestas=[respuesta_llm])

    resultado = responder_con_fragmentos("¿puedo aplicar?", [_fragmento_escuela()], fake)

    assert resultado.citas == []
    assert len(resultado.advertencias) == 1
    assert "ordenanza-inventada-2099" in resultado.advertencias[0]


def test_cita_parcialmente_alucinada_solo_descarta_la_invalida():
    otro_fragmento = FragmentoNormativa(
        2, "10", "sobre cursos de agua", "ordenanza-914-2018", "municipal",
        "san-carlos-centro", score=0.8,
    )
    respuesta_llm = json.dumps({
        "veredicto": "Depende",
        "regla": "Depende de la zona.",
        "articulos_citados": [
            {"norma": "ordenanza-914-2018", "articulo": "8"},  # real
            {"norma": "ordenanza-914-2018", "articulo": "99"},  # no existe
        ],
    })
    fake = ClienteLLMFake(respuestas=[respuesta_llm])

    resultado = responder_con_fragmentos(
        "¿puedo aplicar?", [_fragmento_escuela(), otro_fragmento], fake
    )

    assert len(resultado.citas) == 1
    assert resultado.citas[0].articulo == "8"
    assert len(resultado.advertencias) == 1


def test_respuesta_no_json_no_rompe():
    fake = ClienteLLMFake(respuestas=["esto no es JSON"])
    resultado = responder_con_fragmentos("¿puedo aplicar?", [_fragmento_escuela()], fake)
    assert resultado.veredicto == "Depende"
    assert resultado.citas == []
    assert resultado.advertencias != []


def test_sin_articulos_citados_no_hay_citas():
    respuesta_llm = json.dumps({
        "veredicto": "Depende", "regla": "No hay informacion suficiente.",
        "articulos_citados": [],
    })
    fake = ClienteLLMFake(respuestas=[respuesta_llm])
    resultado = responder_con_fragmentos("¿puedo aplicar?", [_fragmento_escuela()], fake)
    assert resultado.citas == []
    assert resultado.advertencias == []
