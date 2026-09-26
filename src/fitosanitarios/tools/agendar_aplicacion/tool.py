"""Tool `agendar_aplicacion`: agenda una aplicación en la agenda del operario,
pidiendo primero la fecha y después el horario.

Flujo (lo decide el código, no el LLM):
- sin fecha -> pregunta la fecha;
- con fecha y sin hora -> muestra la agenda de ese día y pregunta el horario;
- con fecha y hora -> agenda, avisando si ya hay algo a esa hora.

La fecha y la hora llegan como texto del operario ("martes", "mañana",
"25/09", "8:30") y se resuelven en `servicios/fechas.py`: el LLM no calcula
fechas. Igual que `registrar_evento`, el `thread_id` sale del `config`.

Al agendar, si se conoce la localidad y la fecha está dentro del horizonte, se suma el
pronóstico del tiempo de esa franja (ver DECISIONES.md, "Pronóstico del tiempo al
agendar"). Es información: si no se puede obtener, se agenda igual.
"""

from datetime import date, datetime, time

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pydantic import BaseModel

from fitosanitarios.datos.retrievers.territorio import (
    centro_de_localidad,
    listar_localidades,
    reglas_de_viento,
)
from fitosanitarios.dominio.modelos import CampoFaltante, ResultadoTool
from fitosanitarios.servicios.conversacion import thread_id_de_config
from fitosanitarios.servicios.eventos import consultar_agenda_logica
from fitosanitarios.servicios.fechas import (
    fecha_legible,
    hora_legible,
    resolver_fecha,
    resolver_hora,
)
from fitosanitarios.servicios.localidad import resolver_localidad
from fitosanitarios.servicios.meteorologia import franja
from fitosanitarios.servicios.reglas import normalizar_tipo_aplicacion
from fitosanitarios.servicios.viento import resumen_pronostico
from fitosanitarios.tools.agendar_aplicacion import mensajes
from fitosanitarios.tools.agendar_aplicacion.prompts import DESCRIPCION
from fitosanitarios.tools.agendar_aplicacion.utils import agendar_aplicacion as agendar
from fitosanitarios.tools.agendar_aplicacion.utils import guardar_pronostico


class AgendarAplicacionArgs(BaseModel):
    fecha: str | None = None
    hora: str | None = None
    localidad: str | None = None  # para el pronóstico del tiempo
    # Datos de la receta que se agenda, tal como figuran en la conversación.
    numero: str | None = None
    cultivo: str | None = None
    lote: str | None = None
    superficie_ha: float | None = None
    tipo_aplicacion: str | None = None


def _pronostico(
    conn, texto_localidad: str | None, fecha: date, hora: time, hoy: date,
    cliente_meteo, horizonte_dias: int,
) -> dict | None:
    """El pronóstico de la franja agendada, o `None` si no hay nada que mostrar (sin
    localidad reconocida, sin cliente o sin coordenadas cargadas)."""
    if cliente_meteo is None or not texto_localidad or not texto_localidad.strip():
        return None
    localidad = resolver_localidad(texto_localidad, listar_localidades(conn)).localidad
    if localidad is None:
        return None
    base = {"localidad": localidad.nombre}
    if (fecha - hoy).days > horizonte_dias:
        return {**base, "estado": "lejano", "horizonte_dias": horizonte_dias}
    centro = centro_de_localidad(conn, localidad.id)
    if centro is None:
        return None
    horas = cliente_meteo.horas_del_dia(centro[0], centro[1], fecha)
    resumen = resumen_pronostico(
        franja(horas or [], datetime.combine(fecha, hora)),
        reglas_de_viento(conn, localidad.id, localidad.provincia_id),
    )
    if resumen is None:
        return {**base, "estado": "sin_datos"}
    return {
        **base, "estado": "ok", **resumen,
        "consultado": datetime.now().strftime("%d/%m %H:%M"),
    }


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
    args: AgendarAplicacionArgs, conn, thread_id: str, hoy: date | None = None,
    cliente_meteo=None, horizonte_dias: int = 5,
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
    pronostico = _pronostico(
        conn, args.localidad, fecha, hora, hoy, cliente_meteo, horizonte_dias
    )
    if pronostico is not None and pronostico["estado"] == "ok":
        guardar_pronostico(conn, receta_id, pronostico)
    return ResultadoTool(
        estado="ok",
        datos={
            "receta_id": receta_id, "fecha": fecha.isoformat(),
            "fecha_legible": fecha_legible(fecha), "hora": hora_legible(hora),
            "cultivo": args.cultivo, "lote": args.lote, "pronostico": pronostico,
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
    localidad: str | None = None,
    numero: str | None = None,
    cultivo: str | None = None,
    lote: str | None = None,
    superficie_ha: float | None = None,
    tipo_aplicacion: str | None = None,
) -> tuple[str, ResultadoTool]:
    from fitosanitarios.config import get_settings
    from fitosanitarios.servicios.recursos import cliente_meteorologia, con_conexion

    args = AgendarAplicacionArgs(
        fecha=fecha, hora=hora, numero=numero, cultivo=cultivo, lote=lote,
        superficie_ha=superficie_ha, tipo_aplicacion=tipo_aplicacion, localidad=localidad,
    )
    thread_id = thread_id_de_config(config)
    settings = get_settings()
    resultado = con_conexion(lambda conn: agendar_aplicacion_logica(
        args, conn, thread_id, cliente_meteo=cliente_meteorologia(settings),
        horizonte_dias=settings.meteo_horizonte_dias,
    ))
    fecha_iso = (resultado.datos or {}).get("fecha")
    return mensajes.resumen_para_llm(resultado.estado, fecha_iso), resultado
