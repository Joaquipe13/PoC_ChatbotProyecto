"""Los mensajes de esta tool: lo que pregunta, lo que avisa y cómo se le muestra
el producto al operario (una de las dos formas del tipo de respuesta
`consulta_producto`; la otra es el listado de `consultar_productos`)."""

from fitosanitarios.dominio.modelos import RespuestaAgente, ResultadoTool
from fitosanitarios.servicios.formato import primer_dato

MOTIVO_PRODUCTO_AMBIGUO = "varios productos coinciden con ese nombre"


def pregunta_producto_ambiguo(nombre: str) -> str:
    return f"Hay varios productos parecidos a '{nombre}'. ¿Cuál es?"


def advertencia_sin_uso_registrado(marca: str, cultivo: str) -> str:
    return f"{marca} no tiene un uso registrado para {cultivo}"


def resumen_para_llm(estado: str) -> str:
    return f"validar_producto_registro: estado={estado}"


def plantilla_producto(respuesta: RespuestaAgente, resultados: list[ResultadoTool]) -> str:
    """Sin intro del LLM ni sección *Fuentes* aparte: ver
    `consultar_productos.mensajes.plantilla_listado`."""
    datos = primer_dato(resultados) or {}
    autorizado = (
        "✅ autorizado" if datos.get("cultivo_autorizado") else "⚠️ no autorizado para ese cultivo"
    )
    nombre = datos.get("producto", "(sin nombre)")
    registro = datos.get("numero_inscripcion", "-")
    banda = datos.get("banda_toxicologica") or "S/D"
    lineas = [f"*{nombre}* · Reg. SENASA {registro} · Banda {banda} · {autorizado}"]
    dosis_txt = next(
        (
            (uso.get("dosis") or {}).get("texto_original")
            for uso in datos.get("usos_registrados") or []
            if (uso.get("dosis") or {}).get("texto_original")
        ),
        None,
    )
    if dosis_txt:
        lineas.append(f"Dosis registrada: {dosis_txt}")
    return "\n".join(lineas)
