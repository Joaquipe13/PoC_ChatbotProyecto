"""Chequeo de credenciales al arrancar, con Google y Meta simulados
(`httpx.MockTransport`): no sale a la red."""

import httpx
import pytest

from fitosanitarios.canales.chequeo_credenciales import (
    Informe,
    chequear_al_arrancar,
    chequear_gemini,
    chequear_postgres,
    chequear_whatsapp,
)
from fitosanitarios.config import get_settings


def _settings(**cambios):
    base = {
        "gemini_api_key_1": "key-buena",
        "gemini_api_key_2": None,
        "gemini_api_key_3": None,
        "gemini_api_key_4": None,
        "gemini_api_key_5": None,
        "whatsapp_access_token": "token-bueno",
        "whatsapp_phone_number_id": "123",
        "whatsapp_app_secret": "secreto",
        "whatsapp_verify_token": "verify",
    }
    return get_settings().model_copy(update={**base, **cambios})


def _cliente(manejador) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(manejador))


def _google(request: httpx.Request) -> httpx.Response:
    clave = request.headers.get("x-goog-api-key")
    if clave == "key-buena":
        return httpx.Response(200, json={"name": "models/x"})
    if clave == "key-sin-cuota":
        return httpx.Response(429, json={"error": {"message": "quota"}})
    return httpx.Response(400, json={"error": {"message": "API key not valid."}})


def _meta(request: httpx.Request) -> httpx.Response:
    if request.headers.get("Authorization") == "Bearer token-bueno":
        return httpx.Response(
            200, json={"display_phone_number": "+1 555 0100", "verified_name": "Test"}
        )
    return httpx.Response(
        401, json={"error": {"code": 190, "message": "Session has expired"}}
    )


def test_gemini_key_valida():
    informe = Informe()
    chequear_gemini(_settings(), informe, _cliente(_google))
    assert informe.errores == [] and len(informe.ok) == 1


def test_gemini_key_1_invalida_es_error():
    informe = Informe()
    chequear_gemini(_settings(gemini_api_key_1="mala"), informe, _cliente(_google))
    assert "GEMINI_API_KEY_1 es inválida" in informe.errores[0]
    assert "API key not valid" in informe.errores[0]


def test_gemini_otra_key_invalida_o_sin_cuota_es_aviso():
    informe = Informe()
    settings = _settings(gemini_api_key_2="mala", gemini_api_key_3="key-sin-cuota")
    chequear_gemini(settings, informe, _cliente(_google))
    assert informe.errores == []
    assert "GEMINI_API_KEY_2" in informe.avisos[0]
    assert "cuota" in informe.avisos[1]


def test_gemini_sin_key_1_es_error():
    informe = Informe()
    chequear_gemini(_settings(gemini_api_key_1=None), informe, _cliente(_google))
    assert "falta GEMINI_API_KEY_1" in informe.errores[0]


def test_gemini_sin_conexion_es_error():
    def sin_red(request):
        raise httpx.ConnectError("sin red")

    informe = Informe()
    chequear_gemini(_settings(), informe, _cliente(sin_red))
    assert "sin conexión" in informe.errores[0]


def test_whatsapp_token_valido_muestra_el_numero():
    informe = Informe()
    chequear_whatsapp(_settings(), informe, _cliente(_meta))
    assert informe.errores == []
    assert "+1 555 0100" in informe.ok[0]


def test_whatsapp_token_vencido_explica_como_renovarlo():
    informe = Informe()
    chequear_whatsapp(_settings(whatsapp_access_token="vencido"), informe, _cliente(_meta))
    assert "vence a las 24 h" in informe.errores[0]


def test_whatsapp_faltan_variables():
    informe = Informe()
    settings = _settings(whatsapp_app_secret=None, whatsapp_verify_token="")
    chequear_whatsapp(settings, informe, _cliente(_meta))
    assert informe.errores == [
        "WhatsApp: faltan en .env: WHATSAPP_APP_SECRET, WHATSAPP_VERIFY_TOKEN."
    ]


def test_postgres_apagado_es_error():
    informe = Informe()
    settings = _settings(database_url="postgresql://postgres:postgres@127.0.0.1:1/nada")
    chequear_postgres(settings, informe)
    assert "docker compose up -d db" in informe.errores[0]


def test_con_errores_no_arranca(monkeypatch, capsys):
    cliente = _cliente(_google)
    monkeypatch.setattr(
        "fitosanitarios.canales.chequeo_credenciales.httpx.Client", lambda: cliente
    )
    settings = _settings(
        gemini_api_key_1="mala", database_url="postgresql://postgres:postgres@127.0.0.1:1/nada"
    )
    with pytest.raises(SystemExit) as salida:
        chequear_al_arrancar(settings, whatsapp=False)
    assert salida.value.code == 1
    assert "El servidor no arranca" in capsys.readouterr().err
