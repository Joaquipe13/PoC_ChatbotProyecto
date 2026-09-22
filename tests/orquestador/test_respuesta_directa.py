"""Turnos que terminan en la tool, sin segunda llamada al modelo (ver `respuesta_directa.py`)."""

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from fitosanitarios.dominio.modelos import CampoFaltante, ResultadoTool
from fitosanitarios.orquestador.agente import TOOLS, construir_tools, crear_agente
from fitosanitarios.orquestador.estado import ContadorRepreguntas
from fitosanitarios.orquestador.respuesta_directa import TIPO_POR_TOOL, respuesta_de_las_tools
from fitosanitarios.orquestador.turno import ejecutar_turno
from fitosanitarios.servicios import recursos
from fitosanitarios.tools.evaluar_viabilidad_legal import tool as modulo
from tests.orquestador.fake_chat_model import (
    ChatModelFake,
    mensaje_llama_tool,
    mensaje_respuesta_estructurada,
)

OK = ResultadoTool(estado="ok", datos={"dictamen": {"resultado": "APTA", "condiciones": None}})
PIDE_PROVINCIA = ResultadoTool(estado="faltan_datos", faltantes=[CampoFaltante(
    campo="provincia", motivo="sin normativa", pregunta_sugerida="¿En qué provincia queda?",
    tipo_entrada="texto",
)])


# --- el tipo que se infiere ---


@pytest.mark.parametrize("tool,tipo", list(TIPO_POR_TOOL.items()))
def test_cada_tool_tiene_su_tipo(tool, tipo):
    assert respuesta_de_las_tools([tool], [OK]).tipo == tipo


def test_una_tool_que_pide_un_dato_da_una_repregunta():
    respuesta = respuesta_de_las_tools(["evaluar_viabilidad_legal"], [PIDE_PROVINCIA])
    assert respuesta.tipo == "repregunta"


def test_agendar_sin_hora_conserva_su_tipo_porque_su_plantilla_muestra_la_agenda():
    assert respuesta_de_las_tools(["agendar_aplicacion"], [PIDE_PROVINCIA]).tipo == (
        "agendar_aplicacion"
    )


def test_un_producto_no_encontrado_es_no_resuelto():
    no_encontrado = ResultadoTool(estado="no_resuelto", motivo="producto_no_encontrado")
    assert respuesta_de_las_tools(["validar_producto_registro"], [no_encontrado]).tipo == (
        "no_resuelto"
    )


def test_sin_resultados_no_se_puede_inferir():
    assert respuesta_de_las_tools([], []) is None


def test_una_tool_que_no_corta_el_turno_no_se_infiere():
    assert respuesta_de_las_tools(["evaluar_riesgo"], [OK]) is None


def test_las_tools_que_cortan_son_las_que_tienen_tipo_y_solo_esas():
    """`return_direct` de cada tool y `TIPO_POR_TOOL` no pueden desincronizarse."""
    for t in [*TOOLS, *construir_tools("aW1n")]:
        assert t.return_direct == (t.name in TIPO_POR_TOOL), t.name
    assert {t.name for t in TOOLS if not t.return_direct} == {"evaluar_riesgo", "resolver_vehiculo"}


# --- con el agente completo (modelo simulado) ---


@pytest.fixture
def evaluaciones(monkeypatch):
    llamadas: list[dict] = []

    def logica(args, conn, modelo, tolerancia):
        llamadas.append(args.model_dump())
        return OK

    monkeypatch.setattr(modulo, "evaluar_viabilidad_legal_logica", logica)
    monkeypatch.setattr(recursos, "con_conexion_y_modelo", lambda f: f(None, None))
    return llamadas


ARGS = {
    "tipo_aplicacion": "aerea", "cultivo": "soja", "localidad": "El Trébol",
    "productos": [{"nombre": "Flyer 10 Ec", "dosis_valor": 170, "dosis_unidad": "cm3/ha"}],
}


def _turno(respuestas):
    modelo = ChatModelFake(respuestas=respuestas)
    agente = crear_agente(modelo, checkpointer=InMemorySaver())
    contador = ContadorRepreguntas()
    return modelo, lambda texto: ejecutar_turno(agente, "t-directa", texto, contador)


def test_un_turno_con_tool_llama_una_sola_vez_al_modelo(evaluaciones):
    modelo, turno = _turno([mensaje_llama_tool("evaluar_viabilidad_legal", ARGS)])
    respuesta, mensajes = turno("evaluá esto")

    assert len(modelo.llamadas) == 1
    assert respuesta.tipo == "dictamen" and "APTA" in mensajes[0]


def test_un_turno_sin_tool_sigue_respondiendo_con_el_tipo_del_modelo():
    modelo, turno = _turno([mensaje_respuesta_estructurada({"tipo": "fuera_de_dominio"})])
    respuesta, mensajes = turno("¿va a llover?")
    assert respuesta.tipo == "fuera_de_dominio" and mensajes


def test_si_la_tool_rechaza_los_argumentos_el_modelo_vuelve_a_decidir(evaluaciones):
    """Sin `cultivo` la validación falla antes de que la tool devuelva algo: el modelo ve el
    error y decide (acá, preguntarlo), como antes de que las tools cortaran el turno."""
    sin_cultivo = {k: v for k, v in ARGS.items() if k != "cultivo"}
    pregunta = {"tipo": "repregunta", "faltantes": [{
        "campo": "cultivo", "motivo": "falta", "pregunta_sugerida": "¿Qué cultivo es?",
        "tipo_entrada": "texto",
    }]}
    modelo, turno = _turno([
        mensaje_llama_tool("evaluar_viabilidad_legal", sin_cultivo),
        mensaje_respuesta_estructurada(pregunta),
    ])
    respuesta, mensajes = turno("evaluá Flyer en El Trébol")

    assert evaluaciones == []
    assert len(modelo.llamadas) == 2
    assert respuesta.tipo == "repregunta" and "¿Qué cultivo es?" in mensajes[0]


def test_si_reintenta_con_los_argumentos_corregidos_se_muestra_el_resultado(evaluaciones):
    sin_cultivo = {k: v for k, v in ARGS.items() if k != "cultivo"}
    _, turno = _turno([
        mensaje_llama_tool("evaluar_viabilidad_legal", sin_cultivo, "c1"),
        mensaje_llama_tool("evaluar_viabilidad_legal", ARGS, "c2"),
    ])
    respuesta, mensajes = turno("evaluá Flyer en El Trébol")
    assert len(evaluaciones) == 1
    assert respuesta.tipo == "dictamen" and "APTA" in mensajes[0]
