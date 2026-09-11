"""Tests de ruteo: para cada una de las 6 tools y el caso "ninguna tool",
verifica que el agente arma la llamada correcta y que el turno completo
(tool real + formateador) no rompe. Requiere Postgres real (Docker) porque
las tools ejecutan de verdad contra la base -- ver skill: "las tools...
llaman servicios y devuelven ResultadoTool", eso es justo lo que se está
probando acá, no solo que el LLM "decida" llamar una.
"""

from fitosanitarios.orquestador.agente import crear_agente
from fitosanitarios.orquestador.estado import ContadorRepreguntas
from fitosanitarios.orquestador.turno import ejecutar_turno
from tests.orquestador.fake_chat_model import (
    ChatModelFake,
    mensaje_llama_tool,
    mensaje_respuesta_estructurada,
)

LAT_SAN_CARLOS, LON_SAN_CARLOS = -32.912, -60.642  # lejos de zonas protegidas


def _turno_con_respuestas(respuestas, mensaje="mensaje de prueba", thread_id="t-ruteo"):
    modelo = ChatModelFake(respuestas=respuestas)
    agente = crear_agente(modelo)
    contador = ContadorRepreguntas()
    respuesta, mensajes = ejecutar_turno(agente, thread_id, mensaje, contador)
    return respuesta, mensajes, modelo


def test_ruteo_validar_producto_registro(conexion):
    respuesta, mensajes, _ = _turno_con_respuestas([
        mensaje_llama_tool(
            "validar_producto_registro", {"producto_nombre": "Flyer 10 Ec", "cultivo": "Soja"}
        ),
        mensaje_respuesta_estructurada({"tipo": "consulta_producto"}),
    ])
    assert respuesta.tipo == "consulta_producto"
    assert "Flyer 10 Ec" in mensajes[0]


def test_ruteo_consultar_productos(conexion):
    respuesta, mensajes, _ = _turno_con_respuestas([
        mensaje_llama_tool("consultar_productos", {"cultivo": "Soja"}),
        mensaje_respuesta_estructurada({"tipo": "consulta_producto"}),
    ])
    assert respuesta.tipo == "consulta_producto"
    assert "Productos registrados" in mensajes[0]


def test_ruteo_evaluar_riesgo(conexion):
    respuesta, mensajes, _ = _turno_con_respuestas([
        mensaje_llama_tool("evaluar_riesgo", {
            "lat": LAT_SAN_CARLOS, "lon": LON_SAN_CARLOS, "tipo_aplicacion": "terrestre",
            "productos": ["Flyer 10 Ec"], "cultivo": "Soja",
            "dosis_valor": 170, "dosis_unidad": "cm³/ha",
        }),
        mensaje_respuesta_estructurada({"tipo": "dictamen", "intro": "Riesgo evaluado."}),
    ])
    assert respuesta.tipo == "dictamen"


def test_ruteo_evaluar_viabilidad_legal(conexion):
    # "adversidad" explícita: sin ella, "Flyer 10 Ec" en soja tiene rangos
    # de dosis distintos por adversidad y la dosis queda sin verificar por
    # ambigüedad (ver servicios/validacion_producto.py, hallazgo de esta
    # misma fase, DECISIONES.md).
    respuesta, mensajes, _ = _turno_con_respuestas([
        mensaje_llama_tool("evaluar_viabilidad_legal", {
            "lat": LAT_SAN_CARLOS, "lon": LON_SAN_CARLOS, "tipo_aplicacion": "terrestre",
            "productos": [{"nombre": "Flyer 10 Ec", "dosis_valor": 170, "dosis_unidad": "cm³/ha"}],
            "cultivo": "Soja", "adversidad": "Chinche De La Alfalfa",
        }),
        mensaje_respuesta_estructurada({"tipo": "dictamen"}),
    ])
    assert respuesta.tipo == "dictamen"
    assert "Dictamen" in mensajes[0]
    assert "APTA" in mensajes[0]  # lejos de zonas protegidas, dosis en rango


def test_ruteo_responder_consulta_normativa(conexion):
    respuesta, mensajes, _ = _turno_con_respuestas([
        mensaje_llama_tool("responder_consulta_normativa", {
            "pregunta": "¿a qué distancia de una escuela puedo aplicar por tierra?",
            "jurisdiccion_id": "san-carlos-centro",
        }),
        mensaje_respuesta_estructurada({"tipo": "consulta_normativa"}),
    ])
    assert respuesta.tipo == "consulta_normativa"


def test_ruteo_leer_receta(conexion):
    import base64

    respuesta, mensajes, _ = _turno_con_respuestas([
        mensaje_llama_tool("leer_receta", {"imagen_base64": base64.b64encode(b"fake").decode()}),
        mensaje_respuesta_estructurada({"tipo": "confirmacion_receta"}),
    ])
    # El contenido exacto depende de si USE_FIXTURES usa el LLM fake o real;
    # lo que importa acá es que la tool corrió (no reventó) y el turno
    # devolvió texto formateado según el tipo que declaró el agente.
    assert respuesta.tipo == "confirmacion_receta"
    assert mensajes


def test_excepcion_al_ejecutar_una_tool_no_rompe_el_turno():
    # Hallazgo real corriendo evals/run_evals.py contra Gemini real: el LLM
    # a veces llama consultar_productos sin ningún filtro (arg inválido
    # según su propio validador) y esa excepción se propagaba sin
    # capturar. Ver DECISIONES.md.
    respuesta, mensajes, _ = _turno_con_respuestas([
        mensaje_llama_tool("consultar_productos", {}),
    ])
    assert respuesta.tipo == "error"
    assert "problema técnico" in mensajes[0]


def test_ruteo_ninguna_tool_responde_directo():
    # Sin DB: no hace falta, no se llama ninguna tool.
    respuesta, mensajes, modelo = _turno_con_respuestas([
        mensaje_respuesta_estructurada({"tipo": "ayuda"}),
    ])
    assert respuesta.tipo == "ayuda"
    assert mensajes[0].startswith("Hola")
    assert len(modelo.llamadas) == 1  # un solo turno de modelo, no tool-calling
