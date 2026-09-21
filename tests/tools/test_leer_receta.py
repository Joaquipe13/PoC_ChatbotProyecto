"""Tests de la tool `leer_receta` con LLM fake (sin red, ver skill: "Los tests
nunca salen a la red"). Casos exigidos por plandefases.md Fase 4: receta
completa (ok), receta con campos faltantes (faltan_datos con CampoFaltante
correctos), imagen no legible (no_resuelto con IMAGEN_ILEGIBLE)."""

import base64
import json

from fitosanitarios.dominio.motivos import MotivoNoResuelto
from fitosanitarios.llm.fake import ClienteLLMFake
from fitosanitarios.tools.leer_receta import LeerRecetaArgs, leer_receta, leer_receta_logica

RESPUESTA_COMPLETA = json.dumps(
    {
        "legible": True,
        "numero": "0042",
        "cultivo": "Soja",
        "confianza_cultivo": 0.95,
        "lote": "4",
        "confianza_lote": 0.9,
        "adversidad": "Malezas de hoja ancha",
        "productos": [
            {"producto_nombre": "Glifosato 48%", "dosis_declarada": "2 L/ha", "confianza": 0.9}
        ],
        "superficie_ha": 35.0,
        "confianza_superficie_ha": 0.9,
        "tipo_aplicacion": "terrestre",
    }
)

RESPUESTA_CON_FALTANTES = json.dumps(
    {
        "legible": True,
        "cultivo": "Algodon",
        "confianza_cultivo": 0.9,
        "lote": None,
        "confianza_lote": 0.0,
        "adversidad": None,
        "productos": [
            {"producto_nombre": "Acefato 75%", "dosis_declarada": "0,5 kg/ha", "confianza": 0.9}
        ],
        "superficie_ha": None,
        "confianza_superficie_ha": 0.0,
        "tipo_aplicacion": None,
    }
)


def test_receta_completa_devuelve_ok():
    fake = ClienteLLMFake(respuestas=[RESPUESTA_COMPLETA])

    resultado = leer_receta_logica(b"imagen-fake", fake)

    assert resultado.estado == "ok"
    assert resultado.faltantes == []
    assert resultado.datos["cultivo"] == "Soja"
    assert len(resultado.datos["items"]) == 1


def test_receta_con_campos_faltantes_devuelve_faltan_datos():
    fake = ClienteLLMFake(respuestas=[RESPUESTA_CON_FALTANTES])

    resultado = leer_receta_logica(b"imagen-fake", fake)

    assert resultado.estado == "faltan_datos"
    campos = {f.campo for f in resultado.faltantes}
    # tipo_aplicacion y adversidad son descriptivos/opcionales (ver
    # DECISIONES.md): ausentes no generan CampoFaltante, la receta se arma
    # igual sin ellos.
    assert campos == {"lote", "superficie_ha"}
    # Los datos parciales que sí se leyeron no se pierden
    assert resultado.datos["cultivo"] == "Algodon"
    assert resultado.datos["tipo_aplicacion"] is None
    assert resultado.datos["adversidad"] is None
    assert len(resultado.datos["items"]) == 1


def test_imagen_no_legible_devuelve_no_resuelto_con_motivo():
    fake = ClienteLLMFake(respuestas=[json.dumps({"legible": False})])

    resultado = leer_receta_logica(b"imagen-fake", fake)

    assert resultado.estado == "no_resuelto"
    assert resultado.motivo == MotivoNoResuelto.IMAGEN_ILEGIBLE
    assert resultado.datos is None


def test_respuesta_no_json_tambien_es_no_resuelto():
    fake = ClienteLLMFake(respuestas=["no soy JSON"])

    resultado = leer_receta_logica(b"imagen-fake", fake)

    assert resultado.estado == "no_resuelto"
    assert resultado.motivo == MotivoNoResuelto.IMAGEN_ILEGIBLE


# --- La tool decorada (schema y forma content_and_artifact) ---


def test_args_schema_requiere_imagen_base64():
    args = LeerRecetaArgs(imagen_base64="ZmFrZQ==")
    assert args.imagen_base64 == "ZmFrZQ=="


def test_tool_decorada_tiene_metadata_correcta():
    assert leer_receta.name == "leer_receta"
    assert leer_receta.args_schema is LeerRecetaArgs
    assert leer_receta.response_format == "content_and_artifact"


def test_base64_decodifica_a_los_mismos_bytes():
    original = b"contenido de imagen de prueba"
    codificado = base64.b64encode(original).decode()
    assert base64.b64decode(codificado) == original


# --- lo que ve el agente ---


def test_el_agente_recibe_los_datos_leidos_y_la_localidad():
    """Bug real: el LLM del agente solo veía "Receta leída correctamente" y
    completaba cultivo, producto, dosis y localidad por su cuenta (una receta de
    María Susana se evaluó como "Pergamino")."""
    from fitosanitarios.tools.leer_receta import _resumen_para_llm

    respuesta = json.loads(RESPUESTA_COMPLETA) | {"localidad": "María Susana"}
    resultado = leer_receta_logica(b"img", ClienteLLMFake(respuestas=[json.dumps(respuesta)]))
    assert resultado.datos["localidad"] == "María Susana"
    resumen = _resumen_para_llm(resultado)
    for dato in ("cultivo=Soja", "localidad=María Susana", "Glifosato 48% (dosis: 2 L/ha)",
                 "tipo_aplicacion=terrestre", "superficie_ha=35"):
        assert dato in resumen


def test_un_dato_que_no_figura_se_le_marca_al_agente_para_que_no_lo_invente():
    from fitosanitarios.tools.leer_receta import _resumen_para_llm

    resultado = leer_receta_logica(b"img", ClienteLLMFake(respuestas=[RESPUESTA_COMPLETA]))
    assert "localidad=NO FIGURA" in _resumen_para_llm(resultado)
