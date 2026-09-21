"""Los mensajes de esta tool: lo que pregunta y cómo se le muestra el dictamen al
operario (la plantilla del tipo de respuesta `dictamen` cuando la evaluación trae
veredicto; sin él, la forma es la de `evaluar_riesgo`)."""

from fitosanitarios.dominio.modelos import Cita, RespuestaAgente, ResultadoTool
from fitosanitarios.servicios.formato import (
    SEGUIMIENTO_COMPLETO,
    SEGUIMIENTO_SOLO_INFO,
    bloque_condiciones,
    bloque_no_verificado,
    citas_no_mostradas_inline,
    primer_dato,
    seccion_fuentes,
    unir_secciones,
)

_ICONO_DICTAMEN = {"APTA": "✅", "OBSERVADA": "❌", "NO_EVALUABLE": "⚠️"}


def motivo_producto_ambiguo(nombre: str) -> str:
    return f"'{nombre}' es ambiguo, coincide con varios productos"


def pregunta_producto_ambiguo(nombre: str) -> str:
    return f"Hay varios productos parecidos a '{nombre}'. ¿Cuál es?"


def resumen_para_llm(resultado_dictamen: str) -> str:
    return f"evaluar_viabilidad_legal: {resultado_dictamen}"


def plantilla_dictamen(respuesta: RespuestaAgente, resultados: list[ResultadoTool]) -> str:
    datos = primer_dato(resultados) or {}
    dictamen = datos.get("dictamen") or {}
    resultado = dictamen.get("resultado", "NO_EVALUABLE")
    condiciones = dictamen.get("condiciones")
    lugar = (condiciones or {}).get("localidad") or datos.get("jurisdiccion_id", "")
    icono = _ICONO_DICTAMEN.get(resultado, "⚠️")

    titulo = f"*Dictamen*{' — ' + lugar if lugar else ''}"
    encabezado = f"{titulo}\n*Resultado:* {icono} {resultado}"

    observaciones = dictamen.get("observaciones", [])
    bloque_observaciones = ""
    if observaciones:
        lineas = ["*Observaciones*"]
        lineas += [f"{i}. {o['descripcion']}" for i, o in enumerate(observaciones, start=1)]
        bloque_observaciones = "\n".join(lineas)

    citas = [Cita.model_validate(c) for c in dictamen.get("citas", [])]
    seguimiento = ""
    if condiciones:
        # Una receta observada no se ofrece para agendar.
        seguimiento = SEGUIMIENTO_SOLO_INFO if resultado == "OBSERVADA" else SEGUIMIENTO_COMPLETO
    return unir_secciones(
        encabezado, bloque_observaciones,
        bloque_no_verificado(dictamen.get("chequeos_no_realizados", [])),
        bloque_condiciones(condiciones),
        seccion_fuentes(citas_no_mostradas_inline(citas, condiciones)),
        seguimiento,
    )
