"""Tool `consultar_agenda` (Fase 9, RF9 en la numeración del usuario):
devuelve las tareas del día (o de la fecha pedida) de un operario, con su
estado (pendiente/en_curso/finalizada). Igual que `registrar_evento`, lee
`thread_id` de un `config: RunnableConfig` inyectado, no del LLM (ver
`servicios/conversacion.py`)."""

from datetime import date

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pydantic import BaseModel

from fitosanitarios.dominio.modelos import CampoFaltante, ResultadoTool
from fitosanitarios.servicios.conversacion import thread_id_de_config
from fitosanitarios.servicios.eventos import consultar_agenda_logica
from fitosanitarios.servicios.fechas import fecha_legible, resolver_fecha
from fitosanitarios.tools.consultar_agenda import mensajes
from fitosanitarios.tools.consultar_agenda.prompts import DESCRIPCION


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
                    campo="fecha", motivo=mensajes.motivo_fecha_no_entendida(args.fecha),
                    pregunta_sugerida=mensajes.PREGUNTA_FECHA, tipo_entrada="texto",
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


@tool(
    "consultar_agenda",
    args_schema=ConsultarAgendaArgs,
    description=DESCRIPCION,
    response_format="content_and_artifact",
    return_direct=True,  # ver `orquestador/respuesta_directa.py`
)
def consultar_agenda(config: RunnableConfig, fecha: str | None = None) -> tuple[str, ResultadoTool]:
    from fitosanitarios.servicios.recursos import con_conexion

    args = ConsultarAgendaArgs(fecha=fecha)
    thread_id = thread_id_de_config(config)
    resultado = con_conexion(lambda conn: consultar_agenda_tool_logica(args, conn, thread_id))
    total = resultado.datos["total"] if resultado.datos else 0
    return mensajes.resumen_para_llm(total), resultado
