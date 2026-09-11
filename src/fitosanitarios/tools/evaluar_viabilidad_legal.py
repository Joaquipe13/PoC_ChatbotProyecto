"""Tool `evaluar_viabilidad_legal`: dictamen completo de una receta
confirmada. Ejecuta internamente los chequeos de producto y riesgo -- no
vuelve a invocar `validar_producto_registro`/`evaluar_riesgo` como tools
separadas, para que el dictamen no dependa de que el LLM encadene bien las
tools (ver skill, "Arquitectura")."""

from langchain_core.tools import tool
from pydantic import BaseModel

from fitosanitarios.datos.retrievers.territorio import (
    localidades_candidatas_por_punto,
    reglas_candidatas,
    zonas_protegidas_en_radio,
)
from fitosanitarios.dominio.modelos import CampoFaltante, ResultadoTool
from fitosanitarios.dominio.motivos import MotivoNoResuelto
from fitosanitarios.servicios.dictamen import armar_dictamen
from fitosanitarios.servicios.geo import calcular_distancias, resolver_jurisdiccion
from fitosanitarios.servicios.reglas import evaluar_distancia_zona
from fitosanitarios.servicios.validacion_producto import resolver_y_validar_producto


class ProductoDeclarado(BaseModel):
    nombre: str
    dosis_valor: float
    dosis_unidad: str


class EvaluarViabilidadLegalArgs(BaseModel):
    lat: float
    lon: float
    tipo_aplicacion: str  # "terrestre" | "aerea"
    productos: list[ProductoDeclarado]
    cultivo: str
    adversidad: str | None = None
    superficie_ha: float | None = None


def evaluar_viabilidad_legal_logica(
    args: EvaluarViabilidadLegalArgs,
    conn,
    modelo_embeddings,
    radio_busqueda_m: float,
    tolerancia_pct: float,
) -> ResultadoTool:
    localidades = localidades_candidatas_por_punto(conn, args.lat, args.lon)
    localidad = resolver_jurisdiccion(args.lat, args.lon, localidades)
    if localidad is None:
        return ResultadoTool(
            estado="no_resuelto", motivo=MotivoNoResuelto.JURISDICCION_NO_CUBIERTA
        )

    zonas = zonas_protegidas_en_radio(conn, args.lat, args.lon, radio_busqueda_m)
    distancias = calcular_distancias(args.lat, args.lon, zonas)
    reglas = reglas_candidatas(conn, localidad.id, localidad.provincia_id)

    chequeos_producto = []
    chequeos_distancia = []
    chequeos_dosis = []

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
                        motivo=f"'{producto.nombre}' es ambiguo, coincide con varios productos",
                        pregunta_sugerida="¿Cuál de estos productos es?",
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

        if resolucion.motivo_no_resuelto == MotivoNoResuelto.SIN_USOS_REGISTRADOS:
            continue  # sin banda/usos: no hay con qué evaluar distancia para este producto

        banda = resolucion.banda_toxicologica or "todas"
        for zona in distancias:
            chequeo = evaluar_distancia_zona(
                zona.tipo, zona.nombre, zona.distancia_m, reglas, args.tipo_aplicacion, banda
            )
            if chequeo is not None:
                chequeos_distancia.append(chequeo)

    dictamen = armar_dictamen(chequeos_producto, chequeos_distancia, chequeos_dosis, [])

    estado = "ok" if dictamen.resultado == "APTA" else "observado"
    return ResultadoTool(
        estado=estado,
        datos={
            "dictamen": dictamen.model_dump(mode="json"),
            "jurisdiccion_id": localidad.jurisdiccion_id,
        },
        citas=dictamen.citas,
        chequeos_no_realizados=dictamen.chequeos_no_realizados,
    )


@tool(
    "evaluar_viabilidad_legal",
    args_schema=EvaluarViabilidadLegalArgs,
    response_format="content_and_artifact",
)
def evaluar_viabilidad_legal(
    lat: float,
    lon: float,
    tipo_aplicacion: str,
    productos: list[ProductoDeclarado],
    cultivo: str,
    adversidad: str | None = None,
    superficie_ha: float | None = None,
) -> tuple[str, ResultadoTool]:
    """Emite el dictamen completo (APTA/OBSERVADA/NO EVALUABLE) de una
    receta ya confirmada por el operario. Requiere los mismos datos que
    `validar_producto_registro` y `evaluar_riesgo` juntos.

    Args:
        lat: latitud del lote.
        lon: longitud del lote.
        tipo_aplicacion: "terrestre" o "aerea".
        productos: lista de productos con su dosis declarada.
        cultivo: cultivo declarado.
        adversidad: plaga/maleza/enfermedad, si se mencionó.
        superficie_ha: superficie del lote en hectáreas, si se mencionó.
    """
    from fitosanitarios.config import get_settings
    from fitosanitarios.tools._recursos import con_conexion_y_modelo

    args = EvaluarViabilidadLegalArgs(
        lat=lat, lon=lon, tipo_aplicacion=tipo_aplicacion, productos=productos,
        cultivo=cultivo, adversidad=adversidad, superficie_ha=superficie_ha,
    )
    settings = get_settings()
    resultado = con_conexion_y_modelo(
        lambda conn, modelo: evaluar_viabilidad_legal_logica(
            args, conn, modelo, settings.radio_busqueda_zonas_m, settings.dosis_tolerancia_pct
        )
    )
    dictamen_resultado = resultado.datos["dictamen"]["resultado"] if resultado.datos else "-"
    return f"evaluar_viabilidad_legal: {dictamen_resultado}", resultado
