"""Tool `registrar_evento` (Fase 9, RF7): registra el inicio o el fin de una
aplicación real en el campo, asociada a receta, vehículo y lote.

Necesita saber "de quién" es el turno para encontrar/cerrar el evento en
curso del operario correcto: lee `thread_id` de un parámetro
`config: RunnableConfig` que LangGraph le inyecta a la tool automáticamente
(el mismo `config={"configurable": {"thread_id": ...}}` que
`orquestador/turno.py::ejecutar_turno` ya arma para el checkpointer) sin
exponerlo en el schema que ve el LLM -- confirmado leyendo
`langchain_core/tools/base.py::_find_config_param` y con
`tests/orquestador/test_ruteo.py::test_ruteo_registrar_evento_usa_el_thread_id_del_turno`."""

from typing import Literal

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pydantic import BaseModel

from fitosanitarios.dominio.modelos import CampoFaltante, ResultadoTool
from fitosanitarios.servicios.eventos import finalizar_evento, iniciar_evento
from fitosanitarios.servicios.resolucion_vehiculo import resolver_vehiculo as resolver_vehiculo_srv


class RegistrarEventoArgs(BaseModel):
    accion: Literal["iniciar", "finalizar"]
    vehiculo: str | None = None
    lote: str | None = None
    receta_id: int | None = None


def thread_id_de_config(config: RunnableConfig | None) -> str:
    thread_id = (config or {}).get("configurable", {}).get("thread_id")
    if not thread_id:
        raise ValueError("registrar_evento necesita un thread_id en el config del turno")
    return thread_id


def registrar_evento_logica(args: RegistrarEventoArgs, conn, thread_id: str) -> ResultadoTool:
    if args.accion == "finalizar":
        resultado = finalizar_evento(conn, thread_id)
        if resultado.motivo_no_resuelto is not None:
            return ResultadoTool(estado="no_resuelto", motivo=resultado.motivo_no_resuelto)
        fecha_inicio = resultado.fecha_inicio.isoformat() if resultado.fecha_inicio else None
        fecha_fin = resultado.fecha_fin.isoformat() if resultado.fecha_fin else None
        datos = {"lote": resultado.lote, "fecha_inicio": fecha_inicio, "fecha_fin": fecha_fin}
        return ResultadoTool(estado="ok", datos=datos)

    faltantes = []
    if not args.vehiculo:
        faltantes.append(
            CampoFaltante(
                campo="vehiculo", motivo="no se indicó qué vehículo se usa",
                pregunta_sugerida="¿Con qué vehículo vas a aplicar?", tipo_entrada="texto",
            )
        )
    if not args.lote:
        faltantes.append(
            CampoFaltante(
                campo="lote", motivo="no se indicó el lote",
                pregunta_sugerida="¿En qué lote vas a aplicar?", tipo_entrada="texto",
            )
        )
    if faltantes:
        return ResultadoTool(estado="faltan_datos", faltantes=faltantes)

    resolucion = resolver_vehiculo_srv(conn, args.vehiculo)
    resultado = iniciar_evento(conn, thread_id, resolucion, args.lote, args.receta_id)

    if resultado.motivo_no_resuelto is not None:
        return ResultadoTool(estado="no_resuelto", motivo=resultado.motivo_no_resuelto)
    if resultado.opciones_ambiguas is not None:
        return ResultadoTool(
            estado="faltan_datos",
            faltantes=[
                CampoFaltante(
                    campo="vehiculo",
                    motivo="la descripción no coincide con ningún vehículo del catálogo",
                    pregunta_sugerida="¿Cuál de estos vehículos es?",
                    tipo_entrada="lista",
                    opciones=resultado.opciones_ambiguas,
                )
            ],
        )
    if resultado.ya_en_curso:
        return ResultadoTool(
            estado="observado",
            datos={"lote": resultado.lote, "fecha_inicio": resultado.fecha_inicio.isoformat()},
            advertencias=[
                f"ya hay una aplicación en curso desde {resultado.fecha_inicio.isoformat()} "
                f"en el lote {resultado.lote}; registrá que la terminaste antes de iniciar otra"
            ],
        )

    return ResultadoTool(
        estado="ok",
        datos={
            "vehiculo": resultado.vehiculo.nombre,
            "lote": resultado.lote,
            "fecha_inicio": resultado.fecha_inicio.isoformat(),
        },
    )


@tool("registrar_evento", args_schema=RegistrarEventoArgs, response_format="content_and_artifact")
def registrar_evento(
    accion: Literal["iniciar", "finalizar"],
    config: RunnableConfig,
    vehiculo: str | None = None,
    lote: str | None = None,
    receta_id: int | None = None,
) -> tuple[str, ResultadoTool]:
    """Registra el inicio o el fin de una aplicación real en el campo. Usar
    "iniciar" cuando el operario avisa que va a empezar o está empezando a
    aplicar (con qué vehículo y en qué lote); usar "finalizar" cuando avisa
    que terminó. No confundir con el dictamen (`evaluar_viabilidad_legal`):
    esto registra que se aplicó, no evalúa si es viable aplicar.

    Args:
        accion: "iniciar" o "finalizar".
        vehiculo: con qué vehículo/equipo aplica, tal cual lo describió
            (requerido solo para "iniciar").
        lote: el lote donde aplica (requerido solo para "iniciar").
        receta_id: si esta aplicación corresponde a una receta ya evaluada,
            su id (opcional).
    """
    from fitosanitarios.tools._recursos import con_conexion

    args = RegistrarEventoArgs(accion=accion, vehiculo=vehiculo, lote=lote, receta_id=receta_id)
    thread_id = thread_id_de_config(config)
    resultado = con_conexion(lambda conn: registrar_evento_logica(args, conn, thread_id))
    return f"registrar_evento: accion={accion} estado={resultado.estado}", resultado
