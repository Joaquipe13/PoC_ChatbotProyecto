"""Los mensajes de esta tool: lo que pregunta, lo que avisa y cómo se le muestra
el producto al operario (una de las dos formas del tipo de respuesta
`consulta_producto`; la otra es el listado de `consultar_productos`)."""

from fitosanitarios.dominio.modelos import RespuestaAgente, ResultadoTool
from fitosanitarios.servicios.condiciones_aplicacion import COLOR_BANDA
from fitosanitarios.servicios.formato import (
    primer_dato,
    seccion_fuentes,
    todas_las_citas,
    unir_secciones,
)

MOTIVO_PRODUCTO_AMBIGUO = "varios productos coinciden con ese nombre"
_MAXIMO_DOSIS = 4


def pregunta_producto_ambiguo(nombre: str) -> str:
    return f"Hay varios productos parecidos a '{nombre}'. ¿Cuál es?"


def advertencia_sin_uso_registrado(marca: str, cultivo: str) -> str:
    return f"{marca} no tiene un uso registrado para {cultivo}"


def no_verificado_sin_usos(cultivo: str | None, dosis: str | None) -> str:
    que = f"si {dosis} es una dosis correcta" if dosis else "la dosis ni el cultivo"
    para = f" para {cultivo}" if cultivo and dosis else ""
    return f"No puedo verificar {que}{para}: SENASA no publica los usos de este producto"


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


def _linea_del_producto(datos: dict) -> str:
    """Sin cultivo ("¿qué banda tiene el Tordon?"): registro y banda, con su color, que es
    como la nombra el operario."""
    nombre = datos.get("producto", "(sin nombre)")
    registro = datos.get("numero_inscripcion", "-")
    banda = datos.get("banda_toxicologica")
    color = COLOR_BANDA.get(banda) if banda else None
    banda_txt = f"Banda {banda} ({color})" if color else f"Banda {banda or 'S/D'}"
    return f"*{nombre}* · Reg. SENASA {registro} · {banda_txt}"


def _plantilla_sin_usos(datos: dict, citas: list) -> str:
    """Producto registrado sin cultivos ni dosis publicados: lo que se sabe, qué no se
    puede verificar y, si se encontró, lo que dice su marbete."""
    cultivo = datos.get("cultivo")
    dosis = datos.get("dosis_declarada")
    if dosis and cultivo:
        no_verifico = f"no puedo verificar si {dosis} es correcta para {cultivo.lower()}."
    elif cultivo:
        no_verifico = f"no puedo decirte la dosis registrada para {cultivo.lower()}."
    else:
        no_verifico = "no puedo decirte para qué cultivos ni en qué dosis se usa."
    lineas = [
        _linea_del_producto(datos),
        f"⚠️ SENASA no publica para qué cultivos ni en qué dosis está registrado, así que "
        f"{no_verifico}",
    ]
    marbete = datos.get("marbete")
    if marbete:
        lineas.append(f"*Según su marbete:* {marbete}")
        que_hacer = "confirmalo con el ingeniero agrónomo que firmó la receta."
    else:
        que_hacer = (
            "fijate la dosis en la etiqueta del envase o consultalo con el ingeniero "
            "agrónomo que firmó la receta."
        )
    lineas.append(f"*Qué podés hacer:* {que_hacer}")
    texto = "\n".join(lineas)
    del_marbete = [c for c in citas if (c.documento or "").startswith("marbete")]
    return unir_secciones(texto, seccion_fuentes(del_marbete)) if del_marbete else texto


def plantilla_producto(respuesta: RespuestaAgente, resultados: list[ResultadoTool]) -> str:
    """Sin sección *Fuentes* aparte: ver
    `consultar_productos.mensajes.plantilla_listado`. La dosis registrada es la del cultivo
    consultado: nunca la de otro cultivo (bug real: se mostraba la del primer uso registrado,
    de duraznero, para una consulta sobre soja)."""
    datos = primer_dato(resultados) or {}
    if datos.get("sin_usos_registrados"):
        return _plantilla_sin_usos(datos, todas_las_citas(resultados))
    cultivo = datos.get("cultivo")
    if not cultivo and datos.get("cultivo_autorizado") is None:
        return _linea_del_producto(datos)
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
