"""Tool `validar_producto_registro`: valida un producto puntual contra el
registro de SENASA (ver skill, "Matriz de parámetros")."""

from langchain_core.tools import tool
from pydantic import BaseModel

from fitosanitarios.dominio.modelos import CampoFaltante, ResultadoTool
from fitosanitarios.servicios.validacion_producto import resolver_y_validar_producto


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
                    campo="producto_nombre",
                    motivo="varios productos coinciden con ese nombre",
                    pregunta_sugerida=(
                        f"Hay varios productos parecidos a '{args.producto_nombre}'. ¿Cuál es?"
                    ),
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
        advertencias.append(f"{resolucion.marca} no tiene un uso registrado para {args.cultivo}")

    estado = "ok" if cp.cultivo_autorizado else "observado"
    return ResultadoTool(estado=estado, datos=datos, citas=cp.citas, advertencias=advertencias)


@tool(
    "validar_producto_registro",
    args_schema=ValidarProductoRegistroArgs,
    response_format="content_and_artifact",
)
def validar_producto_registro(
    producto_nombre: str,
    cultivo: str,
    adversidad: str | None = None,
    dosis_valor: float | None = None,
    dosis_unidad: str | None = None,
) -> tuple[str, ResultadoTool]:
    """Valida si un producto puntual está registrado en SENASA y autorizado
    para un cultivo. Usar cuando el operario pregunta por UN producto
    concreto ("¿el glifo full está habilitado para soja?"). Para pedir un
    listado de productos, usar `consultar_productos`.

    Args:
        producto_nombre: nombre comercial tal como lo escribió el operario.
        cultivo: cultivo declarado.
        adversidad: plaga/maleza/enfermedad, si se mencionó.
        dosis_valor: valor numérico de la dosis, si se mencionó.
        dosis_unidad: unidad de la dosis ("L/ha", "kg/ha", etc.), si se mencionó.
    """
    from fitosanitarios.config import get_settings
    from fitosanitarios.tools._recursos import con_conexion_y_modelo

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
    resumen = f"validar_producto_registro: estado={resultado.estado}"
    return resumen, resultado
