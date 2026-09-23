"""Los mensajes de esta tool: lo que ve el agente de lo leído y cómo se le muestra la
receta al operario (la plantilla del tipo de respuesta `confirmacion_receta`, que usa
también `completar_receta`). Las preguntas por los datos obligatorios están en
`servicios/receta.py`."""

from fitosanitarios.dominio.modelos import RespuestaAgente, ResultadoTool
from fitosanitarios.servicios.formato import num
from fitosanitarios.servicios.receta import NOMBRE_CAMPO, datos_para_llm

# --- lo que ve el agente (el LLM orquestador) de lo leído ---


def resumen_para_llm(resultado: ResultadoTool) -> str:
    if resultado.estado in ("ok", "faltan_datos") and resultado.datos:
        texto = (
            "Receta leída. Datos de la receta (usá solo estos; un dato que dice NO FIGURA "
            f"no lo inventes ni lo supongas): {datos_para_llm(resultado.datos)}."
        )
        if resultado.faltantes:
            campos = ", ".join(f.campo for f in resultado.faltantes)
            texto += (
                f" Faltan datos obligatorios: {campos}; ya se le preguntaron al operario. "
                "Cuando los dé (o corrija un dato), llamá `completar_receta` con esos datos."
            )
        else:
            texto += " Si el operario corrige un dato, llamá `completar_receta` con ese dato."
        return texto
    if resultado.estado == "ok":
        return "Receta leída correctamente, todos los campos con confianza suficiente."
    if resultado.estado == "faltan_datos":
        campos = ", ".join(f.campo for f in resultado.faltantes)
        return f"Receta leída parcialmente. Faltan o no se leyeron con confianza: {campos}."
    return "No se pudo leer la imagen como una receta (no es legible)."


# --- plantilla del resultado (tipo de respuesta `confirmacion_receta`) ---


def _con_datos(resultados: list[ResultadoTool]) -> ResultadoTool | None:
    return next((r for r in resultados if r.datos), None)


def _lineas_leidas(datos: dict) -> list[str]:
    """Lo que tiene la receta, sin los datos que faltan (esos se preguntan aparte)."""
    lineas = []
    for campo in ("cultivo", "lote", "localidad"):
        if datos.get(campo):
            lineas.append(f"- *{NOMBRE_CAMPO[campo]}:* {datos[campo]}")
    if datos.get("superficie_ha") is not None:
        lineas.append(f"- *Superficie:* {num(datos['superficie_ha'])} ha")
    if datos.get("adversidad"):
        lineas.append(f"- *Adversidad:* {datos['adversidad']}")
    for item in datos.get("items", []):
        producto = item.get("producto_nombre", "producto sin nombre")
        dosis = f" — {item['dosis_declarada']}" if item.get("dosis_declarada") else ""
        detalle = " · ".join(
            p for p in (item.get("principio_activo"), item.get("clase_toxicologica")) if p
        )
        sufijo = f" ({detalle})" if detalle else ""
        lineas.append(f"- *Producto:* {producto}{dosis}{sufijo}")
        if item.get("adversidad"):
            lineas.append(f"  Plaga/maleza: {item['adversidad']}")
    if datos.get("tipo_aplicacion"):
        tipo = "aérea" if datos["tipo_aplicacion"] == "aerea" else datos["tipo_aplicacion"]
        lineas.append(f"- *Tipo de aplicación:* {tipo}")
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
    return lineas


def plantilla_confirmacion_receta(
    respuesta: RespuestaAgente, resultados: list[ResultadoTool]
) -> str:
    """Con todos los datos obligatorios, la receta para confirmar ([Confirmar]
    [Corregir]). Si falta alguno, no se ofrece confirmar: primero se pregunta lo que
    falta y se muestra aparte lo que sí se leyó (pedido del usuario, 23/09/2026: antes
    se mostraba "no figura ⚠️" y se podía confirmar igual)."""
    resultado = _con_datos(resultados)
    datos = resultado.datos if resultado else {}
    numero_txt = f" N.° {datos['numero']}" if datos.get("numero") else ""
    leidas = _lineas_leidas(datos)
    faltantes = resultado.faltantes if resultado else []

    if faltantes:
        preguntas = [
            f"{i}. *{NOMBRE_CAMPO.get(f.campo, f.campo)}:* {f.pregunta_sugerida}"
            for i, f in enumerate(faltantes, start=1)
        ]
        secciones = [
            f"*Leí la receta{numero_txt}*. Falta la siguiente información obligatoria:",
            "\n".join(preguntas),
        ]
        if leidas:
            secciones.append("\n".join(["*Lo que pude leer:*", *leidas]))
        return "\n\n".join(secciones)

    return "\n".join(
        [f"*Leí la receta{numero_txt}*. Confirmá los datos:", *leidas, "[Confirmar] [Corregir]"]
    )
