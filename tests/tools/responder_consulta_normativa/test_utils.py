import json

from fitosanitarios.llm.fake import ClienteLLMFake
from fitosanitarios.tools.responder_consulta_normativa.utils import (
    FragmentoNormativa,
    filtrar_por_umbral,
    responder_con_fragmentos,
)


def _fragmento_art_7() -> FragmentoNormativa:
    """Ordenanza 841/2010 de El Trébol, art. 7 (texto real)."""
    return FragmentoNormativa(
        articulo_id=1, numero="7",
        texto=(
            "Prohíbese la aplicación aérea de productos fitosanitarios clasificados como "
            "Banda Amarilla desde el Límite 0 y hasta 3.000 metros del mismo."
        ),
        norma="ordenanza-841-2010", ambito="municipal",
        jurisdiccion_id="el-trebol", score=0.9,
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
        "regla": "Con banda amarilla no se puede aplicar por avión a menos de 3000 metros.",
        "articulos_citados": [{"norma": "ordenanza-841-2010", "articulo": "7"}],
    })
    fake = ClienteLLMFake(respuestas=[respuesta_llm])

    resultado = responder_con_fragmentos(
        "¿puedo aplicar con avión a 1000 m con banda amarilla?", [_fragmento_art_7()], fake
    )

    assert resultado.veredicto == "No"
    assert len(resultado.citas) == 1
    assert resultado.citas[0].norma == "ordenanza-841-2010"
    assert resultado.citas[0].articulo == "7"
    assert resultado.citas[0].jurisdiccion_id == "el-trebol"
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

    resultado = responder_con_fragmentos("¿puedo aplicar?", [_fragmento_art_7()], fake)

    assert resultado.citas == []
    assert len(resultado.advertencias) == 1
    assert "ordenanza-inventada-2099" in resultado.advertencias[0]


def test_cita_parcialmente_alucinada_solo_descarta_la_invalida():
    art_4 = FragmentoNormativa(
        2, "4", "Prohíbese las pulverizaciones ... por efecto de vientos de una intensidad "
        "mayor a 8 km/hora ...", "ordenanza-841-2010", "municipal", "el-trebol", score=0.8,
    )
    respuesta_llm = json.dumps({
        "veredicto": "Depende",
        "regla": "Depende de la zona.",
        "articulos_citados": [
            {"norma": "ordenanza-841-2010", "articulo": "7"},  # recuperado
            {"norma": "ordenanza-841-2010", "articulo": "99"},  # no existe
        ],
    })
    fake = ClienteLLMFake(respuestas=[respuesta_llm])

    resultado = responder_con_fragmentos(
        "¿puedo aplicar?", [_fragmento_art_7(), art_4], fake
    )

    assert len(resultado.citas) == 1
    assert resultado.citas[0].articulo == "7"
    assert len(resultado.advertencias) == 1


def test_respuesta_no_json_no_rompe():
    fake = ClienteLLMFake(respuestas=["esto no es JSON"])
    resultado = responder_con_fragmentos("¿puedo aplicar?", [_fragmento_art_7()], fake)
    assert resultado.veredicto == "Depende"
    assert resultado.citas == []
    assert resultado.advertencias != []


def test_sin_articulos_citados_no_hay_citas():
    respuesta_llm = json.dumps({
        "veredicto": "Depende", "regla": "No hay informacion suficiente.",
        "articulos_citados": [],
    })
    fake = ClienteLLMFake(respuestas=[respuesta_llm])
    resultado = responder_con_fragmentos("¿puedo aplicar?", [_fragmento_art_7()], fake)
    assert resultado.citas == []
    assert resultado.advertencias == []


def test_un_fragmento_sin_articulo_se_cita_por_la_norma_sola():
    """Un fallo judicial no tiene artículos: el LLM lo cita con "" y la cita queda sin
    número de artículo."""
    fallo = FragmentoNormativa(
        articulo_id=5, numero=None, texto="Se prohíbe fumigar a menos de 1000 m del pueblo.",
        norma="fallo-sastre-2020", ambito="municipal", jurisdiccion_id="sastre", score=0.7,
    )
    respuesta_llm = json.dumps({
        "veredicto": "No", "regla": "El fallo prohíbe fumigar a menos de 1000 m.",
        "articulos_citados": [{"norma": "fallo-sastre-2020", "articulo": ""}],
    })
    resultado = responder_con_fragmentos("¿qué dice el fallo?", [fallo], ClienteLLMFake(
        respuestas=[respuesta_llm]
    ))
    assert [(c.norma, c.articulo) for c in resultado.citas] == [("fallo-sastre-2020", None)]


def test_el_contexto_marca_de_donde_sale_cada_fragmento():
    from fitosanitarios.tools.responder_consulta_normativa.utils import _armar_contexto

    regla = FragmentoNormativa(
        articulo_id=1, numero="33", texto="prohibido a menos de 3000 m", norma="ley-11273-1995",
        ambito="provincial", jurisdiccion_id="santa-fe", score=0.6, tipo="regla",
    )
    fallo = FragmentoNormativa(
        articulo_id=2, numero=None, texto="texto del fallo", norma="fallo-sastre-2020",
        ambito="municipal", jurisdiccion_id="sastre", score=0.6,
    )
    contexto = _armar_contexto([regla, fallo])
    assert "[ley-11273-1995, regla cargada, art. 33, jurisdicción: santa-fe]" in contexto
    assert "[fallo-sastre-2020, sin artículo, jurisdicción: sastre]" in contexto
