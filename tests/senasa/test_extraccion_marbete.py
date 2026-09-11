import json
from pathlib import Path

from fitosanitarios.llm.fake import ClienteLLMFake
from fitosanitarios.senasa.extraccion_marbete import (
    extraer_texto_pdf,
    extraer_usos_desde_texto,
)

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "senasa"


def test_extraer_texto_pdf_marbete_real():
    # PDF real: SENASA reg. 36.515, "DECIS 10 EC" (11 páginas)
    contenido = (FIXTURES / "marbete_ejemplo.pdf").read_bytes()
    texto = extraer_texto_pdf(contenido)
    assert "DECIS" in texto
    assert "deltametrina" in texto.lower()
    assert len(texto) > 1000


def test_extraer_usos_desde_texto_con_llm_fake():
    respuesta_json = json.dumps(
        [
            {
                "cultivo": "Duraznero",
                "adversidad": "Pulgón verde (Myzus persicae)",
                "dosis": "5",
                "confianza": 1.0,
            },
            {
                "cultivo": "Tomate",
                "adversidad": "Gusano grasiento (Agrotis ipsilon)",
                "dosis": "12",
                "confianza": 0.9,
            },
        ]
    )
    fake = ClienteLLMFake(respuestas=[respuesta_json])

    usos = extraer_usos_desde_texto("cualquier texto de marbete", fake)

    assert len(usos) == 2
    assert usos[0].cultivo == "Duraznero"
    assert usos[0].dosis == "5"
    assert usos[1].confianza == 0.9


def test_extraer_usos_tolera_json_envuelto_en_markdown():
    # Algunos LLM devuelven ```json ... ``` pese a la instrucción de no hacerlo.
    item = '{"cultivo": "Soja", "adversidad": null, "dosis": "2 L/ha", "confianza": 0.8}'
    respuesta = f"```json\n[{item}]\n```"
    fake = ClienteLLMFake(respuestas=[respuesta])

    usos = extraer_usos_desde_texto("texto", fake)

    assert len(usos) == 1
    assert usos[0].cultivo == "Soja"
    assert usos[0].adversidad is None


def test_extraer_usos_lista_vacia_si_no_hay_usos():
    fake = ClienteLLMFake(respuestas=["[]"])
    usos = extraer_usos_desde_texto("texto sin usos reconocibles", fake)
    assert usos == []


def test_extraer_usos_json_invalido_no_rompe():
    fake = ClienteLLMFake(respuestas=["esto no es JSON"])
    usos = extraer_usos_desde_texto("texto", fake)
    assert usos == []


def test_extraer_usos_descarta_items_con_forma_invalida():
    respuesta = json.dumps([{"cultivo": "Soja"}, {"no_es_un_uso": True}])
    fake = ClienteLLMFake(respuestas=[respuesta])
    usos = extraer_usos_desde_texto("texto", fake)
    # Al primero le falta "dosis" (requerido) -> también se descarta; ninguno pasa.
    assert usos == []


def test_extraer_usos_texto_vacio_no_llama_al_llm():
    fake = ClienteLLMFake(respuestas=["no debería usarse"])
    usos = extraer_usos_desde_texto("   ", fake)
    assert usos == []
    assert fake.llamadas == []
