"""Tool `consultar_productos`: lista productos registrados por cultivo,
adversidad o principio activo. Informa lo registrado; no recomienda qué
aplicar (ver skill, tool `consultar_productos`)."""

from langchain_core.tools import tool
from pydantic import BaseModel, model_validator

from fitosanitarios.datos.retrievers.catalogo import (
    listar_productos_por_filtro,
    resolver_entidad_por_nombre,
)
from fitosanitarios.dominio.modelos import CampoFaltante, Cita, ResultadoTool
from fitosanitarios.tools.consultar_productos import mensajes
from fitosanitarios.tools.consultar_productos.prompts import DESCRIPCION
from fitosanitarios.tools.consultar_productos.utils import bandas_hasta


class ConsultarProductosArgs(BaseModel):
    cultivo: str | None = None
    adversidad: str | None = None
    principio_activo: str | None = None
    aptitud: str | None = None
    banda_maxima: str | None = None

    @model_validator(mode="after")
    def _al_menos_un_filtro(self) -> "ConsultarProductosArgs":
        if not (self.cultivo or self.adversidad or self.principio_activo):
            raise ValueError(mensajes.motivo_sin_filtros())
        return self


def consultar_productos_logica(
    args: ConsultarProductosArgs, conn, modelo_embeddings
) -> ResultadoTool:
    cultivo_id = (
        resolver_entidad_por_nombre(conn, "cultivo", "nombre", args.cultivo, modelo_embeddings)
        if args.cultivo else None
    )
    adversidad_id = (
        resolver_entidad_por_nombre(
            conn, "adversidad", "nombre_comun", args.adversidad, modelo_embeddings
        )
        if args.adversidad else None
    )
    principio_id = (
        resolver_entidad_por_nombre(
            conn, "principio_activo", "nombre", args.principio_activo, modelo_embeddings
        )
        if args.principio_activo else None
    )

    if args.cultivo and cultivo_id is None:
        return ResultadoTool(
            estado="faltan_datos",
            faltantes=[
                CampoFaltante(
                    campo="cultivo", motivo=mensajes.motivo_cultivo_no_encontrado(args.cultivo),
                    pregunta_sugerida=mensajes.PREGUNTA_CULTIVO, tipo_entrada="texto",
                )
            ],
        )

    productos = listar_productos_por_filtro(
        conn, cultivo_id=cultivo_id, adversidad_id=adversidad_id,
        principio_activo_id=principio_id, bandas_permitidas=bandas_hasta(args.banda_maxima),
        limite=20,
    )

    citas = [Cita(fuente="senasa", documento="vademécum")] if productos else []
    return ResultadoTool(
        estado="ok",
        # `mostrados`: cuántos entran en el mensaje ("10 de 20"); así el número del
        # encabezado también sale de la tool.
        datos={
            "productos": productos, "total": len(productos),
            "mostrados": min(len(productos), mensajes.MAXIMO_LISTADO),
        },
        citas=citas,
    )


@tool(
    "consultar_productos",
    args_schema=ConsultarProductosArgs,
    description=DESCRIPCION,
    response_format="content_and_artifact",
    return_direct=True,  # ver `orquestador/respuesta_directa.py`
)
def consultar_productos(
    cultivo: str | None = None,
    adversidad: str | None = None,
    principio_activo: str | None = None,
    aptitud: str | None = None,
    banda_maxima: str | None = None,
) -> tuple[str, ResultadoTool]:
    from fitosanitarios.servicios.recursos import con_conexion_y_modelo

    args = ConsultarProductosArgs(
        cultivo=cultivo, adversidad=adversidad, principio_activo=principio_activo,
        aptitud=aptitud, banda_maxima=banda_maxima,
    )
    resultado = con_conexion_y_modelo(
        lambda conn, modelo: consultar_productos_logica(args, conn, modelo)
    )
    return mensajes.resumen_para_llm(resultado.datos["total"]), resultado
