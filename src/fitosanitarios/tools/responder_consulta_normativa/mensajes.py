"""Los mensajes de esta tool: lo que pregunta, lo que avisa y cómo se le muestra
la respuesta al operario (la plantilla del tipo de respuesta `consulta_normativa`)."""

from fitosanitarios.dominio.modelos import RespuestaAgente, ResultadoTool
from fitosanitarios.servicios.formato import (
    primer_dato,
    seccion_fuentes,
    todas_las_citas,
    unir_secciones,
)

# --- preguntas y avisos de la tool ---

MOTIVO_SIN_LOCALIDAD = "no se indicó de qué localidad es la consulta"
PREGUNTA_LOCALIDAD = "¿De qué localidad es la consulta?"
_PREFIJO_SIN_NORMATIVA_MUNICIPAL = "No se cuenta con"

REGLA_RESPUESTA_ININTERPRETABLE = "No se pudo interpretar la respuesta del asistente."
ADVERTENCIA_LLM_SIN_JSON = "respuesta del LLM no era JSON válido"


def es_aclaracion_sin_normativa_municipal(texto: str) -> bool:
    """La aclaración de que se respondió con la normativa provincial: se le muestra al
    operario. Las otras advertencias de la tool (citas descartadas) son internas."""
    return texto.startswith(_PREFIJO_SIN_NORMATIVA_MUNICIPAL)


def aclaracion_sin_normativa_municipal(localidad: str) -> str:
    return (
        f"{_PREFIJO_SIN_NORMATIVA_MUNICIPAL} la normativa municipal de {localidad}: la "
        "respuesta se basa en la normativa provincial"
    )


def advertencia_cita_descartada(norma: str | None, articulo: str | None) -> str:
    return (
        f"El asistente citó {norma} art. {articulo}, que no está entre los fragmentos "
        "recuperados; se descartó esa cita."
    )


def resumen_para_llm(estado: str) -> str:
    return f"responder_consulta_normativa: estado={estado}"


# --- plantilla del resultado (tipo de respuesta `consulta_normativa`) ---


def plantilla_consulta_normativa(
    respuesta: RespuestaAgente, resultados: list[ResultadoTool]
) -> str:
    datos = primer_dato(resultados) or {}
    veredicto = datos.get("veredicto", "Depende")
    regla = datos.get("regla", "")
    cuerpo = f"*{veredicto}.* {regla}"
    aclaracion = "\n".join(
        f"⚠️ {a}" for r in resultados for a in r.advertencias
        if es_aclaracion_sin_normativa_municipal(a)
    )
    return unir_secciones(cuerpo, aclaracion, seccion_fuentes(todas_las_citas(resultados)))
