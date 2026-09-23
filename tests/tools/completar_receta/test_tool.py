"""`completar_receta` y el flujo de una receta de foto con datos obligatorios faltantes
(pedido del usuario, 23/09/2026): se pregunta lo que falta, el operario lo da, se muestra
la receta completa para confirmar y recién entonces se evalúa. Sin base ni red."""

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from fitosanitarios.dominio.modelos import ResultadoTool
from fitosanitarios.orquestador.agente import crear_agente
from fitosanitarios.orquestador.estado import ContadorRepreguntas
from fitosanitarios.orquestador.turno import ejecutar_turno
from fitosanitarios.servicios import recursos
from fitosanitarios.servicios.receta import faltantes_de_receta
from fitosanitarios.tools.completar_receta import (
    CompletarRecetaArgs,
    DosisDeProducto,
    completar_receta_logica,
)
from fitosanitarios.tools.evaluar_viabilidad_legal import tool as modulo_evaluar
from fitosanitarios.tools.leer_receta import tool as modulo_leer
from tests.orquestador.fake_chat_model import ChatModelFake, mensaje_llama_tool

# La receta 1001 del 23/09/2026, tal como la leyó la foto: sin cultivo ni localidad.
RECETA_1001 = {
    "numero": "1001", "cultivo": None, "lote": "8", "localidad": None,
    "adversidad": "Chinche de la alfalfa", "superficie_ha": 40.0,
    "items": [{"producto_nombre": "Flyer 10 Ec", "dosis_declarada": "170 cm3/ha"}],
    "tipo_aplicacion": "terrestre",
}


def test_completa_lo_que_faltaba_y_conserva_lo_leido():
    resultado = completar_receta_logica(
        CompletarRecetaArgs(cultivo="Soja", localidad="Sastre"), RECETA_1001
    )
    assert resultado.estado == "ok" and resultado.faltantes == []
    datos = resultado.datos
    assert (datos["cultivo"], datos["localidad"], datos["lote"]) == ("Soja", "Sastre", "8")
    assert datos["items"][0]["dosis_declarada"] == "170 cm3/ha"


def test_si_todavia_falta_algo_lo_sigue_preguntando():
    resultado = completar_receta_logica(CompletarRecetaArgs(cultivo="Soja"), RECETA_1001)
    assert resultado.estado == "faltan_datos"
    assert [f.campo for f in resultado.faltantes] == ["localidad"]


def test_corrige_la_dosis_del_producto_nombrado_y_el_tipo_de_aplicacion():
    receta = {**RECETA_1001, "cultivo": "Soja", "localidad": "Sastre"}
    resultado = completar_receta_logica(
        CompletarRecetaArgs(
            tipo_aplicacion="aérea", dosis=[DosisDeProducto(producto="flyer", dosis="200 cc/ha")]
        ),
        receta,
    )
    assert resultado.datos["tipo_aplicacion"] == "aerea"
    assert resultado.datos["items"][0]["dosis_declarada"] == "200 cc/ha"


def test_no_pisa_un_dato_con_no_figura():
    receta = {**RECETA_1001, "cultivo": "Soja", "localidad": "Sastre"}
    resultado = completar_receta_logica(CompletarRecetaArgs(cultivo="NO FIGURA"), receta)
    assert resultado.datos["cultivo"] == "Soja"


def test_sin_receta_leida_pide_la_foto():
    resultado = completar_receta_logica(CompletarRecetaArgs(cultivo="Soja"), None)
    assert resultado.estado == "faltan_datos" and not resultado.datos
    assert resultado.faltantes[0].tipo_entrada == "imagen"


# --- el flujo completo, con el agente y un modelo simulado ---

ARGS_EVALUAR = {
    "tipo_aplicacion": "terrestre", "cultivo": "Soja", "localidad": "Sastre",
    "productos": [{"nombre": "Flyer 10 Ec", "dosis_valor": 170, "dosis_unidad": "cm3/ha"}],
}


@pytest.fixture
def evaluaciones(monkeypatch):
    """La foto se "lee" como la receta 1001 y se cuentan las evaluaciones de verdad."""
    leida = ResultadoTool(
        estado="faltan_datos", datos=RECETA_1001, faltantes=faltantes_de_receta(RECETA_1001)
    )
    monkeypatch.setattr(modulo_leer, "leer_receta_logica", lambda imagen, cliente: leida)
    monkeypatch.setattr("fitosanitarios.llm.client.crear_cliente_llm", lambda settings: None)

    llamadas: list[dict] = []

    def evaluar(args, conn, modelo, tolerancia):
        llamadas.append(args.model_dump())
        return ResultadoTool(
            estado="ok", datos={"dictamen": {"resultado": "APTA", "condiciones": None}}
        )

    monkeypatch.setattr(modulo_evaluar, "evaluar_viabilidad_legal_logica", evaluar)
    monkeypatch.setattr(recursos, "con_conexion_y_modelo", lambda f: f(None, None))
    return llamadas


def _conversacion(respuestas_del_modelo):
    agente = crear_agente(ChatModelFake(respuestas=respuestas_del_modelo),
                          checkpointer=InMemorySaver())
    contador = ContadorRepreguntas()
    return lambda texto: ejecutar_turno(agente, "t-completar", texto, contador)


def test_faltan_datos_se_preguntan_se_completan_se_confirman_y_se_evalua(evaluaciones):
    turno = _conversacion([
        mensaje_llama_tool("leer_receta", {"imagen_base64": "eA=="}, "c1"),
        mensaje_llama_tool("completar_receta", {"cultivo": "Soja", "localidad": "Sastre"}, "c2"),
        mensaje_llama_tool("evaluar_viabilidad_legal", ARGS_EVALUAR, "c3"),
    ])

    respuesta, mensajes = turno("Te mando la foto de mi receta.")
    assert respuesta.tipo == "confirmacion_receta"
    assert "Falta la siguiente información obligatoria" in mensajes[0]
    assert "[Confirmar]" not in mensajes[0]

    respuesta, mensajes = turno("soja, en Sastre")
    assert respuesta.tipo == "confirmacion_receta"
    assert "- *Cultivo:* Soja\n- *Lote:* 8\n- *Localidad:* Sastre" in mensajes[0]
    assert mensajes[0].endswith("[Confirmar] [Corregir]")
    assert evaluaciones == []

    respuesta, mensajes = turno("Confirmar")
    assert len(evaluaciones) == 1 and "APTA" in mensajes[0]


def test_confirmar_sin_haber_dado_lo_que_falta_no_evalua_con_no_figura(evaluaciones):
    """Lo que pasó el 23/09/2026: el LLM evaluó con "NO FIGURA" como cultivo y localidad."""
    turno = _conversacion([
        mensaje_llama_tool("leer_receta", {"imagen_base64": "eA=="}, "c1"),
        mensaje_llama_tool(
            "evaluar_viabilidad_legal",
            {**ARGS_EVALUAR, "cultivo": "NO FIGURA", "localidad": "NO FIGURA"}, "c2",
        ),
    ])
    turno("Te mando la foto de mi receta.")
    respuesta, mensajes = turno("Confirmar")

    assert evaluaciones == []
    assert respuesta.tipo == "repregunta"
    assert "¿Qué cultivo es?" in mensajes[0] and "¿En qué localidad se aplica?" in mensajes[0]
