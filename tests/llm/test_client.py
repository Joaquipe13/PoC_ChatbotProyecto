import pytest

from fitosanitarios.config import Settings
from fitosanitarios.llm.client import ClienteGemini, ClienteGroq, crear_cliente_llm
from fitosanitarios.llm.fake import ClienteLLMFake


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

    def falsa_generacion(self, api_key, prompt, system):
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

    def falsa_generacion(self, api_key, prompt, system):
        raise RuntimeError("429 RESOURCE_EXHAUSTED")

    monkeypatch.setattr(ClienteGemini, "_generar_con_key", falsa_generacion)

    with pytest.raises(ServicioLLMNoDisponible):
        cliente.generar("hola")
