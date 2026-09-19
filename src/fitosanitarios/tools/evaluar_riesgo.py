"""Tool `evaluar_riesgo`: banda toxicológica de la aplicación completa y
distancia mínima que fija la normativa de la localidad, más la dosis contra
el rango registrado (ver skill, tabla de tools RAG y "Matriz de parámetros").

No compara contra la ubicación del lote: la localidad se identifica por
nombre y solo se informa qué exige la norma (ver DECISIONES.md).

La banda de la aplicación es la más peligrosa entre los productos de la
mezcla; cada producto conserva la suya en `productos`.
"""

from langchain_core.tools import tool
from pydantic import BaseModel

from fitosanitarios.datos.retrievers.territorio import reglas_candidatas
from fitosanitarios.dominio.modelos import ResultadoTool
from fitosanitarios.servicios.condiciones_aplicacion import calcular_condiciones
from fitosanitarios.servicios.validacion_producto import resolver_y_validar_producto
from fitosanitarios.tools._localidad import resolver_localidad_o_cortar


class EvaluarRiesgoArgs(BaseModel):
    localidad: str | None = None
    tipo_aplicacion: str  # "terrestre" | "aerea"
    productos: list[str]
    cultivo: str
    dosis_valor: float
    dosis_unidad: str
    adversidad: str | None = None


def evaluar_riesgo_logica(
    args: EvaluarRiesgoArgs, conn, modelo_embeddings, tolerancia_pct: float
) -> ResultadoTool:
    localidad, corte = resolver_localidad_o_cortar(conn, args.localidad)
    if corte is not None:
        return corte

    reglas = reglas_candidatas(conn, localidad.id, localidad.provincia_id)

    chequeos_no_realizados = []
    productos_info = []
    banda_por_producto: dict[str, str | None] = {}

    for nombre_producto in args.productos:
        resolucion = resolver_y_validar_producto(
            conn, modelo_embeddings, nombre_producto, args.cultivo,
            args.adversidad, args.dosis_valor, args.dosis_unidad, tolerancia_pct,
        )
        if resolucion.opciones_ambiguas or resolucion.marca is None:
            # Ambigüedad o producto no encontrado corta la evaluación de riesgo
            # para este producto puntual, pero no rompe el resto del turno.
            chequeos_no_realizados.append(
                f"{nombre_producto}: no se pudo resolver contra el registro"
            )
            continue

        banda_por_producto[resolucion.marca] = resolucion.banda_toxicologica
        productos_info.append({
            "nombre": resolucion.marca, "numero_inscripcion": resolucion.numero_inscripcion,
            "banda_toxicologica": resolucion.banda_toxicologica,
        })

        if resolucion.chequeo_dosis is not None and not resolucion.chequeo_dosis.comparable:
            if resolucion.chequeo_dosis.requiere_volumen_caldo:
                chequeos_no_realizados.append(
                    f"{resolucion.marca}: dosis por 100 L requiere volumen de caldo por hectárea"
                )
            else:
                chequeos_no_realizados.append(
                    f"{resolucion.marca}: dosis no comparable "
                    f"({resolucion.chequeo_dosis.motivo_no_comparable})"
                )

    condiciones = calcular_condiciones(
        localidad.nombre, args.tipo_aplicacion, banda_por_producto, reglas
    )
    chequeos_no_realizados.extend(
        f"{producto}: no figura su banda toxicológica en SENASA; la de la aplicación "
        "podría ser más restrictiva"
        for producto in condiciones.productos_sin_banda
    )
    citas = [c for d in condiciones.distancias_minimas for c in d.citas]
    advertencias = [a for d in condiciones.distancias_minimas for a in d.advertencias]
    advertencias.extend(condiciones.advertencias)

    return ResultadoTool(
        estado="ok",
        datos={
            "jurisdiccion_id": localidad.jurisdiccion_id,
            "productos": productos_info,
            "condiciones": condiciones.model_dump(mode="json"),
        },
        citas=citas, advertencias=advertencias,
        chequeos_no_realizados=chequeos_no_realizados,
    )


@tool("evaluar_riesgo", args_schema=EvaluarRiesgoArgs, response_format="content_and_artifact")
def evaluar_riesgo(
    tipo_aplicacion: str,
    productos: list[str],
    cultivo: str,
    dosis_valor: float,
    dosis_unidad: str,
    localidad: str | None = None,
    adversidad: str | None = None,
) -> tuple[str, ResultadoTool]:
    """Informa la banda toxicológica de la aplicación (la más peligrosa entre
    sus productos) y la distancia mínima que fija la normativa de la
    localidad, más la dosis contra el rango registrado. No usa la ubicación
    exacta del lote. Usar para consultas sueltas; para el dictamen completo de
    una receta confirmada usar `evaluar_viabilidad_legal`.

    Args:
        localidad: localidad o municipio donde se va a aplicar.
        tipo_aplicacion: "terrestre" o "aerea".
        productos: nombres de los productos a aplicar.
        cultivo: cultivo declarado.
        dosis_valor: valor numérico de la dosis.
        dosis_unidad: unidad de la dosis ("L/ha", "kg/ha", etc.).
        adversidad: plaga/maleza/enfermedad, si se mencionó.
    """
    from fitosanitarios.config import get_settings
    from fitosanitarios.tools._recursos import con_conexion_y_modelo

    args = EvaluarRiesgoArgs(
        localidad=localidad, tipo_aplicacion=tipo_aplicacion, productos=productos,
        cultivo=cultivo, dosis_valor=dosis_valor, dosis_unidad=dosis_unidad,
        adversidad=adversidad,
    )
    settings = get_settings()
    resultado = con_conexion_y_modelo(
        lambda conn, modelo: evaluar_riesgo_logica(
            args, conn, modelo, settings.dosis_tolerancia_pct
        )
    )
    return f"evaluar_riesgo: estado={resultado.estado}", resultado
