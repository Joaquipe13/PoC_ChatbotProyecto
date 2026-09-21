"""Los mensajes de esta tool: lo que pregunta cuando no pudo leer un dato, lo que
ve el agente de lo leído y cómo se le muestra la receta al operario para que la
confirme (la plantilla del tipo de respuesta `confirmacion_receta`)."""

from fitosanitarios.dominio.modelos import RespuestaAgente, ResultadoTool
from fitosanitarios.servicios.formato import num, primer_dato

# --- preguntas y motivos de la tool ---

MOTIVO_CAMPO_ILEGIBLE = "no se pudo leer con confianza suficiente en la imagen"
MOTIVO_SIN_PRODUCTOS = "no se pudo leer ningún producto con confianza suficiente"
PREGUNTA_POR_CAMPO = {
    "cultivo": "¿Qué cultivo es?",
    "lote": "¿Cuál es el número o nombre del lote?",
    "superficie_ha": "¿Cuántas hectáreas tiene el lote?",
    "productos": "¿Qué producto y dosis indica la receta?",
}

# --- lo que ve el agente (el LLM orquestador) de lo leído ---


def datos_para_llm(datos: dict) -> str:
    """Lo leído, en texto: es lo ÚNICO que el agente sabe de la receta (el
    formateador arma el mensaje al usuario desde el artifact, no desde acá).
    Sin esto el LLM completaba cultivo, producto, dosis y localidad por su
    cuenta y evaluaba datos inventados (bug real, ver DIFICULTADES.md)."""
    productos = "; ".join(
        f"{i['producto_nombre']} (dosis: {i.get('dosis_declarada') or 'NO FIGURA'})"
        for i in datos.get("items", [])
    )
    campos = {
        "cultivo": datos.get("cultivo"), "lote": datos.get("lote"),
        "superficie_ha": datos.get("superficie_ha"),
        "tipo_aplicacion": datos.get("tipo_aplicacion"),
        "localidad": datos.get("localidad"), "adversidad": datos.get("adversidad"),
        "productos": productos or None,
    }
    return "; ".join(f"{k}={v if v not in (None, '') else 'NO FIGURA'}" for k, v in campos.items())


def resumen_para_llm(resultado: ResultadoTool) -> str:
    if resultado.estado in ("ok", "faltan_datos") and resultado.datos:
        texto = (
            "Receta leída. Datos de la receta (usá solo estos; un dato que dice NO FIGURA "
            f"no lo inventes ni lo supongas): {datos_para_llm(resultado.datos)}."
        )
        if resultado.faltantes:
            campos = ", ".join(f.campo for f in resultado.faltantes)
            texto += f" No se leyeron con confianza: {campos}."
        return texto
    if resultado.estado == "ok":
        return "Receta leída correctamente, todos los campos con confianza suficiente."
    if resultado.estado == "faltan_datos":
        campos = ", ".join(f.campo for f in resultado.faltantes)
        return f"Receta leída parcialmente. Faltan o no se leyeron con confianza: {campos}."
    return "No se pudo leer la imagen como una receta (no es legible)."


# --- plantilla del resultado (tipo de respuesta `confirmacion_receta`) ---


def plantilla_confirmacion_receta(
    respuesta: RespuestaAgente, resultados: list[ResultadoTool]
) -> str:
    """`cultivo`, `lote`, `superficie`, `producto` y `tipo_aplicacion` son los
    campos que alimentan un chequeo legal más adelante (el tipo define la banda
    y la distancia mínima que se informan; ver `utils.py`): si faltan se
    muestran igual, con ⚠️. El resto de los campos (ver `Receta`, DECISIONES.md)
    son descriptivos de la receta real -- se muestran solo si se pudieron leer,
    sin ⚠️ ni bloquear la confirmación."""
    datos = primer_dato(resultados) or {}
    numero_txt = f" N.° {datos['numero']}" if datos.get("numero") else ""
    lineas = [f"*Leí la receta{numero_txt}*. Confirmá los datos:"]
    lineas.append(f"- *Cultivo:* {datos.get('cultivo') or 'no figura ⚠️'}")
    lineas.append(f"- *Lote:* {datos.get('lote') or 'no figura ⚠️'}")
    lineas.append(f"- *Localidad:* {datos.get('localidad') or 'no figura ⚠️'}")
    lineas.append(
        f"- *Superficie:* {num(datos['superficie_ha'])} ha"
        if datos.get("superficie_ha") is not None
        else "- *Superficie:* no figura ⚠️"
    )
    if datos.get("adversidad"):
        lineas.append(f"- *Adversidad:* {datos['adversidad']}")
    for item in datos.get("items", []):
        producto = item.get("producto_nombre", "producto sin nombre")
        dosis = item.get("dosis_declarada") or "sin dosis"
        detalle = " · ".join(
            p for p in (item.get("principio_activo"), item.get("clase_toxicologica")) if p
        )
        sufijo = f" ({detalle})" if detalle else ""
        lineas.append(f"- *Producto:* {producto} — {dosis}{sufijo}")
        if item.get("adversidad"):
            lineas.append(f"  Plaga/maleza: {item['adversidad']}")
    if not datos.get("items"):
        lineas.append("- *Producto:* no figura ⚠️")
    lineas.append(f"- *Tipo de aplicación:* {datos.get('tipo_aplicacion') or 'no figura ⚠️'}")
    if datos.get("caudal"):
        lineas.append(f"- *Caudal:* {datos['caudal']}")
    if datos.get("ubic_poblado"):
        lineas.append(f"- *Ubicación respecto de zonas pobladas:* {datos['ubic_poblado']}")
    if datos.get("condiciones"):
        lineas.append(f"- *Condiciones de aplicación:* {datos['condiciones']}")
    if datos.get("restricciones"):
        lineas.append(f"- *Restricciones:* {datos['restricciones']}")
    if datos.get("observaciones"):
        lineas.append(f"- *Observaciones:* {datos['observaciones']}")
    if datos.get("fecha_emision"):
        lineas.append(f"- *Fecha de emisión:* {datos['fecha_emision']}")
    if datos.get("validez_dias") is not None:
        lineas.append(f"- *Validez:* {num(datos['validez_dias'])} días")
    lineas.append("[Confirmar] [Corregir]")
    return "\n".join(lineas)
