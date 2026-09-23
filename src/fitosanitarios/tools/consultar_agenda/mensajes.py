"""Los mensajes de esta tool: lo que pregunta y cómo se le muestra la agenda al
operario (la plantilla del tipo de respuesta `agenda`)."""

from fitosanitarios.dominio.modelos import RespuestaAgente, ResultadoTool
from fitosanitarios.servicios.formato import lineas_agenda, primer_dato

PREGUNTA_FECHA = "¿De qué día querés ver la agenda?"


def motivo_fecha_no_entendida(texto: str) -> str:
    return f"no entendí la fecha '{texto}'"


def resumen_para_llm(total: int) -> str:
    return f"consultar_agenda: {total} tareas"


def _plantilla_varios_dias(dias: list[dict]) -> str:
    """Un bloque por día, también los que no tienen tareas: así se ve que se miró
    cada día pedido."""
    total = sum(len(d["tareas"]) for d in dias)
    desde, hasta = dias[0]["fecha_legible"], dias[-1]["fecha_legible"]
    titulo = f"*Agenda del {desde} al {hasta}*"
    lineas = [titulo + (f" ({total})" if total else "")]
    for d in dias:
        nombre = d["fecha_legible"][0].upper() + d["fecha_legible"][1:]
        if d["tareas"]:
            lineas.append(f"*{nombre}:*")
            lineas.extend(lineas_agenda(d["tareas"]))
        else:
            lineas.append(f"*{nombre}:* sin tareas")
    return "\n".join(lineas)


def plantilla_agenda(respuesta: RespuestaAgente, resultados: list[ResultadoTool]) -> str:
    datos = primer_dato(resultados) or {}
    if len(datos.get("dias", [])) > 1:
        return _plantilla_varios_dias(datos["dias"])
    fecha = datos.get("fecha", "")
    tareas = datos.get("tareas", [])

    if not tareas:
        if fecha:
            return f"No tenés tareas agendadas para el {datos.get('fecha_legible') or fecha}."
        return "No tenés tareas agendadas."

    fecha = datos.get("fecha_legible") or fecha
    return "\n".join([f"*Agenda del {fecha}* ({len(tareas)})"] + lineas_agenda(tareas))
