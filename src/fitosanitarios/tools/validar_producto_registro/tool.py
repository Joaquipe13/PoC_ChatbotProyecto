"""Tool `validar_producto_registro`: valida un producto puntual contra el
registro de SENASA (ver skill, "Matriz de parámetros")."""

from langchain_core.tools import tool
from pydantic import BaseModel

from fitosanitarios.dominio.modelos import CampoFaltante, ResultadoTool
from fitosanitarios.servicios.validacion_producto import resolver_y_validar_producto
from fitosanitarios.tools.validar_producto_registro import mensajes
from fitosanitarios.tools.validar_producto_registro.prompts import DESCRIPCION


class ValidarProductoRegistroArgs(BaseModel):
    producto_nombre: str
    cultivo: str
    adversidad: str | None = None
    dosis_valor: float | None = None
    dosis_unidad: str | None = None


def validar_producto_registro_logica(
    args: ValidarProductoRegistroArgs, conn, modelo_embeddings, tolerancia_pct: float
) -> ResultadoTool:
    resolucion = resolver_y_validar_producto(
        conn, modelo_embeddings, args.producto_nombre, args.cultivo,
        args.adversidad, args.dosis_valor, args.dosis_unidad, tolerancia_pct,
    )

    if resolucion.opciones_ambiguas:
        return ResultadoTool(
            estado="faltan_datos",
            faltantes=[
                CampoFaltante(
                    campo="producto_nombre", motivo=mensajes.MOTIVO_PRODUCTO_AMBIGUO,
                    pregunta_sugerida=mensajes.pregunta_producto_ambiguo(args.producto_nombre),
                    tipo_entrada="lista",
                    opciones=resolucion.opciones_ambiguas,
                )
            ],
        )

    if resolucion.motivo_no_resuelto is not None:
        return ResultadoTool(estado="no_resuelto", motivo=resolucion.motivo_no_resuelto)

    cp = resolucion.chequeo_producto
    datos = {
        "producto": resolucion.marca,
        "numero_inscripcion": resolucion.numero_inscripcion,
        "banda_toxicologica": resolucion.banda_toxicologica,
        "cultivo_autorizado": cp.cultivo_autorizado,
        "usos_registrados": resolucion.usos_registrados,
    }
    advertencias = []
    if cp.cultivo_autorizado is False:
        advertencias.append(mensajes.advertencia_sin_uso_registrado(resolucion.marca, args.cultivo))

    estado = "ok" if cp.cultivo_autorizado else "observado"
    return ResultadoTool(estado=estado, datos=datos, citas=cp.citas, advertencias=advertencias)


@tool(
    "validar_producto_registro",
    args_schema=ValidarProductoRegistroArgs,
    description=DESCRIPCION,
    response_format="content_and_artifact",
)
def validar_producto_registro(
    producto_nombre: str,
    cultivo: str,
    adversidad: str | None = None,
    dosis_valor: float | None = None,
    dosis_unidad: str | None = None,
) -> tuple[str, ResultadoTool]:
    from fitosanitarios.config import get_settings
    from fitosanitarios.servicios.recursos import con_conexion_y_modelo

    args = ValidarProductoRegistroArgs(
        producto_nombre=producto_nombre, cultivo=cultivo, adversidad=adversidad,
        dosis_valor=dosis_valor, dosis_unidad=dosis_unidad,
    )
    settings = get_settings()
    resultado = con_conexion_y_modelo(
        lambda conn, modelo: validar_producto_registro_logica(
            args, conn, modelo, settings.dosis_tolerancia_pct
        )
    )
    return mensajes.resumen_para_llm(resultado.estado), resultado
