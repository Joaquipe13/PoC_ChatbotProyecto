"""Los mensajes de esta tool: lo que pregunta, lo que avisa y cómo se le muestra
el resultado al operario (la plantilla del tipo de respuesta `agendar_aplicacion`)."""

from fitosanitarios.dominio.modelos import RespuestaAgente, ResultadoTool
from fitosanitarios.servicios.formato import lineas_agenda, unir_secciones

# --- preguntas y motivos de la tool ---

PREGUNTA_FECHA = "¿Para qué fecha querés agendar la aplicación?"
PREGUNTA_HORA = "¿En qué horario querés agendarla?"
MOTIVO_SIN_FECHA = "no se indicó la fecha"
MOTIVO_SIN_HORA = "no se indicó el horario"


def motivo_fecha_no_entendida(texto: str) -> str:
    return f"no entendí la fecha '{texto}'"


def motivo_fecha_pasada(fecha_legible: str) -> str:
    return f"{fecha_legible} ya pasó"


def motivo_hora_no_entendida(texto: str) -> str:
    return f"no entendí el horario '{texto}'"


def advertencia_choque(cultivo: str | None, lote: str | None, hora: str) -> str:
    return (
        f"Ya tenías {cultivo or 'una tarea'} (lote {lote or 'sin lote'}) "
        f"agendada a las {hora}"
    )


def resumen_para_llm(estado: str, fecha_iso: str | None) -> str:
    """Lo único que ve el LLM de la tool: la fecha ya resuelta viaja acá para que
    el turno siguiente (el horario) la reutilice tal cual."""
    resumen = f"agendar_aplicacion: {estado}"
    if fecha_iso:
        resumen += f", fecha={fecha_iso}"
    return resumen


# --- plantilla del resultado (tipo de respuesta `agendar_aplicacion`) ---

_SIN_FALTANTE = "No pude agendar la aplicación. ¿Me decís de nuevo el día y el horario?"
_EJEMPLOS_HORA = "Por ejemplo: 8:30 o 3 de la tarde."
_EJEMPLOS_FECHA = (
    "Podés decirme un día (por ejemplo \"martes\" o \"mañana\") o una fecha (por ejemplo 25/09)."
)


def plantilla_agendar_aplicacion(
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
        return _SIN_FALTANTE

    if faltante.campo == "hora":
        tareas = datos.get("tareas", [])
        if tareas:
            agenda = "\n".join(
                [f"*Agenda del {datos['fecha_legible']}* ({len(tareas)})"] + lineas_agenda(tareas)
            )
        else:
            agenda = f"No tenés nada agendado para el {datos['fecha_legible']}."
        return unir_secciones(agenda, f"{faltante.pregunta_sugerida} {_EJEMPLOS_HORA}")

    aviso = ""
    if not faltante.motivo.startswith("no se indicó"):
        aviso = f"{faltante.motivo[0].upper()}{faltante.motivo[1:]}. "
    return f"{aviso}{faltante.pregunta_sugerida} {_EJEMPLOS_FECHA}"
