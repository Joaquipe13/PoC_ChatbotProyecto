"""Tests del agente de prueba con un simulador y un bot falsos (sin red ni base).

Como los de `test_invariantes.py`, no corren con `pytest` a secas: `uv run pytest evals`.
"""

import json

import pytest

from evals import agente_prueba as ap
from evals import chat, registro

ESCENARIO = {
    "id": "caso_prueba", "persona": "Marcos", "objetivo": "saber si puede aplicar",
    "datos": {"imagen": "data/recetas_ejemplo/01_apta_terrestre.jpg"},
    "comportamiento": "manda la foto", "expectativas_duras": [{"tipo": "alguna_tool"}],
}


class SimuladorFalso:
    def __init__(self, *respuestas):
        self.respuestas = list(respuestas)
        self.pedidos = []

    def generar(self, prompt, *, system=None):
        self.pedidos.append(prompt)
        return self.respuestas.pop(0)


def _reg(texto, envio="texto", opciones=()):
    return {"mensajes": [{"texto": texto, "envio": envio, "opciones": list(opciones)}]}


@pytest.fixture
def run(tmp_path, monkeypatch):
    monkeypatch.setattr(registro, "RUNS", tmp_path)
    return "r1"


def test_interpretar_acepta_json_con_o_sin_bloque_de_codigo():
    assert ap.interpretar('{"accion": "escribir", "mensaje": "hola"}').mensaje == "hola"
    assert ap.interpretar('```json\n{"accion": "terminar", "resultado": "x"}\n```').accion == (
        "terminar"
    )
    assert ap.interpretar("hola") is None
    assert ap.interpretar('{"accion": "bailar"}') is None


def test_el_simulador_no_recibe_las_expectativas():
    pedido = ap.pedido_al_simulador(ESCENARIO, [])
    assert "Marcos" in pedido and "expectativas" not in pedido and "alguna_tool" not in pedido


def test_lo_que_ve_el_usuario_incluye_los_botones():
    texto = ap.lo_que_vio_el_usuario(_reg("¿Agendamos?", "botones", ["Agendar", "No"]))
    assert texto == "¿Agendamos?\n[BOTONES: Agendar | No]"


def test_una_conversacion_con_foto_y_cierre(run):
    simulador = SimuladorFalso(
        json.dumps({"accion": "foto", "mensaje": ""}),
        json.dumps({"accion": "escribir", "mensaje": "en El Trebol"}),
        json.dumps({"accion": "terminar", "resultado": "objetivo logrado: es apta"}),
    )
    enviados = []

    def turno(thread, run_, texto, imagen, pausa, max_turnos):
        enviados.append((thread, texto, imagen))
        return _reg(f"respuesta a {texto}"), 0

    cierre = ap.conversar(ESCENARIO, run, 1, simulador, 0, 5, turno=turno)
    assert cierre["logrado"] is True
    assert enviados[0][0] == "sim-caso_prueba__1"
    assert enviados[0][1] == chat.TEXTO_FOTO_POR_DEFECTO  # foto sin texto
    assert enviados[0][2].name == "01_apta_terrestre.jpg"
    assert enviados[1][2] is None
    # el segundo pedido al simulador ya trae la respuesta del bot
    assert "respuesta a Te mando la foto" in simulador.pedidos[1]
    registros = registro.leer_registros(registro.ruta_log(run, "sim-caso_prueba__1"))
    assert registros[-1]["tipo_registro"] == "cierre" and registros[-1]["simulador"] == "gemini"


def test_una_falla_de_infraestructura_se_reintenta_una_vez(run, monkeypatch):
    monkeypatch.setattr(ap, "ESPERA_INFRA_S", 0)
    simulador = SimuladorFalso(
        json.dumps({"accion": "escribir", "mensaje": "hola"}),
        json.dumps({"accion": "terminar", "resultado": "objetivo logrado"}),
    )
    codigos = [chat.CODIGO_INFRA, 0]

    def turno(*_):
        return _reg("ok"), codigos.pop(0)

    assert ap.conversar(ESCENARIO, run, 1, simulador, 0, 5, turno=turno)["logrado"] is True
    assert codigos == []


def test_dos_fallas_de_infraestructura_cierran_como_infra(run, monkeypatch):
    monkeypatch.setattr(ap, "ESPERA_INFRA_S", 0)
    simulador = SimuladorFalso(json.dumps({"accion": "escribir", "mensaje": "hola"}))

    def turno(*_):
        return _reg("error"), chat.CODIGO_INFRA

    cierre = ap.conversar(ESCENARIO, run, 1, simulador, 0, 5, turno=turno)
    assert cierre["resultado"].startswith("infra") and cierre["logrado"] is False


def test_sin_json_valido_dos_veces_termina(run):
    simulador = SimuladorFalso("no se", "tampoco")
    cierre = ap.conversar(ESCENARIO, run, 1, simulador, 0, 5, turno=lambda *_: (_reg("x"), 0))
    assert cierre["resultado"].startswith("abandoné") and cierre["logrado"] is False


def test_el_limite_de_turnos_corta_la_conversacion(run):
    simulador = SimuladorFalso(*[json.dumps({"accion": "escribir", "mensaje": "otra"})] * 3)
    cierre = ap.conversar(ESCENARIO, run, 1, simulador, 0, 2, turno=lambda *_: (_reg("x"), 0))
    assert cierre["resultado"] == "abandoné: límite de turnos"
