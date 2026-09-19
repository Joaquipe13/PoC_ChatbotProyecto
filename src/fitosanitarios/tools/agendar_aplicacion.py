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
from fitosanitarios.servicios.agendamiento import agendar_aplicacion as agendar
from fitosanitarios.servicios.eventos import consultar_agenda_logica
from fitosanitarios.servicios.fechas import (
    fecha_legible,
    hora_legible,
    resolver_fecha,
    resolver_hora,
)
from fitosanitarios.tools.registrar_evento import thread_id_de_config


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
                campo="fecha", motivo=motivo,
                pregunta_sugerida="¿Para qué fecha querés agendar la aplicación?",
                tipo_entrada="texto",
            )
        ],
    )


def agendar_aplicacion_logica(
    args: AgendarAplicacionArgs, conn, thread_id: str, hoy: date | None = None
) -> ResultadoTool:
    hoy = hoy or date.today()

    if not args.fecha:
        return _pedir_fecha("no se indicó la fecha")
    fecha = resolver_fecha(args.fecha, hoy)
    if fecha is None:
        return _pedir_fecha(f"no entendí la fecha '{args.fecha}'")
    if fecha < hoy:
        return _pedir_fecha(f"{fecha_legible(fecha)} ya pasó")

    hora = resolver_hora(args.hora) if args.hora else None
    if hora is None:
        tareas = consultar_agenda_logica(conn, thread_id, fecha)
        motivo = f"no entendí el horario '{args.hora}'" if args.hora else "no se indicó el horario"
        return ResultadoTool(
            estado="faltan_datos",
            datos={
                "fecha": fecha.isoformat(), "fecha_legible": fecha_legible(fecha),
                "tareas": tareas,
            },
            faltantes=[
                CampoFaltante(
                    campo="hora", motivo=motivo,
                    pregunta_sugerida="¿En qué horario querés agendarla?",
                    tipo_entrada="texto",
                )
            ],
        )

    receta_id, choques = agendar(
        conn, thread_id, fecha, hora,
        {
            "numero": args.numero, "cultivo": args.cultivo, "lote": args.lote,
            "superficie_ha": args.superficie_ha, "tipo_aplicacion": args.tipo_aplicacion,
        },
    )
    advertencias = [
        f"Ya tenías {t.get('cultivo') or 'una tarea'} (lote {t.get('lote') or 'sin lote'}) "
        f"agendada a las {hora_legible(hora)}"
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
    response_format="content_and_artifact",
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
    """Agenda la aplicación de la receta en la agenda del operario. Usar
    cuando pide agendar ("agendala", "sí, agendala", "agendala para el
    martes"). La tool pregunta lo que falta: no inventes ni calcules fechas.

    Args:
        fecha: el día tal como lo dijo el operario ("martes", "mañana",
            "25/09"), sin convertirlo. Si no dijo ninguno, no completar. Si
            una respuesta anterior de esta tool informó `fecha=AAAA-MM-DD`,
            pasar esa fecha.
        hora: el horario tal como lo dijo ("8", "8:30", "3 de la tarde"). Si
            no lo dijo, no completar.
        numero: número de la receta, si se conoce.
        cultivo: cultivo de la receta, si se conoce.
        lote: lote de la receta, si se conoce.
        superficie_ha: superficie en hectáreas, si se conoce.
        tipo_aplicacion: "terrestre" o "aerea", si se conoce.
    """
    from fitosanitarios.tools._recursos import con_conexion

    args = AgendarAplicacionArgs(
        fecha=fecha, hora=hora, numero=numero, cultivo=cultivo, lote=lote,
        superficie_ha=superficie_ha, tipo_aplicacion=tipo_aplicacion,
    )
    thread_id = thread_id_de_config(config)
    resultado = con_conexion(lambda conn: agendar_aplicacion_logica(args, conn, thread_id))
    fecha_iso = (resultado.datos or {}).get("fecha")
    # La fecha ya resuelta viaja en el resumen: es lo único que ve el LLM, y
    # el turno siguiente (el horario) tiene que reutilizarla tal cual.
    resumen = f"agendar_aplicacion: {resultado.estado}"
    if fecha_iso:
        resumen += f", fecha={fecha_iso}"
    return resumen, resultado
