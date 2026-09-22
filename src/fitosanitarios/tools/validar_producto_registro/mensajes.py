"""Los mensajes de esta tool: lo que pregunta, lo que avisa y cómo se le muestra
el producto al operario (una de las dos formas del tipo de respuesta
`consulta_producto`; la otra es el listado de `consultar_productos`)."""

from fitosanitarios.dominio.modelos import RespuestaAgente, ResultadoTool
from fitosanitarios.servicios.formato import primer_dato

MOTIVO_PRODUCTO_AMBIGUO = "varios productos coinciden con ese nombre"
_MAXIMO_DOSIS = 4


def pregunta_producto_ambiguo(nombre: str) -> str:
    return f"Hay varios productos parecidos a '{nombre}'. ¿Cuál es?"


def advertencia_sin_uso_registrado(marca: str, cultivo: str) -> str:
    return f"{marca} no tiene un uso registrado para {cultivo}"


def resumen_para_llm(estado: str) -> str:
    return f"validar_producto_registro: estado={estado}"


def _dosis_del_cultivo(usos: list[dict]) -> list[str]:
    """Las dosis registradas para el cultivo, sin repetir, con su adversidad si la traen."""
    lineas: list[str] = []
    for uso in usos:
        texto = (uso.get("dosis") or {}).get("texto_original")
        if not texto:
            continue
        adversidad = uso.get("adversidad")
        linea = f"{texto} ({adversidad})" if adversidad else texto
        if linea not in lineas:
            lineas.append(linea)
    return lineas


def plantilla_producto(respuesta: RespuestaAgente, resultados: list[ResultadoTool]) -> str:
    """Sin sección *Fuentes* aparte: ver
    `consultar_productos.mensajes.plantilla_listado`. La dosis registrada es la del cultivo
    consultado: nunca la de otro cultivo (bug real: se mostraba la del primer uso registrado,
    de duraznero, para una consulta sobre soja)."""
    datos = primer_dato(resultados) or {}
    cultivo = datos.get("cultivo")
    para = f" para {cultivo}" if cultivo else ""
    estado = f"✅ autorizado{para}" if datos.get("cultivo_autorizado") else (
        f"⚠️ no autorizado{para}" if cultivo else "⚠️ no autorizado para ese cultivo"
    )
    nombre = datos.get("producto", "(sin nombre)")
    registro = datos.get("numero_inscripcion", "-")
    banda = datos.get("banda_toxicologica") or "S/D"
    lineas = [f"*{nombre}* · Reg. SENASA {registro} · Banda {banda} · {estado}"]

    dosis = _dosis_del_cultivo(datos.get("usos_del_cultivo") or [])
    titulo = f"Dosis registrada{para}"
    if len(dosis) == 1:
        lineas.append(f"{titulo}: {dosis[0]}")
    elif dosis:
        lineas.append(f"{titulo}:")
        lineas.extend(f"- {d}" for d in dosis[:_MAXIMO_DOSIS])
        if len(dosis) > _MAXIMO_DOSIS:
            lineas.append(f"- y {len(dosis) - _MAXIMO_DOSIS} más")
    return "\n".join(lineas)
