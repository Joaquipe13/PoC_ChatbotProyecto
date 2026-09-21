"""Tool `resolver_vehiculo` (Fase 9, RF6): interpreta en lenguaje natural
qué vehículo/equipo de aplicación menciona el operario, contra
`catalogo.vehiculo` (ver skill, "Arquitectura": la tool valida entrada,
llama al servicio y devuelve `ResultadoTool`)."""

from langchain_core.tools import tool
from pydantic import BaseModel

from fitosanitarios.dominio.modelos import ResultadoTool
from fitosanitarios.servicios.resolucion_vehiculo import (
    faltante_vehiculo_no_identificado,
)
from fitosanitarios.servicios.resolucion_vehiculo import resolver_vehiculo as resolver_vehiculo_srv
from fitosanitarios.tools.resolver_vehiculo import mensajes
from fitosanitarios.tools.resolver_vehiculo.prompts import DESCRIPCION


class ResolverVehiculoArgs(BaseModel):
    descripcion: str


def resolver_vehiculo_logica(args: ResolverVehiculoArgs, conn, modelo_embeddings) -> ResultadoTool:
    resolucion = resolver_vehiculo_srv(conn, modelo_embeddings, args.descripcion)

    if resolucion.motivo_no_resuelto is not None:
        return ResultadoTool(estado="no_resuelto", motivo=resolucion.motivo_no_resuelto)

    if resolucion.opciones_ambiguas is not None:
        return ResultadoTool(
            estado="faltan_datos",
            faltantes=[
                faltante_vehiculo_no_identificado(args.descripcion, resolucion.opciones_ambiguas)
            ],
        )

    v = resolucion.vehiculo
    return ResultadoTool(
        estado="ok", datos={"vehiculo": v.nombre, "tipo_aplicacion": v.tipo_aplicacion}
    )


@tool(
    "resolver_vehiculo",
    args_schema=ResolverVehiculoArgs,
    description=DESCRIPCION,
    response_format="content_and_artifact",
)
def resolver_vehiculo(descripcion: str) -> tuple[str, ResultadoTool]:
    from fitosanitarios.servicios.recursos import con_conexion_y_modelo

    args = ResolverVehiculoArgs(descripcion=descripcion)
    resultado = con_conexion_y_modelo(
        lambda conn, modelo: resolver_vehiculo_logica(args, conn, modelo)
    )
    return mensajes.resumen_para_llm(resultado.estado), resultado
