"""Los tipos propios que quedan en el checkpoint se recuperan sin depender del modo
permisivo de LangGraph, que avisa que una versión futura los va a bloquear."""

import logging

from fitosanitarios.dominio.modelos import CampoFaltante, RespuestaAgente
from fitosanitarios.dominio.motivos import MotivoNoResuelto
from fitosanitarios.orquestador.agente import serializador_checkpoint


def test_la_respuesta_y_el_motivo_vuelven_del_checkpoint_sin_avisos(caplog):
    respuesta = RespuestaAgente(
        tipo="repregunta",
        faltantes=[CampoFaltante(
            campo="localidad", motivo="falta", pregunta_sugerida="¿Dónde?", tipo_entrada="texto",
        )],
    )
    valor = {"structured_response": respuesta, "motivo": MotivoNoResuelto.SIN_REGLA_APLICABLE}
    serde = serializador_checkpoint()
    with caplog.at_level(logging.WARNING, logger="langgraph"):
        recuperado = serde.loads_typed(serde.dumps_typed(valor))
    assert recuperado == valor
    assert isinstance(recuperado["structured_response"], RespuestaAgente)
    assert isinstance(recuperado["motivo"], MotivoNoResuelto)
    avisos = [r.getMessage() for r in caplog.records]
    assert not [a for a in avisos if "unregistered" in a or "blocked" in a.lower()]
