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
from fitosanitarios.servicios.conversacion import thread_id_de_config
from fitosanitarios.servicios.eventos import finalizar_evento, iniciar_evento
from fitosanitarios.servicios.resolucion_vehiculo import (
    faltante_vehiculo_no_identificado,
)
from fitosanitarios.servicios.resolucion_vehiculo import resolver_vehiculo as resolver_vehiculo_srv
from fitosanitarios.tools.registrar_evento import mensajes
from fitosanitarios.tools.registrar_evento.prompts import DESCRIPCION


class RegistrarEventoArgs(BaseModel):
    accion: Literal["iniciar", "finalizar"]
    vehiculo: str | None = None
    lote: str | None = None
    receta_id: int | None = None


def registrar_evento_logica(
    args: RegistrarEventoArgs, conn, modelo_embeddings, thread_id: str
) -> ResultadoTool:
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
                campo="vehiculo", motivo=mensajes.MOTIVO_SIN_VEHICULO,
                pregunta_sugerida=mensajes.PREGUNTA_VEHICULO, tipo_entrada="texto",
            )
        )
    if not args.lote:
        faltantes.append(
            CampoFaltante(
                campo="lote", motivo=mensajes.MOTIVO_SIN_LOTE,
                pregunta_sugerida=mensajes.PREGUNTA_LOTE, tipo_entrada="texto",
            )
        )
    if faltantes:
        return ResultadoTool(estado="faltan_datos", faltantes=faltantes)

    resolucion = resolver_vehiculo_srv(conn, modelo_embeddings, args.vehiculo)
    resultado = iniciar_evento(conn, thread_id, resolucion, args.lote, args.receta_id)

    if resultado.motivo_no_resuelto is not None:
        return ResultadoTool(estado="no_resuelto", motivo=resultado.motivo_no_resuelto)
    if resultado.opciones_ambiguas is not None:
        return ResultadoTool(
            estado="faltan_datos",
            faltantes=[
                faltante_vehiculo_no_identificado(args.vehiculo, resultado.opciones_ambiguas)
            ],
        )
    if resultado.ya_en_curso:
        return ResultadoTool(
            estado="observado",
            datos={"lote": resultado.lote, "fecha_inicio": resultado.fecha_inicio.isoformat()},
            advertencias=[
                mensajes.advertencia_ya_en_curso(resultado.fecha_inicio.isoformat(), resultado.lote)
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


@tool(
    "registrar_evento",
    args_schema=RegistrarEventoArgs,
    description=DESCRIPCION,
    response_format="content_and_artifact",
)
def registrar_evento(
    accion: Literal["iniciar", "finalizar"],
    config: RunnableConfig,
    vehiculo: str | None = None,
    lote: str | None = None,
    receta_id: int | None = None,
) -> tuple[str, ResultadoTool]:
    from fitosanitarios.servicios.recursos import con_conexion_y_modelo

    args = RegistrarEventoArgs(accion=accion, vehiculo=vehiculo, lote=lote, receta_id=receta_id)
    thread_id = thread_id_de_config(config)
    resultado = con_conexion_y_modelo(
        lambda conn, modelo: registrar_evento_logica(args, conn, modelo, thread_id)
    )
    return mensajes.resumen_para_llm(accion, resultado.estado), resultado
