"""Tests del protocolo del webhook (handshake, firma, dedup, `statuses`
ignorados) con `procesar_mensaje` stubeado -- no hace falta LLM real para
estos, solo Postgres real (Docker) para la deduplicación (ver
`fitosanitarios.canales.whatsapp.dedup`).

Los tests que llegan a marcar un `message_id` como procesado usan un id
único por corrida (`uuid4`): la fila queda en `operacion.mensaje_whatsapp`
para siempre (no hay rollback entre tests), así que un string fijo hace que
la segunda corrida de la suite completa encuentre el mensaje ya procesado y
falle (ver DIFICULTADES.md, Fase 8)."""

import hashlib
import hmac
import json
import uuid

import pytest
from fastapi.testclient import TestClient

from fitosanitarios.canales.whatsapp.webhook import crear_app, texto_e_imagen, tipo_soportado
from fitosanitarios.config import get_settings


def _settings_test():
    return get_settings().model_copy(
        update={
            "whatsapp_verify_token": "verify-token-test",
            "whatsapp_app_secret": "app-secret-test",
        }
    )


def _firmar(cuerpo: bytes, secreto: str) -> str:
    return "sha256=" + hmac.new(secreto.encode(), cuerpo, hashlib.sha256).hexdigest()


def _payload_texto(message_id: str, texto: str = "hola") -> dict:
    return {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "id": message_id,
                                    "from": "5493411234567",
                                    "type": "text",
                                    "text": {"body": texto},
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }


def _payload_statuses() -> dict:
    return {
        "entry": [
            {
                "changes": [
                    {"value": {"statuses": [{"id": "wamid.status-1", "status": "delivered"}]}}
                ]
            }
        ]
    }


@pytest.fixture
def cliente_y_llamadas(conexion):
    settings = _settings_test()
    llamadas: list[tuple[dict, str]] = []
    app = crear_app(settings, lambda mensaje, numero: llamadas.append((mensaje, numero)))
    return TestClient(app), settings, llamadas


def test_handshake_responde_el_challenge(cliente_y_llamadas):
    client, settings, _ = cliente_y_llamadas
    resp = client.get(
        "/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": settings.whatsapp_verify_token,
            "hub.challenge": "1234567",
        },
    )
    assert resp.status_code == 200
    assert resp.text == "1234567"


def test_handshake_con_token_incorrecto_rechaza(cliente_y_llamadas):
    client, _, _ = cliente_y_llamadas
    resp = client.get(
        "/webhook",
        params={"hub.mode": "subscribe", "hub.verify_token": "incorrecto", "hub.challenge": "1"},
    )
    assert resp.status_code == 403


def test_post_sin_firma_devuelve_401(cliente_y_llamadas):
    client, _, llamadas = cliente_y_llamadas
    cuerpo = json.dumps(_payload_texto("wamid.sin-firma-001")).encode()
    resp = client.post("/webhook", content=cuerpo)
    assert resp.status_code == 401
    assert llamadas == []


def test_post_firma_invalida_devuelve_401(cliente_y_llamadas):
    client, _, llamadas = cliente_y_llamadas
    cuerpo = json.dumps(_payload_texto("wamid.firma-mala-001")).encode()
    resp = client.post("/webhook", content=cuerpo, headers={"X-Hub-Signature-256": "sha256=00"})
    assert resp.status_code == 401
    assert llamadas == []


def test_post_firma_valida_procesa_el_mensaje(cliente_y_llamadas):
    client, settings, llamadas = cliente_y_llamadas
    cuerpo = json.dumps(_payload_texto(f"wamid.test-{uuid.uuid4()}")).encode()
    firma = _firmar(cuerpo, settings.whatsapp_app_secret)
    resp = client.post("/webhook", content=cuerpo, headers={"X-Hub-Signature-256": firma})
    assert resp.status_code == 200
    assert len(llamadas) == 1
    assert llamadas[0][1] == "5493411234567"


def test_post_statuses_se_ignora(cliente_y_llamadas):
    client, settings, llamadas = cliente_y_llamadas
    cuerpo = json.dumps(_payload_statuses()).encode()
    firma = _firmar(cuerpo, settings.whatsapp_app_secret)
    resp = client.post("/webhook", content=cuerpo, headers={"X-Hub-Signature-256": firma})
    assert resp.status_code == 200
    assert llamadas == []


def test_post_message_id_repetido_no_se_reprocesa(cliente_y_llamadas):
    client, settings, llamadas = cliente_y_llamadas
    cuerpo = json.dumps(_payload_texto(f"wamid.test-{uuid.uuid4()}")).encode()
    firma = _firmar(cuerpo, settings.whatsapp_app_secret)
    client.post("/webhook", content=cuerpo, headers={"X-Hub-Signature-256": firma})
    client.post("/webhook", content=cuerpo, headers={"X-Hub-Signature-256": firma})
    assert len(llamadas) == 1


def test_tipo_soportado_text_image_location():
    assert tipo_soportado({"type": "text"}) is True
    assert tipo_soportado({"type": "image"}) is True
    assert tipo_soportado({"type": "location"}) is True


def test_tipo_soportado_interactive_button_o_list():
    assert tipo_soportado({"type": "interactive", "interactive": {"type": "button_reply"}}) is True
    assert tipo_soportado({"type": "interactive", "interactive": {"type": "list_reply"}}) is True


def test_tipo_soportado_interactive_no_manejado_es_no_soportado():
    assert tipo_soportado({"type": "interactive", "interactive": {"type": "nfm_reply"}}) is False


def test_tipo_soportado_sticker_o_audio_es_no_soportado():
    assert tipo_soportado({"type": "sticker"}) is False
    assert tipo_soportado({"type": "audio"}) is False


def test_texto_e_imagen_text():
    texto, imagen = texto_e_imagen({"type": "text", "text": {"body": "hola"}}, lambda _: b"")
    assert texto == "hola"
    assert imagen is None


def test_texto_e_imagen_location():
    mensaje = {"type": "location", "location": {"latitude": -32.9, "longitude": -60.6}}
    texto, imagen = texto_e_imagen(mensaje, lambda _: b"")
    assert "-32.9" in texto and "-60.6" in texto
    assert imagen is None


def test_texto_e_imagen_button_reply():
    mensaje = {
        "type": "interactive",
        "interactive": {"type": "button_reply", "button_reply": {"title": "Confirmar"}},
    }
    texto, imagen = texto_e_imagen(mensaje, lambda _: b"")
    assert texto == "Confirmar"
    assert imagen is None


def test_texto_e_imagen_descarga_y_codifica_la_foto():
    mensaje = {"type": "image", "image": {"id": "media-1", "caption": "mi receta"}}
    texto, imagen = texto_e_imagen(mensaje, lambda media_id: b"contenido-fake")
    assert texto == "mi receta"
    import base64

    assert base64.b64decode(imagen) == b"contenido-fake"


def test_texto_e_imagen_foto_sin_caption_usa_texto_generico():
    mensaje = {"type": "image", "image": {"id": "media-1"}}
    texto, _ = texto_e_imagen(mensaje, lambda _: b"x")
    assert texto == "Te mando la foto de mi receta."
