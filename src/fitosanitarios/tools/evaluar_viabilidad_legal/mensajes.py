"""Los mensajes de esta tool: lo que pregunta y cómo se le muestra el dictamen al
operario (la plantilla del tipo de respuesta `dictamen` cuando la evaluación trae
veredicto; sin él, la forma es la de `evaluar_riesgo`)."""

from fitosanitarios.dominio.modelos import CampoFaltante, Cita, RespuestaAgente, ResultadoTool
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


MOTIVO_SIN_CONFIRMAR = "la receta leída de la foto todavía no fue confirmada"
PREGUNTA_CONFIRMAR = "Antes de evaluar: ¿confirmás que los datos de la receta son correctos?"


def faltante_confirmacion() -> CampoFaltante:
    """Se pide la confirmación con los mismos botones con que se mostró la receta."""
    return CampoFaltante(
        campo="confirmacion", motivo=MOTIVO_SIN_CONFIRMAR, pregunta_sugerida=PREGUNTA_CONFIRMAR,
        tipo_entrada="botones", opciones=["Confirmar", "Corregir"],
    )


def resumen_para_llm(resultado: ResultadoTool, resultado_dictamen: str) -> str:
    """Lo que ve el LLM de la tool. Si pidió un dato, se lo dice para que se lo pregunte al
    operario en vez de volver a llamarla."""
    texto = f"evaluar_viabilidad_legal: {resultado_dictamen}"
    if resultado.faltantes:
        campos = ", ".join(f.campo for f in resultado.faltantes)
        texto += (
            f". Falta: {campos}. Preguntáselo al operario y no vuelvas a llamar la tool "
            "hasta que responda"
        )
    return texto


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
