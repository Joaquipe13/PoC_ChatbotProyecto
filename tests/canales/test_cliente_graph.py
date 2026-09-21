"""Tests de armado de payloads y validación de límites de la Graph API, sin
red (`_payload_*` son puras). El envío/descarga real se prueba a mano contra
la API real (ver plan, Fase 8, criterios de aceptación)."""

import pytest

from fitosanitarios.canales.whatsapp import cliente_graph
from fitosanitarios.canales.whatsapp.cliente_graph import (
    _payload_botones,
    _payload_con_opciones,
    _payload_lista,
    _payload_texto,
    partir_opciones,
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


# --- opciones del formateador -> botones / lista interactivos ---


def test_partir_opciones_linea_de_botones_al_final():
    cuerpo, opciones = partir_opciones("*Leí la receta*\n- *Cultivo:* soja\n[Confirmar] [Corregir]")
    assert cuerpo == "*Leí la receta*\n- *Cultivo:* soja"
    assert opciones == ["Confirmar", "Corregir"]


def test_partir_opciones_bloque_de_lista_al_final():
    texto = "Necesito 1 dato:\n1. *provincia*: ¿Cuál?\n   - Santa Fe\n   - Córdoba"
    cuerpo, opciones = partir_opciones(texto)
    assert cuerpo == "Necesito 1 dato:\n1. *provincia*: ¿Cuál?"
    assert opciones == ["Santa Fe", "Córdoba"]


def test_partir_opciones_ignora_las_que_quedan_en_el_medio():
    texto = "1. *a*: ¿Sí?\n[Sí] [No]\n2. *b*: ¿Cuál?"
    assert partir_opciones(texto) == (texto, [])


def test_partir_opciones_no_confunde_la_seccion_fuentes():
    texto = "Respuesta\n\n*Fuentes*\n- Ordenanza 841/2010, art. 7"
    assert partir_opciones(texto) == (texto, [])


def test_payload_con_opciones_hasta_tres_es_botones():
    payload = _payload_con_opciones("549", "¿Confirmás?", ["Confirmar", "Corregir"])
    assert payload["interactive"]["type"] == "button"
    assert payload["interactive"]["action"]["buttons"][1]["reply"]["title"] == "Corregir"


def test_payload_con_opciones_de_cuatro_a_diez_es_lista():
    payload = _payload_con_opciones("549", "Elegí", [f"Opción {i}" for i in range(6)])
    assert payload["interactive"]["type"] == "list"


def test_payload_con_opciones_titulo_de_mas_de_20_pasa_a_lista():
    opciones = ["Glifosato 48% Ebc Gold", "Glifosato 48 Sigma"]
    payload = _payload_con_opciones("549", "Elegí", opciones)
    assert payload["interactive"]["type"] == "list"


@pytest.mark.parametrize("cuerpo, opciones", [
    ("", ["Sí", "No"]),                      # sin cuerpo
    ("x" * 1025, ["Sí", "No"]),              # cuerpo más largo que el límite de la API
    ("Elegí", ["Sí", "Sí"]),                 # títulos repetidos
    ("Elegí", ["x" * 25]),                   # título más largo que el de una fila
    ("Elegí", [str(i) for i in range(11)]),  # más de 10 filas
])
def test_payload_con_opciones_fuera_de_limites_devuelve_none(cuerpo, opciones):
    assert _payload_con_opciones("549", cuerpo, opciones) is None


def test_enviar_mensajes_manda_interactivo_y_texto_segun_corresponda(monkeypatch):
    enviados = []
    monkeypatch.setattr(cliente_graph, "_enviar", lambda _settings, p: enviados.append(p))
    cliente_graph.enviar_mensajes(None, "549", ["Listo\n[Confirmar] [Corregir]", "Hola"])
    assert [p["type"] for p in enviados] == ["interactive", "text"]


def test_enviar_mensajes_reenvia_como_texto_si_la_api_rechaza_el_interactivo(monkeypatch):
    enviados = []

    def falso(settings, payload):
        if payload["type"] == "interactive":
            raise cliente_graph.ErrorEnvioWhatsApp("rechazado")
        enviados.append(payload)

    monkeypatch.setattr(cliente_graph, "_enviar", falso)
    cliente_graph.enviar_mensajes(None, "549", ["Listo\n[Confirmar] [Corregir]"])
    assert enviados[0]["text"]["body"] == "Listo\n[Confirmar] [Corregir]"
