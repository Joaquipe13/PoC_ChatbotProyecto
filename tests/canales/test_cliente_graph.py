"""Tests de armado de payloads y validación de límites de la Graph API, sin
red (`_payload_*` son puras). El envío/descarga real se prueba a mano contra
la API real (ver plan, Fase 8, criterios de aceptación)."""

import pytest

from fitosanitarios.canales.whatsapp.cliente_graph import (
    _payload_botones,
    _payload_lista,
    _payload_texto,
)


def test_payload_texto():
    payload = _payload_texto("5493411234567", "hola")
    assert payload["to"] == "5493411234567"
    assert payload["type"] == "text"
    assert payload["text"]["body"] == "hola"


def test_payload_botones_ok():
    botones = [{"id": "confirmar", "titulo": "Confirmar"}, {"id": "cancelar", "titulo": "Cancelar"}]
    payload = _payload_botones("5493411234567", "¿Confirmás?", botones)
    filas = payload["interactive"]["action"]["buttons"]
    assert len(filas) == 2
    assert filas[0]["reply"]["id"] == "confirmar"


def test_payload_botones_rechaza_mas_de_tres():
    botones = [{"id": str(i), "titulo": str(i)} for i in range(4)]
    with pytest.raises(ValueError, match="entre 1 y 3"):
        _payload_botones("5493411234567", "texto", botones)


def test_payload_botones_rechaza_titulo_largo():
    botones = [{"id": "x", "titulo": "x" * 21}]
    with pytest.raises(ValueError, match="título de botón demasiado largo"):
        _payload_botones("5493411234567", "texto", botones)


def test_payload_lista_ok():
    filas = [{"id": f"p{i}", "titulo": f"Producto {i}"} for i in range(5)]
    payload = _payload_lista("5493411234567", "Elegí uno", "Ver productos", filas)
    assert len(payload["interactive"]["action"]["sections"][0]["rows"]) == 5


def test_payload_lista_rechaza_mas_de_diez():
    filas = [{"id": str(i), "titulo": str(i)} for i in range(11)]
    with pytest.raises(ValueError, match="entre 1 y 10"):
        _payload_lista("5493411234567", "texto", "botón", filas)
