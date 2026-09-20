"""Tests del protocolo HTTP del canal web (Fase 11) con `procesar_mensaje`
stubeado -- no hace falta LLM ni Postgres reales, igual que
`tests/canales/test_webhook.py` para el canal WhatsApp."""

from fastapi.testclient import TestClient

from fitosanitarios.canales.web.canal import MensajeEntrante, crear_app, texto_final
from fitosanitarios.config import get_settings


def _cliente_y_llamadas():
    llamadas: list[tuple[str, str, str | None]] = []

    def procesar(session_id: str, texto: str, imagen_base64: str | None) -> list[str]:
        llamadas.append((session_id, texto, imagen_base64))
        return ["respuesta simulada"]

    app = crear_app(get_settings(), procesar)
    return TestClient(app), llamadas


def test_index_sirve_html():
    client, _ = _cliente_y_llamadas()
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "<title>" in resp.text


def test_mensaje_de_texto_llega_al_procesador():
    client, llamadas = _cliente_y_llamadas()
    resp = client.post("/api/mensaje", json={"session_id": "s1", "texto": "hola"})
    assert resp.status_code == 200
    assert resp.json() == {"mensajes": ["respuesta simulada"]}
    assert llamadas == [("s1", "hola", None)]


def test_mensaje_con_imagen_pasa_el_base64():
    client, llamadas = _cliente_y_llamadas()
    client.post(
        "/api/mensaje",
        json={"session_id": "s1", "texto": "mi receta", "imagen_base64": "Zm9v"},
    )
    assert llamadas == [("s1", "mi receta", "Zm9v")]


def test_mensaje_con_imagen_sin_texto_usa_texto_generico():
    """Regresión: una foto adjuntada sin escribir nada mandaba texto="" al
    agente, que nunca disparaba `leer_receta` y caía en la respuesta
    genérica de ayuda (ver DIFICULTADES.md)."""
    client, llamadas = _cliente_y_llamadas()
    client.post(
        "/api/mensaje",
        json={"session_id": "s1", "texto": "", "imagen_base64": "Zm9v"},
    )
    assert llamadas == [("s1", "Te mando la foto de mi receta.", "Zm9v")]


def test_mensaje_vacio_sin_imagen_no_llama_al_procesador():
    client, llamadas = _cliente_y_llamadas()
    resp = client.post("/api/mensaje", json={"session_id": "s1", "texto": "   "})
    assert resp.status_code == 200
    assert resp.json() == {"mensajes": []}
    assert llamadas == []


def test_la_pagina_no_ofrece_compartir_ubicacion():
    client, _ = _cliente_y_llamadas()
    html = client.get("/").text
    assert "📍" not in html and "geolocation" not in html


def test_texto_final_devuelve_el_texto():
    mensaje = MensajeEntrante(session_id="s1", texto="hola")
    assert texto_final(mensaje) == "hola"
