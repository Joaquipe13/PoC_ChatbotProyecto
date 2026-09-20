from dataclasses import dataclass, field

import pytest

from fitosanitarios.config import Settings
from fitosanitarios.llm.client import (
    ClienteGemini,
    ClienteGroq,
    _texto_de_respuesta,
    crear_cliente_llm,
)
from fitosanitarios.llm.fake import ClienteLLMFake


@dataclass
class _ParteFalsa:
    text: str | None
    thought: bool = False


@dataclass
class _ContenidoFalso:
    parts: list[_ParteFalsa] = field(default_factory=list)


@dataclass
class _CandidatoFalso:
    content: _ContenidoFalso | None = None


@dataclass
class _RespuestaFalsa:
    text: str | None
    candidates: list[_CandidatoFalso] = field(default_factory=list)


def test_crear_cliente_llm_devuelve_fake_con_use_fixtures(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost/db")
    settings = Settings(_env_file=None)
    cliente = crear_cliente_llm(settings)
    assert isinstance(cliente, ClienteLLMFake)


def test_cliente_gemini_requiere_al_menos_una_key():
    with pytest.raises(ValueError):
        ClienteGemini(api_keys=[], model="gemini-flash-latest")


def test_cliente_groq_requiere_key():
    with pytest.raises(ValueError):
        ClienteGroq(api_key="", model="llama-3.3-70b-versatile")


def test_cliente_gemini_rota_ante_error_de_cuota(monkeypatch):
    cliente = ClienteGemini(api_keys=["key-agotada", "key-buena"], model="gemini-flash-latest")

    llamadas: list[str] = []

    def falsa_generacion(self, api_key, prompt, system, imagen, mime_type="image/jpeg"):
        llamadas.append(api_key)
        if api_key == "key-agotada":
            raise RuntimeError("429 RESOURCE_EXHAUSTED")
        return "respuesta ok"

    monkeypatch.setattr(ClienteGemini, "_generar_con_key", falsa_generacion)

    assert cliente.generar("hola") == "respuesta ok"
    assert llamadas == ["key-agotada", "key-buena"]


def test_cliente_gemini_agota_todas_las_keys(monkeypatch):
    from fitosanitarios.llm.client import ServicioLLMNoDisponible

    cliente = ClienteGemini(api_keys=["k1", "k2"], model="gemini-flash-latest")

    def falsa_generacion(self, api_key, prompt, system, imagen, mime_type="image/jpeg"):
        raise RuntimeError("429 RESOURCE_EXHAUSTED")

    monkeypatch.setattr(ClienteGemini, "_generar_con_key", falsa_generacion)

    with pytest.raises(ServicioLLMNoDisponible):
        cliente.generar("hola")


def test_cliente_gemini_generar_con_imagen_pasa_los_bytes(monkeypatch):
    cliente = ClienteGemini(api_keys=["k1"], model="gemini-flash-latest")
    recibido = {}

    def falsa_generacion(self, api_key, prompt, system, imagen, mime_type="image/jpeg"):
        recibido["imagen"] = imagen
        recibido["mime_type"] = mime_type
        return "ok"

    monkeypatch.setattr(ClienteGemini, "_generar_con_key", falsa_generacion)

    resultado = cliente.generar_con_imagen(b"contenido-jpeg", "describí esta imagen")

    assert resultado == "ok"
    assert recibido["imagen"] == b"contenido-jpeg"
    assert recibido["mime_type"] == "image/jpeg"


# --- _texto_de_respuesta (regresión, ver DIFICULTADES.md) ---


def test_texto_de_respuesta_usa_el_accessor_cuando_no_esta_vacio():
    respuesta = _RespuestaFalsa(text="hola")
    assert _texto_de_respuesta(respuesta) == "hola"


def test_texto_de_respuesta_cae_a_las_partes_si_el_accessor_da_vacio():
    """Caso real: `gemini-3.5-flash-lite` en llamadas multimodales devuelve
    `respuesta.text == ""` aunque el JSON pedido está completo en
    `candidates[0].content.parts[0].text` (con un `thought_signature` que
    rompe la heurística de esa propiedad, ver `_texto_de_respuesta`)."""
    parte = _ParteFalsa(text='{"legible": true}')
    respuesta = _RespuestaFalsa(text="", candidates=[_CandidatoFalso(_ContenidoFalso([parte]))])
    assert _texto_de_respuesta(respuesta) == '{"legible": true}'


def test_texto_de_respuesta_ignora_partes_marcadas_como_pensamiento():
    partes = [_ParteFalsa(text="razonando...", thought=True), _ParteFalsa(text="respuesta final")]
    respuesta = _RespuestaFalsa(text="", candidates=[_CandidatoFalso(_ContenidoFalso(partes))])
    assert _texto_de_respuesta(respuesta) == "respuesta final"


def test_texto_de_respuesta_sin_candidatos_devuelve_vacio():
    assert _texto_de_respuesta(_RespuestaFalsa(text="", candidates=[])) == ""
