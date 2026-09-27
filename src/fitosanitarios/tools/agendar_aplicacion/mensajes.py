"""Los mensajes de esta tool: lo que pregunta, lo que avisa y cómo se le muestra
el resultado al operario (la plantilla del tipo de respuesta `agendar_aplicacion`)."""

from fitosanitarios.dominio.modelos import Cita, RespuestaAgente, ResultadoTool
from fitosanitarios.servicios.formato import cita_norma, lineas_agenda, num, unir_secciones

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
        f"Ya tenías {cultivo or 'una tarea'} ({f'lote {lote}' if lote else 'sin lote'}) "
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


_VERIFICAR = "Es un pronóstico: verificá el viento en el lote antes de empezar."


def _rango(minimo, maximo, unidad: str) -> str:
    if minimo is None or maximo is None:
        return "no figura"
    if round(minimo) == round(maximo):
        return f"{num(round(maximo))} {unidad}"
    return f"{num(round(minimo))} a {num(round(maximo))} {unidad}"


def seccion_pronostico(pronostico: dict | None, fecha_legible: str) -> str:
    """El pronóstico de la franja agendada, como información (no controla nada). La norma
    de viento de la localidad, si el viento pronosticado supera su umbral, va como
    referencia."""
    if not pronostico:
        return ""
    if pronostico["estado"] == "lejano":
        return (
            f"🌤️ Todavía no hay un pronóstico confiable para el {fecha_legible}: se muestra "
            f"a partir de {pronostico['horizonte_dias']} días antes."
        )
    if pronostico["estado"] != "ok":
        return "🌤️ No pude consultar el pronóstico del tiempo."

    p = pronostico
    lineas = [
        f"*Pronóstico en {p['localidad']}, de {p['desde']} a {p['hasta']}* "
        f"(Open-Meteo, consultado el {p['consultado']})"
    ]
    viento = _rango(p["viento_min_kmh"], p["viento_max_kmh"], "km/h")
    if p.get("viene_de"):
        viento = f"del {p['viene_de']} (empuja hacia el {p['empuja_hacia']}), {viento}"
    if p.get("rafagas_max_kmh") is not None:
        viento += f", ráfagas de hasta {num(round(p['rafagas_max_kmh']))} km/h"
    lineas.append(f"- Viento {viento}")
    if p.get("lluvia_mm") is not None:
        lluvia = f"- Lluvia: {num(p['lluvia_mm'])} mm"
        if p.get("lluvia_probabilidad_max") is not None:
            lluvia += f" (probabilidad de hasta {num(p['lluvia_probabilidad_max'])} %)"
        lineas.append(lluvia)
    clima = f"- Temperatura: {_rango(p['temperatura_min'], p['temperatura_max'], '°C')}"
    if p.get("humedad_min") is not None:
        clima += f" · humedad desde {num(p['humedad_min'])} %"
    lineas.append(clima)
    for n in p.get("normas") or []:
        cita = cita_norma(Cita(fuente="normativa", norma=n["norma"], articulo=n["articulo"]))
        lineas.append(f"📋 {cita}: {n['descripcion']}.")
    lineas.append(_VERIFICAR)
    return "\n".join(lineas)


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
        return unir_secciones(
            "\n".join(lineas),
            seccion_pronostico(datos.get("pronostico"), datos["fecha_legible"]),
        )

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
