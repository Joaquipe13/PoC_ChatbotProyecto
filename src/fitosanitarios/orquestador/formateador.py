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

import re

from fitosanitarios.dominio.modelos import Cita, RespuestaAgente, ResultadoTool
from fitosanitarios.dominio.motivos import DESCRIPCION_MOTIVO, MotivoNoResuelto

LIMITE_CARACTERES_WHATSAPP = 4096

_ICONO_DICTAMEN = {"APTA": "✅", "OBSERVADA": "❌", "NO_EVALUABLE": "⚠️"}

_NOMBRE_ZONA = {
    "zona_urbana": "zona urbana",
    "escuela": "escuelas",
    "curso_agua": "cursos de agua",
    "otro": "otras zonas protegidas",
}


def _num(valor) -> str:
    if valor is None:
        return "no figura"
    if isinstance(valor, bool):
        return str(valor)
    if isinstance(valor, int) or (isinstance(valor, float) and float(valor).is_integer()):
        return str(int(valor))
    return f"{valor}".replace(".", ",")


def _norma_legible(norma: str) -> str:
    """"ordenanza-841-2010" (nombre del PDF) -> "Ordenanza 841/2010"."""
    m = re.fullmatch(r"(ordenanza|decreto|resolucion|ley)-(\w+)-(\d{4})", norma)
    if not m:
        return norma
    tipo = "Resolución" if m[1] == "resolucion" else m[1].capitalize()
    return f"{tipo} {m[2]}/{m[3]}"


def _cita_norma(cita: Cita) -> str:
    """Norma y artículo sin la jurisdicción: "Ordenanza 841/2010, art. 7"."""
    partes = [
        p for p in (
            _norma_legible(cita.norma) if cita.norma else None,
            f"art. {cita.articulo}" if cita.articulo else None,
        ) if p
    ]
    return ", ".join(partes) if partes else "normativa"


def _texto_cita(cita: Cita) -> str:
    if cita.fuente == "normativa":
        texto = _cita_norma(cita)
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
    """`cultivo`, `lote`, `superficie`, `producto` y `tipo_aplicacion` son los
    campos que alimentan un chequeo legal más adelante (el tipo define la banda
    y la distancia mínima que se informan; ver `servicios/extraccion_receta.py`):
    si faltan se muestran igual, con ⚠️. El resto de los campos (ver
    `Receta`, DECISIONES.md) son descriptivos de la receta real -- se
    muestran solo si se pudieron leer, sin ⚠️ ni bloquear la confirmación."""
    datos = _primer_dato(resultados) or {}
    numero_txt = f" N.° {datos['numero']}" if datos.get("numero") else ""
    lineas = [f"*Leí la receta{numero_txt}*. Confirmá los datos:"]
    lineas.append(f"- *Cultivo:* {datos.get('cultivo') or 'no figura ⚠️'}")
    lineas.append(f"- *Lote:* {datos.get('lote') or 'no figura ⚠️'}")
    lineas.append(
        f"- *Superficie:* {_num(datos['superficie_ha'])} ha"
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
        lineas.append(f"- *Validez:* {_num(datos['validez_dias'])} días")
    lineas.append("[Confirmar] [Corregir]")
    return "\n".join(lineas)


# --- dictamen ---

_SEGUIMIENTO_COMPLETO = (
    "¿Querés más info (la banda de cada producto) o que agende la aplicación?"
)
_SEGUIMIENTO_SOLO_INFO = "¿Querés más info (la banda de cada producto)?"


def _bloque_condiciones(condiciones: dict | None) -> str:
    """Lo más concreto posible: distancia mínima y la norma que la fija. La
    banda de cada producto queda para cuando el usuario pide más info. No
    compara contra la ubicación del lote."""
    if not condiciones:
        return ""
    tipo = "aérea" if condiciones["tipo_aplicacion"] == "aerea" else condiciones["tipo_aplicacion"]
    banda = condiciones.get("banda")
    if banda:
        color = f" ({condiciones['banda_color']})" if condiciones.get("banda_color") else ""
        detalle = f"{tipo} · banda {banda}{color}"
    else:
        detalle = f"{tipo} · banda no determinada ⚠️"
    lineas = [f"*Condiciones de aplicación* — {condiciones['localidad']} · {detalle}"]
    for d in condiciones.get("distancias_minimas", []):
        zona = _NOMBRE_ZONA.get(d["tipo_zona"], d["tipo_zona"])
        limitante = d.get("norma_limitante")
        norma = f" ({_cita_norma(Cita.model_validate(limitante))})" if limitante else ""
        lineas.append(f"- *Distancia mínima a {zona}:* {_num(d['distancia_min_m'])} m{norma}")
    for d in condiciones.get("distancias_minimas", []):
        if d.get("extraida_de_pdf") and d.get("norma_limitante"):
            zona = _NOMBRE_ZONA.get(d["tipo_zona"], d["tipo_zona"])
            fuente = _cita_norma(Cita.model_validate(d["norma_limitante"]))
            lineas.append(
                f"⚠️ La distancia a {zona} se leyó del texto de {fuente} (la norma no "
                "tiene reglas.csv): verificala con la norma."
            )
        lineas.extend(f"⚠️ {a}" for a in d.get("advertencias", []))
    lineas.extend(f"⚠️ {a}" for a in condiciones.get("advertencias", []))
    return "\n".join(lineas)


def _citas_no_mostradas_inline(citas: list[Cita], condiciones: dict | None) -> list[Cita]:
    """La norma que limita cada distancia ya va en su línea: en *Fuentes*
    queda el resto (SENASA, otras reglas que aplican) sin repetirla."""
    if not condiciones:
        return citas
    inline = [
        Cita.model_validate(d["norma_limitante"])
        for d in condiciones.get("distancias_minimas", []) if d.get("norma_limitante")
    ]
    return [c for c in citas if c not in inline]


def _plantilla_dictamen(respuesta: RespuestaAgente, resultados: list[ResultadoTool]) -> str:
    datos = _primer_dato(resultados) or {}
    dictamen = datos.get("dictamen")
    if dictamen is None:
        # `evaluar_riesgo` suelto: solo condiciones de aplicación, sin veredicto.
        condiciones = datos.get("condiciones")
        no_realizados = [c for r in resultados for c in r.chequeos_no_realizados]
        bloque_no_realizados = (
            "\n".join(["*No se pudo verificar*"] + [f"- {c}" for c in no_realizados])
            if no_realizados else ""
        )
        citas = _citas_no_mostradas_inline(_todas_las_citas(resultados), condiciones)
        return _unir_secciones(
            _bloque_condiciones(condiciones), bloque_no_realizados, _seccion_fuentes(citas),
            _SEGUIMIENTO_COMPLETO if condiciones else "",
        )
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

    no_realizados = dictamen.get("chequeos_no_realizados", [])
    bloque_no_realizados = ""
    if no_realizados:
        lineas = ["*No se pudo verificar*"]
        lineas += [f"- {c}" for c in no_realizados]
        bloque_no_realizados = "\n".join(lineas)

    citas = [Cita.model_validate(c) for c in dictamen.get("citas", [])]
    seguimiento = ""
    if condiciones:
        # Una receta observada no se ofrece para agendar.
        seguimiento = _SEGUIMIENTO_SOLO_INFO if resultado == "OBSERVADA" else _SEGUIMIENTO_COMPLETO
    return _unir_secciones(
        encabezado, bloque_observaciones, bloque_no_realizados,
        _bloque_condiciones(condiciones),
        _seccion_fuentes(_citas_no_mostradas_inline(citas, condiciones)),
        seguimiento,
    )


# --- detalle_bandas ---


_COLOR_BANDA = {"Ia": "roja", "Ib": "roja", "II": "amarilla", "III": "azul", "IV": "verde"}


def _plantilla_detalle_bandas(respuesta: RespuestaAgente, resultados: list[ResultadoTool]) -> str:
    """Banda toxicológica de cada producto a aplicar (lo que se ofrece tras el
    dictamen). Sale de la evaluación de riesgo del turno, no del LLM."""
    datos = _primer_dato(resultados) or {}
    condiciones = datos.get("condiciones") or (datos.get("dictamen") or {}).get("condiciones")
    if not condiciones:
        return "No pude obtener la banda de los productos."
    registros = {p.get("nombre"): p.get("numero_inscripcion") for p in datos.get("productos", [])}

    lineas = ["*Banda de cada producto*"]
    for producto, banda in (condiciones.get("productos_por_banda") or {}).items():
        reg = f" · Reg. SENASA {registros[producto]}" if registros.get(producto) else ""
        if banda:
            lineas.append(f"- {producto}{reg}: {banda} ({_COLOR_BANDA.get(banda, 'sin color')})")
        else:
            lineas.append(f"- {producto}{reg}: no figura en SENASA ⚠️")
    if condiciones.get("banda"):
        color = _COLOR_BANDA.get(condiciones["banda"], "")
        lineas.append(
            f"La aplicación se rige por la más peligrosa: {condiciones['banda']}"
            + (f" ({color})." if color else ".")
        )
    return _unir_secciones("\n".join(lineas), "¿Querés que agende la aplicación?")


# --- agendar_aplicacion ---


def _lineas_agenda(tareas: list[dict]) -> list[str]:
    _ICONO_TAREA = {"pendiente": "⏳", "en_curso": "🚜", "finalizada": "✅"}
    lineas = []
    for i, t in enumerate(tareas, start=1):
        icono = _ICONO_TAREA.get(t.get("estado_tarea"), "⚠️")
        hora = f"{t['hora']} — " if t.get("hora") else ""
        cultivo = t.get("cultivo") or "sin cultivo"
        lote = t.get("lote") or "sin lote"
        lineas.append(f"{i}. {icono} {hora}{cultivo} — lote {lote} ({t.get('estado_tarea')})")
    return lineas


def _plantilla_agendar_aplicacion(
    respuesta: RespuestaAgente, resultados: list[ResultadoTool]
) -> str:
    resultado = resultados[0] if resultados else None
    datos = (resultado.datos if resultado else None) or {}

    if resultado is not None and resultado.estado == "ok":
        lineas = [f"✅ *Aplicación agendada* — {datos['fecha_legible']}, {datos['hora']} hs"]
        if datos.get("cultivo"):
            lineas.append(f"- *Cultivo:* {datos['cultivo']}")
        if datos.get("lote"):
            lineas.append(f"- *Lote:* {datos['lote']}")
        lineas.extend(f"⚠️ {a}" for a in resultado.advertencias)
        return "\n".join(lineas)

    faltante = resultado.faltantes[0] if resultado and resultado.faltantes else None
    if faltante is None:
        return "No pude agendar la aplicación. ¿Me decís de nuevo el día y el horario?"

    if faltante.campo == "hora":
        tareas = datos.get("tareas", [])
        if tareas:
            agenda = "\n".join(
                [f"*Agenda del {datos['fecha_legible']}* ({len(tareas)})"] + _lineas_agenda(tareas)
            )
        else:
            agenda = f"No tenés nada agendado para el {datos['fecha_legible']}."
        pregunta = f"{faltante.pregunta_sugerida} Por ejemplo: 8:30 o 3 de la tarde."
        return _unir_secciones(agenda, pregunta)

    aviso = ""
    if not faltante.motivo.startswith("no se indicó"):
        aviso = f"{faltante.motivo[0].upper()}{faltante.motivo[1:]}. "
    return (
        f"{aviso}{faltante.pregunta_sugerida} Podés decirme un día (por ejemplo "
        "\"martes\" o \"mañana\") o una fecha (por ejemplo 25/09)."
    )


# --- consulta_producto ---


def _plantilla_consulta_producto(
    respuesta: RespuestaAgente, resultados: list[ResultadoTool]
) -> str:
    """Sin intro del LLM ni sección *Fuentes* aparte (ver `formatear_respuesta`
    y DECISIONES.md): acá la única Cita que arman las tools es un marcador
    genérico ("SENASA, (vademécum)" o "SENASA, Reg. NNNN (detalle API)") que
    no agrega nada sobre lo que ya va en la línea del producto (el propio
    n.° de registro), así que mostrarla aparte es puro ruido. La Cita real
    sigue viajando en `ResultadoTool.citas` y quedando logueada por turno;
    esto solo cambia qué se le muestra al usuario en el chat."""
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
            lineas.append(f"{i}. *{marca}* · Reg. SENASA {registro} · Banda {banda} · {dosis_txt}")
        lineas.append(
            "Es lo que figura en el registro; qué aplicar lo define la receta "
            "del ingeniero agrónomo."
        )
        return "\n".join(lineas)

    # validar_producto_registro: producto puntual
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


# --- consulta_normativa ---


def _plantilla_consulta_normativa(
    respuesta: RespuestaAgente, resultados: list[ResultadoTool]
) -> str:
    datos = _primer_dato(resultados) or {}
    veredicto = datos.get("veredicto", "Depende")
    regla = datos.get("regla", "")
    cuerpo = f"*{veredicto}.* {regla}"
    aclaracion = "\n".join(
        f"⚠️ {a}" for r in resultados for a in r.advertencias if a.startswith("No se cuenta con")
    )
    return _unir_secciones(
        cuerpo, aclaracion, _seccion_fuentes(_todas_las_citas(resultados))
    )


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
        "verificar productos registrados en SENASA, responder dudas sobre la normativa "
        "de aplicación de las localidades cargadas, y registrar/consultar tus "
        "aplicaciones en el campo. ¿Me mandás una receta o una consulta sobre eso?"
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


# --- consulta_vehiculo (Fase 9) ---


def _plantilla_consulta_vehiculo(
    respuesta: RespuestaAgente, resultados: list[ResultadoTool]
) -> str:
    datos = _primer_dato(resultados) or {}
    vehiculo = datos.get("vehiculo", "(sin identificar)")
    tipo_aplic = datos.get("tipo_aplicacion", "")
    return f"*Vehículo:* {vehiculo}" + (f" ({tipo_aplic})" if tipo_aplic else "")


# --- evento_registrado (Fase 9) ---


def _plantilla_evento_registrado(
    respuesta: RespuestaAgente, resultados: list[ResultadoTool]
) -> str:
    datos = _primer_dato(resultados) or {}
    resultado = resultados[0] if resultados else None

    if resultado is not None and resultado.estado == "observado":
        lineas = ["⚠️ *Ya hay una aplicación en curso*"]
        lineas.extend(f"- {a}" for a in resultado.advertencias)
        return "\n".join(lineas)

    if datos.get("fecha_fin"):
        lineas = ["✅ *Aplicación finalizada*"]
        if datos.get("lote"):
            lineas.append(f"- *Lote:* {datos['lote']}")
        lineas.append(f"- *Inicio:* {datos.get('fecha_inicio', 'no figura')}")
        lineas.append(f"- *Fin:* {datos['fecha_fin']}")
        return "\n".join(lineas)

    lineas = ["✅ *Aplicación iniciada*"]
    if datos.get("vehiculo"):
        lineas.append(f"- *Vehículo:* {datos['vehiculo']}")
    if datos.get("lote"):
        lineas.append(f"- *Lote:* {datos['lote']}")
    lineas.append(f"- *Inicio:* {datos.get('fecha_inicio', 'no figura')}")
    return "\n".join(lineas)


# --- agenda (Fase 9) ---


def _plantilla_agenda(respuesta: RespuestaAgente, resultados: list[ResultadoTool]) -> str:
    datos = _primer_dato(resultados) or {}
    fecha = datos.get("fecha", "")
    tareas = datos.get("tareas", [])

    if not tareas:
        if fecha:
            return f"No tenés tareas agendadas para el {datos.get('fecha_legible') or fecha}."
        return "No tenés tareas agendadas."

    fecha = datos.get("fecha_legible") or fecha
    return "\n".join([f"*Agenda del {fecha}* ({len(tareas)})"] + _lineas_agenda(tareas))


# --- ayuda ---


def _plantilla_ayuda(respuesta: RespuestaAgente, resultados: list[ResultadoTool]) -> str:
    return (
        "Hola 👋 Soy el asistente de recetas fitosanitarias. Puedo:\n"
        "- Leer una foto de tu receta y decirte si es apta para aplicar.\n"
        "- Buscar si un producto está registrado en SENASA.\n"
        "- Responder dudas sobre la normativa de aplicación de tu localidad.\n"
        "- Registrar cuando empezás y terminás de aplicar.\n"
        "- Contarte tu agenda del día.\n"
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
    "consulta_vehiculo": _plantilla_consulta_vehiculo,
    "evento_registrado": _plantilla_evento_registrado,
    "agenda": _plantilla_agenda,
    "detalle_bandas": _plantilla_detalle_bandas,
    "agendar_aplicacion": _plantilla_agendar_aplicacion,
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
    if respuesta.intro and respuesta.tipo not in (
        "fuera_de_dominio", "ayuda", "error", "consulta_producto",
    ):
        texto = f"{respuesta.intro}\n\n{texto}"
    return partir_por_seccion(texto)
