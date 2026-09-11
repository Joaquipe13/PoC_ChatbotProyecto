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
        "confianza_adversidad": 0.9,
        "productos": [
            {"producto_nombre": "Glifosato 48%", "dosis_declarada": "2 L/ha", "confianza": 0.9}
        ],
        "superficie_ha": 35.0,
        "confianza_superficie_ha": 0.9,
        "tipo_aplicacion": "terrestre",
        "confianza_tipo_aplicacion": 0.9,
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
        "confianza_adversidad": 0.0,
        "productos": [
            {"producto_nombre": "Acefato 75%", "dosis_declarada": "0,5 kg/ha", "confianza": 0.9}
        ],
        "superficie_ha": None,
        "confianza_superficie_ha": 0.0,
        "tipo_aplicacion": None,
        "confianza_tipo_aplicacion": 0.0,
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
    assert campos == {"lote", "adversidad", "superficie_ha", "tipo_aplicacion"}
    # Los datos parciales que sí se leyeron no se pierden
    assert resultado.datos["cultivo"] == "Algodon"
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
