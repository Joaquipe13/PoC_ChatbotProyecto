"""`consultar_marbete` con el retriever y el LLM simulados (sin base ni red): la
verificación de las páginas citadas y los casos sin respaldo."""

import json

import pytest

from fitosanitarios.datos.retrievers.catalogo import CandidatoProducto
from fitosanitarios.dominio.modelos import RespuestaAgente
from fitosanitarios.dominio.motivos import MotivoNoResuelto
from fitosanitarios.llm.fake import ClienteLLMFake
from fitosanitarios.orquestador.formateador import formatear_respuesta
from fitosanitarios.tools.consultar_marbete import ConsultarMarbeteArgs, consultar_marbete_logica
from fitosanitarios.tools.consultar_marbete import tool as modulo

VERTIMEC = CandidatoProducto(
    id=1, numero_inscripcion="30116", marca="Vertimec", banda_toxicologica="II",
    estado_producto="Activo", score=0.9,
)
FRAGMENTOS = [
    {"id": 1, "pagina": 7, "texto": "Carencia: cítricos 7 días.", "score": 0.6,
     "palabras": ["carenci", "citric", "7", "dias"]},
    {"id": 2, "pagina": 2, "texto": "Precauciones generales.", "score": 0.3,
     "palabras": ["precaucion", "general"]},
]


class ModeloFalso:
    def encode(self, texto):
        import numpy as np
        return np.zeros(3)


@pytest.fixture
def retriever(monkeypatch):
    monkeypatch.setattr(modulo, "buscar_productos_por_nombre", lambda c, n, m: [VERTIMEC])
    monkeypatch.setattr(modulo, "fragmentos_de_marbete", lambda c, e, pid: FRAGMENTOS)
    monkeypatch.setattr(modulo, "palabras_de", lambda c, t: ["carenci", "citric"])


def _consultar(respuesta_llm: dict | str, umbral: float = 0.42):
    texto = respuesta_llm if isinstance(respuesta_llm, str) else json.dumps(respuesta_llm)
    return consultar_marbete_logica(
        ConsultarMarbeteArgs(producto="vertimec", pregunta="¿qué carencia tiene en cítricos?"),
        None, ModeloFalso(), ClienteLLMFake(respuestas=[texto]), umbral,
    )


def test_responde_citando_la_pagina_del_marbete(retriever):
    resultado = _consultar({"respuesta": "La carencia en cítricos es de 7 días.",
                            "paginas_citadas": [7]})
    assert resultado.estado == "ok"
    texto = formatear_respuesta(RespuestaAgente(tipo="consulta_marbete"), [resultado])[0]
    assert texto == (
        "*Vertimec* · Reg. SENASA 30116\nLa carencia en cítricos es de 7 días.\n\n"
        "*Fuentes*\n- SENASA, Reg. 30116 (marbete, pág. 7)"
    )


def test_una_pagina_que_no_se_recupero_se_descarta(retriever):
    """La página 2 está en el marbete pero no pasó el umbral: no se le pasó al LLM."""
    resultado = _consultar({"respuesta": "x", "paginas_citadas": [7, 2, 99]})
    assert [c.documento for c in resultado.citas] == ["marbete, pág. 7"]
    assert len(resultado.advertencias) == 2


def test_sin_ninguna_pagina_verificada_no_hay_respuesta(retriever):
    resultado = _consultar({"respuesta": "El marbete no lo dice.", "paginas_citadas": []})
    assert resultado.estado == "no_resuelto"
    assert resultado.motivo == MotivoNoResuelto.MARBETE_SIN_RESPALDO


def test_si_nada_pasa_el_umbral_no_se_llama_al_llm(retriever):
    resultado = _consultar("esto no se llega a leer", umbral=0.9)
    assert resultado.motivo == MotivoNoResuelto.MARBETE_SIN_RESPALDO


def test_producto_no_encontrado(monkeypatch):
    monkeypatch.setattr(modulo, "buscar_productos_por_nombre", lambda c, n, m: [])
    resultado = _consultar({})
    assert resultado.motivo == MotivoNoResuelto.PRODUCTO_NO_ENCONTRADO
