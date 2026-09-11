"""Formateador determinista: arma el texto final de WhatsApp a partir de
`RespuestaAgente.tipo` y los artifacts (`ResultadoTool`) de las tools que
corrieron en el turno -- nunca del texto libre del LLM (ver skill,
"Contratos": el formateador "renderiza los artifacts de las tools
ejecutadas en el turno actual, así el LLM no puede alterar números ni
citas", y "Formato de respuestas").

Una función `_plantilla_<tipo>` por cada valor de `RespuestaAgente.tipo`
(ver docs/especificacion-plantillas.md), reunidas en un solo módulo en vez
de una carpeta `plantillas/` -- son 9 funciones chicas, no ameritan
subpaquete propio (ver DECISIONES.md).
"""

from fitosanitarios.dominio.modelos import Cita, RespuestaAgente, ResultadoTool
from fitosanitarios.dominio.motivos import DESCRIPCION_MOTIVO, MotivoNoResuelto

LIMITE_CARACTERES_WHATSAPP = 4096

_ICONO_DICTAMEN = {"APTA": "✅", "OBSERVADA": "❌", "NO_EVALUABLE": "⚠️"}


def _num(valor) -> str:
    if valor is None:
        return "no figura"
    if isinstance(valor, bool):
        return str(valor)
    if isinstance(valor, int) or (isinstance(valor, float) and float(valor).is_integer()):
        return str(int(valor))
    return f"{valor}".replace(".", ",")


def _texto_cita(cita: Cita) -> str:
    if cita.fuente == "normativa":
        partes = [p for p in (cita.norma, f"art. {cita.articulo}" if cita.articulo else None) if p]
        texto = ", ".join(partes) if partes else "normativa"
        if cita.jurisdiccion_id:
            texto += f" ({cita.jurisdiccion_id})"
        return texto
    partes = [p for p in (
        f"Reg. {cita.registro_senasa}" if cita.registro_senasa else None,
        f"({cita.documento})" if cita.documento else None,
    ) if p]
    return "SENASA" + (", " + " ".join(partes) if partes else "")


def _seccion_fuentes(citas: list[Cita]) -> str:
    if not citas:
        return ""
    vistas: list[str] = []
    for c in citas:
        texto = _texto_cita(c)
        if texto not in vistas:
            vistas.append(texto)
    return "\n".join(["*Fuentes*"] + [f"- {v}" for v in vistas])


def _unir_secciones(*secciones: str) -> str:
    return "\n\n".join(s for s in secciones if s.strip())


def _primer_dato(resultados: list[ResultadoTool]) -> dict | None:
    for r in resultados:
        if r.datos:
            return r.datos
    return None


def _todas_las_citas(resultados: list[ResultadoTool]) -> list[Cita]:
    citas: list[Cita] = []
    for r in resultados:
        citas.extend(r.citas)
    return citas


# --- confirmacion_receta ---


def _plantilla_confirmacion_receta(
    respuesta: RespuestaAgente, resultados: list[ResultadoTool]
) -> str:
    datos = _primer_dato(resultados) or {}
    numero_txt = f" N.° {datos['numero']}" if datos.get("numero") else ""
    lineas = [f"*Leí la receta{numero_txt}*. Confirmá los datos:"]
    lineas.append(f"- *Cultivo:* {datos.get('cultivo') or 'no figura ⚠️'}")
    lineas.append(f"- *Lote:* {datos.get('lote') or 'no figura ⚠️'}")
    if datos.get("adversidad"):
        lineas.append(f"- *Adversidad:* {datos['adversidad']}")
    for item in datos.get("items", []):
        producto = item.get("producto_nombre", "producto sin nombre")
        dosis = item.get("dosis_declarada") or "sin dosis"
        lineas.append(f"- *Producto:* {producto} — {dosis}")
    if not datos.get("items"):
        lineas.append("- *Producto:* no figura ⚠️")
    if datos.get("superficie_ha") is not None:
        lineas.append(f"- *Superficie:* {_num(datos['superficie_ha'])} ha")
    tipo_aplic = datos.get("tipo_aplicacion")
    lineas.append(f"- *Tipo de aplicación:* {tipo_aplic if tipo_aplic else 'no figura ⚠️'}")
    lineas.append("[Confirmar] [Corregir]")
    return "\n".join(lineas)


# --- dictamen ---


def _plantilla_dictamen(respuesta: RespuestaAgente, resultados: list[ResultadoTool]) -> str:
    datos = _primer_dato(resultados) or {}
    dictamen = datos.get("dictamen", {})
    resultado = dictamen.get("resultado", "NO_EVALUABLE")
    jurisdiccion = datos.get("jurisdiccion_id", "")
    icono = _ICONO_DICTAMEN.get(resultado, "⚠️")

    titulo = f"*Dictamen*{' — ' + jurisdiccion if jurisdiccion else ''}"
    encabezado = f"{titulo}\n*Resultado:* {icono} {resultado}"

    observaciones = dictamen.get("observaciones", [])
    bloque_observaciones = ""
    if observaciones:
        lineas = ["*Observaciones*"]
        lineas += [f"{i}. {o['descripcion']}" for i, o in enumerate(observaciones, start=1)]
        bloque_observaciones = "\n".join(lineas)

    no_realizados = dictamen.get("chequeos_no_realizados", [])
    bloque_no_realizados = ""
    if no_realizados:
        lineas = ["*No se pudo verificar*"]
        lineas += [f"- {c}" for c in no_realizados]
        bloque_no_realizados = "\n".join(lineas)

    citas = [Cita.model_validate(c) for c in dictamen.get("citas", [])]
    return _unir_secciones(
        encabezado, bloque_observaciones, bloque_no_realizados, _seccion_fuentes(citas)
    )


# --- consulta_producto ---


def _plantilla_consulta_producto(
    respuesta: RespuestaAgente, resultados: list[ResultadoTool]
) -> str:
    datos = _primer_dato(resultados) or {}

    if "productos" in datos:  # consultar_productos: listado
        productos = datos["productos"]
        total = datos.get("total", len(productos))
        if not productos:
            return "No encontré productos registrados con esos filtros."
        lineas = [f"*Productos registrados* ({len(productos)} de {total})"]
        for i, p in enumerate(productos[:10], start=1):
            dosis = p.get("dosis") or {}
            dosis_txt = dosis.get("texto_original", "sin dosis registrada")
            marca = p.get("marca", "(sin marca)")
            registro = p.get("numero_inscripcion", "-")
            banda = p.get("banda_toxicologica") or "S/D"
            lineas.append(f"{i}. {marca} · Reg. SENASA {registro} · Banda {banda} · {dosis_txt}")
        lineas.append(
            "Es lo que figura en el registro; qué aplicar lo define la receta "
            "del ingeniero agrónomo."
        )
        cuerpo = "\n".join(lineas)
    else:  # validar_producto_registro: producto puntual
        autorizado = (
            "✅" if datos.get("cultivo_autorizado") else "⚠️ no autorizado para ese cultivo"
        )
        nombre = datos.get("producto", "(sin nombre)")
        registro = datos.get("numero_inscripcion", "-")
        banda = datos.get("banda_toxicologica") or "S/D"
        cuerpo = f"*{nombre}* · Reg. SENASA {registro} · Banda {banda} · {autorizado}"

    return _unir_secciones(cuerpo, _seccion_fuentes(_todas_las_citas(resultados)))


# --- consulta_normativa ---


def _plantilla_consulta_normativa(
    respuesta: RespuestaAgente, resultados: list[ResultadoTool]
) -> str:
    datos = _primer_dato(resultados) or {}
    veredicto = datos.get("veredicto", "Depende")
    regla = datos.get("regla", "")
    cuerpo = f"*{veredicto}.* {regla}"
    return _unir_secciones(cuerpo, _seccion_fuentes(_todas_las_citas(resultados)))


# --- repregunta ---


def _plantilla_repregunta(respuesta: RespuestaAgente, resultados: list[ResultadoTool]) -> str:
    faltantes = respuesta.faltantes or (resultados[0].faltantes if resultados else [])
    if not faltantes:
        return (
            "Necesito un dato más para continuar, pero no pude identificar cuál. "
            "¿Podés repetir el mensaje?"
        )
    plural = "s" if len(faltantes) != 1 else ""
    lineas = [f"Para continuar necesito {len(faltantes)} dato{plural}:"]
    for i, f in enumerate(faltantes[:3], start=1):
        lineas.append(f"{i}. *{f.campo}*: {f.pregunta_sugerida}")
        if f.tipo_entrada == "botones" and f.opciones:
            lineas.append("[" + "] [".join(f.opciones) + "]")
        elif f.tipo_entrada == "lista" and f.opciones:
            lineas.extend(f"   - {o}" for o in f.opciones[:10])
    return "\n".join(lineas)


# --- fuera_de_dominio ---


def _plantilla_fuera_de_dominio(respuesta: RespuestaAgente, resultados: list[ResultadoTool]) -> str:
    return (
        "Solo puedo ayudarte con recetas de fitosanitarios: leer y validar recetas, "
        "verificar productos registrados en SENASA y responder dudas sobre la normativa "
        "de aplicación de las localidades cargadas. ¿Me mandás una receta o una consulta "
        "sobre eso?"
    )


# --- no_resuelto ---


def _plantilla_no_resuelto(respuesta: RespuestaAgente, resultados: list[ResultadoTool]) -> str:
    motivo: MotivoNoResuelto | None = next((r.motivo for r in resultados if r.motivo), None)
    porque = DESCRIPCION_MOTIVO.get(motivo, "no se pudo determinar el motivo exacto.")

    advertencias = [a for r in resultados for a in r.advertencias]
    lineas = ["⚠️ *No pude completar la consulta*", f"*Por qué:* {porque}"]
    if advertencias:
        lineas.append(f"*Detalle:* {advertencias[0]}")
    lineas.append(
        "*Qué podés hacer:* revisá el dato e intentá de nuevo, o consultá al área de "
        "ambiente del municipio / a tu ingeniero agrónomo."
    )
    return "\n".join(lineas)


# --- ayuda ---


def _plantilla_ayuda(respuesta: RespuestaAgente, resultados: list[ResultadoTool]) -> str:
    return (
        "Hola 👋 Soy el asistente de recetas fitosanitarias. Puedo:\n"
        "- Leer una foto de tu receta y decirte si es apta para aplicar.\n"
        "- Buscar si un producto está registrado en SENASA.\n"
        "- Responder dudas sobre la normativa de aplicación de tu localidad.\n"
        "Mandame una foto de receta o contame qué necesitás."
    )


# --- error ---


def _plantilla_error(respuesta: RespuestaAgente, resultados: list[ResultadoTool]) -> str:
    return (
        "⚠️ Tuve un problema técnico y no pude procesar tu mensaje. Probá de nuevo en "
        "unos minutos; si sigue fallando, contactá a soporte."
    )


_PLANTILLAS = {
    "confirmacion_receta": _plantilla_confirmacion_receta,
    "dictamen": _plantilla_dictamen,
    "consulta_producto": _plantilla_consulta_producto,
    "consulta_normativa": _plantilla_consulta_normativa,
    "repregunta": _plantilla_repregunta,
    "fuera_de_dominio": _plantilla_fuera_de_dominio,
    "no_resuelto": _plantilla_no_resuelto,
    "ayuda": _plantilla_ayuda,
    "error": _plantilla_error,
}


def partir_por_seccion(texto: str, limite: int = LIMITE_CARACTERES_WHATSAPP) -> list[str]:
    """Parte un mensaje largo por sección (separadas por línea en blanco),
    nunca a mitad de una lista (ver skill, "Formato de respuestas")."""
    if len(texto) <= limite:
        return [texto]
    secciones = texto.split("\n\n")
    mensajes: list[str] = []
    actual = ""
    for seccion in secciones:
        candidato = f"{actual}\n\n{seccion}" if actual else seccion
        if len(candidato) > limite and actual:
            mensajes.append(actual)
            actual = seccion
        else:
            actual = candidato
    if actual:
        mensajes.append(actual)
    return mensajes


def formatear_respuesta(respuesta: RespuestaAgente, resultados: list[ResultadoTool]) -> list[str]:
    """Punto de entrada del formateador: `RespuestaAgente.tipo` + los
    `ResultadoTool` de las tools ejecutadas en el turno -> lista de mensajes
    de WhatsApp (más de uno solo si supera el límite de caracteres)."""
    render = _PLANTILLAS[respuesta.tipo]
    texto = render(respuesta, resultados)
    if respuesta.intro and respuesta.tipo not in ("fuera_de_dominio", "ayuda", "error"):
        texto = f"{respuesta.intro}\n\n{texto}"
    return partir_por_seccion(texto)
