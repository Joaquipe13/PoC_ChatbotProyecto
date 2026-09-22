"""Tool `agendar_aplicacion`: agenda una aplicación en la agenda del operario,
pidiendo primero la fecha y después el horario.

Flujo (lo decide el código, no el LLM):
- sin fecha -> pregunta la fecha;
- con fecha y sin hora -> muestra la agenda de ese día y pregunta el horario;
- con fecha y hora -> agenda, avisando si ya hay algo a esa hora.

La fecha y la hora llegan como texto del operario ("martes", "mañana",
"25/09", "8:30") y se resuelven en `servicios/fechas.py`: el LLM no calcula
fechas. Igual que `registrar_evento`, el `thread_id` sale del `config`.
"""

from datetime import date

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pydantic import BaseModel

from fitosanitarios.dominio.modelos import CampoFaltante, ResultadoTool
from fitosanitarios.servicios.conversacion import thread_id_de_config
from fitosanitarios.servicios.eventos import consultar_agenda_logica
from fitosanitarios.servicios.fechas import (
    fecha_legible,
    hora_legible,
    resolver_fecha,
    resolver_hora,
)
from fitosanitarios.servicios.reglas import normalizar_tipo_aplicacion
from fitosanitarios.tools.agendar_aplicacion import mensajes
from fitosanitarios.tools.agendar_aplicacion.prompts import DESCRIPCION
from fitosanitarios.tools.agendar_aplicacion.utils import agendar_aplicacion as agendar


class AgendarAplicacionArgs(BaseModel):
    fecha: str | None = None
    hora: str | None = None
    # Datos de la receta que se agenda, tal como figuran en la conversación.
    numero: str | None = None
    cultivo: str | None = None
    lote: str | None = None
    superficie_ha: float | None = None
    tipo_aplicacion: str | None = None


def _pedir_fecha(motivo: str) -> ResultadoTool:
    return ResultadoTool(
        estado="faltan_datos",
        faltantes=[
            CampoFaltante(
                campo="fecha", motivo=motivo, pregunta_sugerida=mensajes.PREGUNTA_FECHA,
                tipo_entrada="texto",
            )
        ],
    )


def agendar_aplicacion_logica(
    args: AgendarAplicacionArgs, conn, thread_id: str, hoy: date | None = None
) -> ResultadoTool:
    hoy = hoy or date.today()

    if not args.fecha:
        return _pedir_fecha(mensajes.MOTIVO_SIN_FECHA)
    fecha = resolver_fecha(args.fecha, hoy)
    if fecha is None:
        return _pedir_fecha(mensajes.motivo_fecha_no_entendida(args.fecha))
    if fecha < hoy:
        return _pedir_fecha(mensajes.motivo_fecha_pasada(fecha_legible(fecha)))

    hora = resolver_hora(args.hora) if args.hora else None
    if hora is None:
        tareas = consultar_agenda_logica(conn, thread_id, fecha)
        motivo = (
            mensajes.motivo_hora_no_entendida(args.hora) if args.hora
            else mensajes.MOTIVO_SIN_HORA
        )
        return ResultadoTool(
            estado="faltan_datos",
            datos={
                "fecha": fecha.isoformat(), "fecha_legible": fecha_legible(fecha),
                "tareas": tareas,
            },
            faltantes=[
                CampoFaltante(
                    campo="hora", motivo=motivo, pregunta_sugerida=mensajes.PREGUNTA_HORA,
                    tipo_entrada="texto",
                )
            ],
        )

    receta_id, choques = agendar(
        conn, thread_id, fecha, hora,
        {
            "numero": args.numero, "cultivo": args.cultivo, "lote": args.lote,
            "superficie_ha": args.superficie_ha, "tipo_aplicacion": (
                normalizar_tipo_aplicacion(args.tipo_aplicacion) or args.tipo_aplicacion
            ),
        },
    )
    advertencias = [
        mensajes.advertencia_choque(t.get("cultivo"), t.get("lote"), hora_legible(hora))
        for t in choques
    ]
    return ResultadoTool(
        estado="ok",
        datos={
            "receta_id": receta_id, "fecha": fecha.isoformat(),
            "fecha_legible": fecha_legible(fecha), "hora": hora_legible(hora),
            "cultivo": args.cultivo, "lote": args.lote,
        },
        advertencias=advertencias,
    )


@tool(
    "agendar_aplicacion",
    args_schema=AgendarAplicacionArgs,
    description=DESCRIPCION,
    response_format="content_and_artifact",
    return_direct=True,  # ver `orquestador/respuesta_directa.py`
)
def agendar_aplicacion(
    config: RunnableConfig,
    fecha: str | None = None,
    hora: str | None = None,
    numero: str | None = None,
    cultivo: str | None = None,
    lote: str | None = None,
    superficie_ha: float | None = None,
    tipo_aplicacion: str | None = None,
) -> tuple[str, ResultadoTool]:
    from fitosanitarios.servicios.recursos import con_conexion

    args = AgendarAplicacionArgs(
        fecha=fecha, hora=hora, numero=numero, cultivo=cultivo, lote=lote,
        superficie_ha=superficie_ha, tipo_aplicacion=tipo_aplicacion,
    )
    thread_id = thread_id_de_config(config)
    resultado = con_conexion(lambda conn: agendar_aplicacion_logica(args, conn, thread_id))
    fecha_iso = (resultado.datos or {}).get("fecha")
    return mensajes.resumen_para_llm(resultado.estado, fecha_iso), resultado
