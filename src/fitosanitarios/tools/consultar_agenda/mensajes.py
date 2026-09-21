"""Los mensajes de esta tool: lo que pregunta y cómo se le muestra la agenda al
operario (la plantilla del tipo de respuesta `agenda`)."""

from fitosanitarios.dominio.modelos import RespuestaAgente, ResultadoTool
from fitosanitarios.servicios.formato import lineas_agenda, primer_dato

PREGUNTA_FECHA = "¿De qué día querés ver la agenda?"


def motivo_fecha_no_entendida(texto: str) -> str:
    return f"no entendí la fecha '{texto}'"


def resumen_para_llm(total: int) -> str:
    return f"consultar_agenda: {total} tareas"


def plantilla_agenda(respuesta: RespuestaAgente, resultados: list[ResultadoTool]) -> str:
    datos = primer_dato(resultados) or {}
    fecha = datos.get("fecha", "")
    tareas = datos.get("tareas", [])

    if not tareas:
        if fecha:
            return f"No tenés tareas agendadas para el {datos.get('fecha_legible') or fecha}."
        return "No tenés tareas agendadas."

    fecha = datos.get("fecha_legible") or fecha
    return "\n".join([f"*Agenda del {fecha}* ({len(tareas)})"] + lineas_agenda(tareas))
