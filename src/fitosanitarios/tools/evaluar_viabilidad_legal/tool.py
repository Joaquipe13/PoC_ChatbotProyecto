"""Tool `evaluar_viabilidad_legal`: dictamen completo de una receta
confirmada. Ejecuta internamente los chequeos de producto y riesgo -- no
vuelve a invocar `validar_producto_registro`/`evaluar_riesgo` como tools
separadas, para que el dictamen no dependa de que el LLM encadene bien las
tools (ver skill, "Arquitectura")."""

from langchain_core.tools import tool
from pydantic import BaseModel

from fitosanitarios.datos.retrievers.territorio import reglas_candidatas
from fitosanitarios.dominio.modelos import CampoFaltante, ResultadoTool
from fitosanitarios.dominio.motivos import MotivoNoResuelto
from fitosanitarios.servicios.condiciones_aplicacion import calcular_condiciones
from fitosanitarios.servicios.dictamen import armar_dictamen
from fitosanitarios.servicios.ubicacion import resolver_ubicacion_o_cortar
from fitosanitarios.servicios.validacion_producto import resolver_y_validar_producto
from fitosanitarios.tools.evaluar_viabilidad_legal import mensajes
from fitosanitarios.tools.evaluar_viabilidad_legal.prompts import DESCRIPCION


class ProductoDeclarado(BaseModel):
    nombre: str
    dosis_valor: float
    dosis_unidad: str


class EvaluarViabilidadLegalArgs(BaseModel):
    localidad: str | None = None
    provincia: str | None = None  # solo si la localidad no está cargada
    tipo_aplicacion: str  # "terrestre" | "aerea"
    productos: list[ProductoDeclarado]
    cultivo: str
    adversidad: str | None = None
    superficie_ha: float | None = None


def evaluar_viabilidad_legal_logica(
    args: EvaluarViabilidadLegalArgs,
    conn,
    modelo_embeddings,
    tolerancia_pct: float,
) -> ResultadoTool:
    ubicacion, corte = resolver_ubicacion_o_cortar(conn, args.localidad, args.provincia)
    if corte is not None:
        return corte

    reglas = reglas_candidatas(conn, ubicacion.localidad_id, ubicacion.provincia_id)

    chequeos_producto = []
    chequeos_dosis = []
    banda_por_producto: dict[str, str | None] = {}

    for producto in args.productos:
        resolucion = resolver_y_validar_producto(
            conn, modelo_embeddings, producto.nombre, args.cultivo,
            args.adversidad, producto.dosis_valor, producto.dosis_unidad, tolerancia_pct,
        )

        if resolucion.opciones_ambiguas:
            return ResultadoTool(
                estado="faltan_datos",
                faltantes=[
                    CampoFaltante(
                        campo="productos",
                        motivo=mensajes.motivo_producto_ambiguo(producto.nombre),
                        pregunta_sugerida=mensajes.pregunta_producto_ambiguo(producto.nombre),
                        tipo_entrada="lista",
                        opciones=resolucion.opciones_ambiguas,
                    )
                ],
            )
        if resolucion.motivo_no_resuelto == MotivoNoResuelto.PRODUCTO_NO_ENCONTRADO:
            return ResultadoTool(
                estado="no_resuelto", motivo=MotivoNoResuelto.PRODUCTO_NO_ENCONTRADO
            )

        chequeos_producto.append(resolucion.chequeo_producto)
        if resolucion.chequeo_dosis is not None:
            chequeos_dosis.append(resolucion.chequeo_dosis)

        banda_por_producto[resolucion.marca] = resolucion.banda_toxicologica

    condiciones = calcular_condiciones(
        ubicacion.nombre, args.tipo_aplicacion, banda_por_producto, reglas,
        con_normativa_municipal=ubicacion.con_normativa_municipal,
    )
    dictamen = armar_dictamen(chequeos_producto, chequeos_dosis, [], condiciones)

    estado = "ok" if dictamen.resultado == "APTA" else "observado"
    return ResultadoTool(
        estado=estado,
        datos={
            "dictamen": dictamen.model_dump(mode="json"),
            "jurisdiccion_id": ubicacion.jurisdiccion_id,
        },
        citas=dictamen.citas,
        advertencias=condiciones.advertencias
        + [a for d in condiciones.distancias_minimas for a in d.advertencias],
        chequeos_no_realizados=dictamen.chequeos_no_realizados,
    )


@tool(
    "evaluar_viabilidad_legal",
    args_schema=EvaluarViabilidadLegalArgs,
    description=DESCRIPCION,
    response_format="content_and_artifact",
)
def evaluar_viabilidad_legal(
    tipo_aplicacion: str,
    productos: list[ProductoDeclarado],
    cultivo: str,
    localidad: str | None = None,
    provincia: str | None = None,
    adversidad: str | None = None,
    superficie_ha: float | None = None,
) -> tuple[str, ResultadoTool]:
    from fitosanitarios.config import get_settings
    from fitosanitarios.servicios.recursos import con_conexion_y_modelo

    args = EvaluarViabilidadLegalArgs(
        localidad=localidad, provincia=provincia, tipo_aplicacion=tipo_aplicacion,
        productos=productos,
        cultivo=cultivo, adversidad=adversidad, superficie_ha=superficie_ha,
    )
    settings = get_settings()
    resultado = con_conexion_y_modelo(
        lambda conn, modelo: evaluar_viabilidad_legal_logica(
            args, conn, modelo, settings.dosis_tolerancia_pct
        )
    )
    dictamen_resultado = resultado.datos["dictamen"]["resultado"] if resultado.datos else "-"
    return mensajes.resumen_para_llm(dictamen_resultado), resultado
