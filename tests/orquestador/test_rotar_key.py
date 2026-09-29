"""Ante un error de cuota de Gemini, el agente repite la llamada con la key siguiente
(`RotarKeyAnteCuota`). Hasta el 28/09/2026 usaba solo la primera: con dos operarios
escribiendo a la vez, turnos que terminaban en "Tuve un problema técnico"."""

import pytest

from fitosanitarios.orquestador.agente import crear_agente
from fitosanitarios.orquestador.estado import ContadorRepreguntas
from fitosanitarios.orquestador.turno import ejecutar_turno
from tests.orquestador.fake_chat_model import ChatModelFake, mensaje_respuesta_estructurada


class ChatModelSinCuota(ChatModelFake):
    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.llamadas.append(list(messages))
        raise RuntimeError("429 RESOURCE_EXHAUSTED. You exceeded your current quota")


class ChatModelRoto(ChatModelFake):
    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        raise ValueError("otro error, no de cuota")


def _turno(principal, respaldo):
    agente = crear_agente(principal, respaldo=respaldo)
    return ejecutar_turno(agente, "t", "hola", ContadorRepreguntas())


def test_sin_cuota_en_la_primera_key_responde_con_la_siguiente():
    principal = ChatModelSinCuota()
    segunda = ChatModelSinCuota()
    tercera = ChatModelFake(respuestas=[mensaje_respuesta_estructurada({"tipo": "ayuda"})])
    respuesta, _ = _turno(principal, [segunda, tercera])
    assert respuesta.tipo == "ayuda"
    assert len(principal.llamadas) == 1 and len(segunda.llamadas) == 1


def test_sin_cuota_en_ninguna_key_es_un_error():
    respuesta, _ = _turno(ChatModelSinCuota(), [ChatModelSinCuota()])
    assert respuesta.tipo == "error"


def test_un_error_que_no_es_de_cuota_no_rota():
    tercera = ChatModelFake(respuestas=[mensaje_respuesta_estructurada({"tipo": "ayuda"})])
    respuesta, _ = _turno(ChatModelRoto(), [tercera])
    assert respuesta.tipo == "error"
    assert tercera.respuestas  # no se la llamó


@pytest.mark.parametrize("respaldo", [None, []])
def test_sin_respaldo_no_hay_middleware_de_rotacion(respaldo):
    agente = crear_agente(ChatModelFake(), respaldo=respaldo)
    assert agente is not None
