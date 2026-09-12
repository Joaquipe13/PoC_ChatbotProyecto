"""Tool `consultar_agenda` (Fase 9, RF9 en la numeración del usuario):
devuelve las tareas del día (o de la fecha pedida) de un operario, con su
estado (pendiente/en_curso/finalizada). Igual que `registrar_evento`, lee
`thread_id` de un `config: RunnableConfig` inyectado, no del LLM (ver
`tools/registrar_evento.py` para la justificación completa)."""

from datetime import date, datetime

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pydantic import BaseModel

from fitosanitarios.dominio.modelos import ResultadoTool
from fitosanitarios.servicios.eventos import consultar_agenda_logica
from fitosanitarios.tools.registrar_evento import thread_id_de_config


class ConsultarAgendaArgs(BaseModel):
    fecha: str | None = None  # ISO "AAAA-MM-DD"; None = hoy, resuelto en código


def _resolver_fecha(fecha_str: str | None) -> date:
    if fecha_str is None:
        return date.today()
    return datetime.strptime(fecha_str, "%Y-%m-%d").date()


def consultar_agenda_tool_logica(args: ConsultarAgendaArgs, conn, thread_id: str) -> ResultadoTool:
    fecha = _resolver_fecha(args.fecha)
    tareas = consultar_agenda_logica(conn, thread_id, fecha)
    return ResultadoTool(
        estado="ok", datos={"fecha": fecha.isoformat(), "tareas": tareas, "total": len(tareas)}
    )


@tool("consultar_agenda", args_schema=ConsultarAgendaArgs, response_format="content_and_artifact")
def consultar_agenda(config: RunnableConfig, fecha: str | None = None) -> tuple[str, ResultadoTool]:
    """Devuelve las tareas del operario para un día (recetas con fecha
    prevista para ese día, con su estado). Usar cuando pide su agenda o plan
    del día ("¿qué tengo para hoy?", "¿qué me toca aplicar mañana?").

    Args:
        fecha: fecha en formato AAAA-MM-DD, solo si el operario pidió un día
            específico distinto de hoy; si no lo dijo, no completar este
            argumento (se usa hoy por defecto).
    """
    from fitosanitarios.tools._recursos import con_conexion

    args = ConsultarAgendaArgs(fecha=fecha)
    thread_id = thread_id_de_config(config)
    resultado = con_conexion(lambda conn: consultar_agenda_tool_logica(args, conn, thread_id))
    return f"consultar_agenda: {resultado.datos['total']} tareas", resultado
