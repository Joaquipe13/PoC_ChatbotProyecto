"""Ruteo de las consultas de normativa sin base: el agente (con un modelo simulado
que "decide" llamar la tool), la tool real y el formateador, con los accesos a
datos reemplazados. Lo que se prueba es la cañería (esquema de la tool, artifact,
plantilla), no la interpretación del LLM: eso, con frases mal escritas, hay que
probarlo con el modelo real."""

import pytest

from fitosanitarios.orquestador.agente import crear_agente
from fitosanitarios.orquestador.estado import ContadorRepreguntas
from fitosanitarios.orquestador.turno import ejecutar_turno
from fitosanitarios.servicios.localidad import Jurisdiccion, Ubicacion
from fitosanitarios.servicios.reglas import ReglaCandidata
from fitosanitarios.tools import _recursos
from fitosanitarios.tools import consultar_articulo as mod_articulo
from fitosanitarios.tools import listar_limitaciones as mod_limitaciones
from tests.orquestador.fake_chat_model import (
    ChatModelFake,
    mensaje_llama_tool,
    mensaje_respuesta_estructurada,
)

UBICACION = Ubicacion(
    nombre="El Trébol", provincia_id=1, localidad_id=1, jurisdiccion_id="el-trebol",
    con_normativa_municipal=True,
)


@pytest.fixture(autouse=True)
def sin_base(monkeypatch):
    monkeypatch.setattr(_recursos, "con_conexion", lambda f: f(None))
    for modulo in (mod_articulo, mod_limitaciones):
        monkeypatch.setattr(
            modulo, "resolver_ubicacion_o_cortar", lambda c, t, p=None: (UBICACION, None)
        )
    monkeypatch.setattr(
        mod_articulo, "listar_provincias",
        lambda c: [
            Jurisdiccion(id=1, jurisdiccion_id="santa-fe", nombre="Santa Fe", provincia_id=1)
        ],
    )
    monkeypatch.setattr(mod_articulo, "normas_de_alcance", lambda c, loc, prov: [])
    monkeypatch.setattr(
        mod_articulo, "articulos_por_numero",
        lambda c, numero, loc, prov: [{
            "id": 1, "numero": "33", "pagina": 1, "requiere_revision": False,
            "archivo": "ley-11273-1995", "ambito": "provincial", "jurisdiccion_id": "santa-fe",
            "texto": "Prohíbese la aplicación aérea\ndentro de 3.000 metros.",
        }] if numero == "33" else [],
    )

    def reglas(conn, localidad_id, provincia_id, permitido=False):
        if permitido:
            return []
        return [ReglaCandidata(
            tipo_zona="zona_urbana", tipo_aplicacion="aerea", bandas=["Ia", "Ib", "II"],
            distancia_min_m=3000, norma="ley-11273-1995", articulo="33",
            jurisdiccion_id=None,
        )]

    monkeypatch.setattr(mod_limitaciones, "reglas_candidatas", reglas)


def _turno(respuestas):
    agente = crear_agente(ChatModelFake(respuestas=respuestas))
    return ejecutar_turno(agente, "t-normativa", "mensaje", ContadorRepreguntas())


def test_que_dice_el_articulo_33():
    respuesta, mensajes = _turno([
        mensaje_llama_tool("consultar_articulo", {"numero_articulo": "33"}),
        mensaje_respuesta_estructurada({"tipo": "consulta_articulo"}),
    ])
    assert respuesta.tipo == "consulta_articulo"
    assert mensajes[0].startswith("*Ley 11273/1995, art. 33 (santa-fe)*\n")
    assert "Prohíbese la aplicación aérea dentro de 3.000 metros." in mensajes[0]


def test_articulo_que_no_existe_responde_que_no_lo_encontro():
    respuesta, mensajes = _turno([
        mensaje_llama_tool("consultar_articulo", {"numero_articulo": "999"}),
        mensaje_respuesta_estructurada({"tipo": "consulta_articulo"}),
    ])
    assert "No pude completar la consulta" in mensajes[0]
    assert "No hay un artículo con ese número" in mensajes[0]


def test_que_limitaciones_hay_en_la_localidad():
    respuesta, mensajes = _turno([
        mensaje_llama_tool("listar_limitaciones", {"localidad": "el trebol"}),
        mensaje_respuesta_estructurada({"tipo": "limitaciones"}),
    ])
    assert respuesta.tipo == "limitaciones"
    assert "*Limitaciones en El Trébol*" in mensajes[0]
    assert "a menos de 3000 m no se puede aplicar (Ley 11273/1995, art. 33)" in mensajes[0]


def test_puedo_aplicar_a_1000_metros():
    respuesta, mensajes = _turno([
        mensaje_llama_tool(
            "listar_limitaciones",
            {"localidad": "El Trébol", "distancia_m": 1000, "tipo_aplicacion": "aerea"},
        ),
        mensaje_respuesta_estructurada({"tipo": "limitaciones"}),
    ])
    assert mensajes[0].startswith("*A 1000 m en El Trébol*")
    assert "No hay excepciones cargadas para esa distancia." in mensajes[0]


def test_si_el_llm_elige_otro_tipo_igual_se_formatea_lo_que_devolvio_la_tool_que_repregunta(
    monkeypatch,
):
    from fitosanitarios.dominio.modelos import CampoFaltante, ResultadoTool

    pedir = ResultadoTool(estado="faltan_datos", faltantes=[CampoFaltante(
        campo="localidad", motivo="falta", pregunta_sugerida="¿En qué localidad se aplica?",
        tipo_entrada="texto",
    )])
    monkeypatch.setattr(
        mod_limitaciones, "resolver_ubicacion_o_cortar", lambda c, t, p=None: (None, pedir)
    )
    _, mensajes = _turno([
        mensaje_llama_tool("listar_limitaciones", {}),
        mensaje_respuesta_estructurada({"tipo": "limitaciones"}),
    ])
    assert mensajes == ["¿En qué localidad se aplica?"]
