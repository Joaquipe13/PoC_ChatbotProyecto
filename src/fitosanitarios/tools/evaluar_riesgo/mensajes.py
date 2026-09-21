"""Los mensajes de esta tool: lo que avisa que no pudo verificar y cómo se le
muestra el resultado al operario. Dos plantillas: la del riesgo evaluado "suelto"
(sin dictamen; es la forma del tipo de respuesta `dictamen` que no trae
veredicto) y la del detalle de bandas (tipo de respuesta `detalle_bandas`)."""

from fitosanitarios.dominio.modelos import RespuestaAgente, ResultadoTool
from fitosanitarios.servicios.formato import (
    COLOR_BANDA,
    SEGUIMIENTO_COMPLETO,
    bloque_condiciones,
    bloque_no_verificado,
    citas_no_mostradas_inline,
    primer_dato,
    seccion_fuentes,
    todas_las_citas,
    unir_secciones,
)

# --- avisos de lo que no se pudo verificar ---


def no_se_pudo_resolver(producto: str) -> str:
    return f"{producto}: no se pudo resolver contra el registro"


def dosis_requiere_volumen_de_caldo(marca: str) -> str:
    return f"{marca}: dosis por 100 L requiere volumen de caldo por hectárea"


def dosis_no_comparable(marca: str, motivo: str) -> str:
    return f"{marca}: dosis no comparable ({motivo})"


def banda_no_figura(producto: str) -> str:
    return (
        f"{producto}: no figura su banda toxicológica en SENASA; la de la aplicación "
        "podría ser más restrictiva"
    )


def resumen_para_llm(estado: str) -> str:
    return f"evaluar_riesgo: estado={estado}"


# --- plantillas del resultado ---


def plantilla_riesgo(respuesta: RespuestaAgente, resultados: list[ResultadoTool]) -> str:
    """`evaluar_riesgo` suelto: solo condiciones de aplicación, sin veredicto."""
    datos = primer_dato(resultados) or {}
    condiciones = datos.get("condiciones")
    no_realizados = [c for r in resultados for c in r.chequeos_no_realizados]
    citas = citas_no_mostradas_inline(todas_las_citas(resultados), condiciones)
    return unir_secciones(
        bloque_condiciones(condiciones), bloque_no_verificado(no_realizados),
        seccion_fuentes(citas), SEGUIMIENTO_COMPLETO if condiciones else "",
    )


def plantilla_detalle_bandas(respuesta: RespuestaAgente, resultados: list[ResultadoTool]) -> str:
    """Banda toxicológica de cada producto a aplicar (lo que se ofrece tras el
    dictamen). Sale de la evaluación de riesgo del turno, no del LLM."""
    datos = primer_dato(resultados) or {}
    condiciones = datos.get("condiciones") or (datos.get("dictamen") or {}).get("condiciones")
    if not condiciones:
        return "No pude obtener la banda de los productos."
    registros = {p.get("nombre"): p.get("numero_inscripcion") for p in datos.get("productos", [])}
    productos = condiciones.get("productos_por_banda") or {}

    lineas = ["*Banda de cada producto*"]
    for producto, banda in productos.items():
        reg = f" · Reg. SENASA {registros[producto]}" if registros.get(producto) else ""
        if banda:
            lineas.append(f"- {producto}{reg}: {banda} ({COLOR_BANDA.get(banda, 'sin color')})")
        else:
            lineas.append(f"- {producto}{reg}: no figura en SENASA ⚠️")
    if not productos:
        lineas.append("- No pude identificar ningún producto en el registro de SENASA ⚠️")
    if condiciones.get("banda"):
        color = COLOR_BANDA.get(condiciones["banda"], "")
        lineas.append(
            f"La aplicación se rige por la más peligrosa: {condiciones['banda']}"
            + (f" ({color})." if color else ".")
        )

    # Las restricciones (distancias mínimas y sus avisos) van en el mismo
    # mensaje: quien pide la banda pide también qué exige la norma.
    no_realizados = [c for r in resultados for c in r.chequeos_no_realizados]
    return unir_secciones(
        "\n".join(lineas), bloque_condiciones(condiciones), bloque_no_verificado(no_realizados),
        "¿Querés que agende la aplicación?" if productos else "",
    )
