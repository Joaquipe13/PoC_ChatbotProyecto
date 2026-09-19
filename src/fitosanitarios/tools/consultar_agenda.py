"""Tool `consultar_agenda` (Fase 9, RF9 en la numeración del usuario):
devuelve las tareas del día (o de la fecha pedida) de un operario, con su
estado (pendiente/en_curso/finalizada). Igual que `registrar_evento`, lee
`thread_id` de un `config: RunnableConfig` inyectado, no del LLM (ver
`tools/registrar_evento.py` para la justificación completa)."""

from datetime import date

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pydantic import BaseModel

from fitosanitarios.dominio.modelos import CampoFaltante, ResultadoTool
from fitosanitarios.servicios.eventos import consultar_agenda_logica
from fitosanitarios.servicios.fechas import fecha_legible, resolver_fecha
from fitosanitarios.tools.registrar_evento import thread_id_de_config


class ConsultarAgendaArgs(BaseModel):
    fecha: str | None = None  # texto del operario o ISO; None = hoy, resuelto en código


def consultar_agenda_tool_logica(
    args: ConsultarAgendaArgs, conn, thread_id: str, hoy: date | None = None
) -> ResultadoTool:
    hoy = hoy or date.today()
    fecha = resolver_fecha(args.fecha, hoy) if args.fecha else hoy
    if fecha is None:
        return ResultadoTool(
            estado="faltan_datos",
            faltantes=[
                CampoFaltante(
                    campo="fecha", motivo=f"no entendí la fecha '{args.fecha}'",
                    pregunta_sugerida="¿De qué día querés ver la agenda?",
                    tipo_entrada="texto",
                )
            ],
        )
    tareas = consultar_agenda_logica(conn, thread_id, fecha)
    return ResultadoTool(
        estado="ok",
        datos={
            "fecha": fecha.isoformat(), "fecha_legible": fecha_legible(fecha),
            "tareas": tareas, "total": len(tareas),
        },
    )


@tool("consultar_agenda", args_schema=ConsultarAgendaArgs, response_format="content_and_artifact")
def consultar_agenda(config: RunnableConfig, fecha: str | None = None) -> tuple[str, ResultadoTool]:
    """Devuelve las tareas del operario para un día (recetas con fecha
    prevista para ese día, con su estado). Usar cuando pide su agenda o plan
    del día ("¿qué tengo para hoy?", "¿qué me toca aplicar mañana?").

    Args:
        fecha: el día tal como lo dijo el operario ("martes", "mañana",
            "25/09"), sin convertirlo, solo si pidió uno distinto de hoy; si
            no lo dijo, no completar este argumento (se usa hoy por defecto).
    """
    from fitosanitarios.tools._recursos import con_conexion

    args = ConsultarAgendaArgs(fecha=fecha)
    thread_id = thread_id_de_config(config)
    resultado = con_conexion(lambda conn: consultar_agenda_tool_logica(args, conn, thread_id))
    total = resultado.datos["total"] if resultado.datos else 0
    return f"consultar_agenda: {total} tareas", resultado
