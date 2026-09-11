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

# Bandas "hasta" una banda máxima (Ia es la más peligrosa, IV la menos).
_BANDAS_HASTA = {
    "Ia": ["Ia"],
    "Ib": ["Ia", "Ib"],
    "II": ["Ia", "Ib", "II"],
    "III": ["Ia", "Ib", "II", "III"],
    "IV": ["Ia", "Ib", "II", "III", "IV"],
}


class ConsultarProductosArgs(BaseModel):
    cultivo: str | None = None
    adversidad: str | None = None
    principio_activo: str | None = None
    aptitud: str | None = None
    banda_maxima: str | None = None

    @model_validator(mode="after")
    def _al_menos_un_filtro(self) -> "ConsultarProductosArgs":
        if not (self.cultivo or self.adversidad or self.principio_activo):
            raise ValueError(
                "consultar_productos requiere cultivo, adversidad o principio_activo"
            )
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
                    campo="cultivo",
                    motivo=f"no se encontró un cultivo parecido a '{args.cultivo}'",
                    pregunta_sugerida="¿Cómo se llama el cultivo?",
                    tipo_entrada="texto",
                )
            ],
        )

    bandas = _BANDAS_HASTA.get(args.banda_maxima) if args.banda_maxima else None
    productos = listar_productos_por_filtro(
        conn, cultivo_id=cultivo_id, adversidad_id=adversidad_id,
        principio_activo_id=principio_id, bandas_permitidas=bandas, limite=20,
    )

    citas = [Cita(fuente="senasa", documento="vademécum")] if productos else []
    return ResultadoTool(
        estado="ok",
        datos={"productos": productos, "total": len(productos)},
        citas=citas,
    )


@tool(
    "consultar_productos", args_schema=ConsultarProductosArgs,
    response_format="content_and_artifact",
)
def consultar_productos(
    cultivo: str | None = None,
    adversidad: str | None = None,
    principio_activo: str | None = None,
    aptitud: str | None = None,
    banda_maxima: str | None = None,
) -> tuple[str, ResultadoTool]:
    """Lista productos registrados en SENASA para un cultivo, plaga o
    principio activo. Usar cuando el operario pide un listado ("¿qué hay
    para yuyo colorado en soja?"), no para preguntar por un producto puntual
    (eso es `validar_producto_registro`). Informa lo registrado; no
    recomienda qué aplicar.

    Args:
        cultivo: cultivo a buscar, si se mencionó.
        adversidad: plaga, maleza o enfermedad a buscar, si se mencionó.
        principio_activo: principio activo a buscar, si se mencionó.
        aptitud: herbicida/insecticida/fungicida/etc., si se mencionó.
        banda_maxima: banda toxicológica más peligrosa a incluir (ej. "III"
            incluye III y IV, no Ia/Ib/II), si se mencionó.
    """
    from fitosanitarios.tools._recursos import con_conexion_y_modelo

    args = ConsultarProductosArgs(
        cultivo=cultivo, adversidad=adversidad, principio_activo=principio_activo,
        aptitud=aptitud, banda_maxima=banda_maxima,
    )
    resultado = con_conexion_y_modelo(
        lambda conn, modelo: consultar_productos_logica(args, conn, modelo)
    )
    return f"consultar_productos: {resultado.datos['total']} productos encontrados", resultado
