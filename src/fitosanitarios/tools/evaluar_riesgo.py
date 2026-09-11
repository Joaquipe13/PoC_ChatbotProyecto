"""Tool `evaluar_riesgo`: jurisdicción por punto en polígono, distancia a
zonas protegidas propias y vecinas, y dosis contra el rango registrado (ver
skill, tabla de tools RAG y "Matriz de parámetros").

Cada producto declarado se evalúa por separado contra cada zona (su propia
banda toxicológica puede activar una regla distinta a la de otro producto en
la misma receta); no se colapsa a "peor caso" por simplicidad, para no
ocultar una regla que aplica a un producto y no a otro.
"""

from langchain_core.tools import tool
from pydantic import BaseModel

from fitosanitarios.datos.retrievers.territorio import (
    localidades_candidatas_por_punto,
    reglas_candidatas,
    zonas_protegidas_en_radio,
)
from fitosanitarios.dominio.modelos import ResultadoTool
from fitosanitarios.dominio.motivos import MotivoNoResuelto
from fitosanitarios.servicios.geo import calcular_distancias, resolver_jurisdiccion
from fitosanitarios.servicios.reglas import evaluar_distancia_zona
from fitosanitarios.servicios.validacion_producto import resolver_y_validar_producto


class EvaluarRiesgoArgs(BaseModel):
    lat: float
    lon: float
    tipo_aplicacion: str  # "terrestre" | "aerea"
    productos: list[str]
    cultivo: str
    dosis_valor: float
    dosis_unidad: str
    adversidad: str | None = None


def evaluar_riesgo_logica(
    args: EvaluarRiesgoArgs, conn, modelo_embeddings, radio_busqueda_m: float, tolerancia_pct: float
) -> ResultadoTool:
    localidades = localidades_candidatas_por_punto(conn, args.lat, args.lon)
    localidad = resolver_jurisdiccion(args.lat, args.lon, localidades)
    if localidad is None:
        return ResultadoTool(estado="no_resuelto", motivo=MotivoNoResuelto.JURISDICCION_NO_CUBIERTA)

    zonas = zonas_protegidas_en_radio(conn, args.lat, args.lon, radio_busqueda_m)
    distancias = calcular_distancias(args.lat, args.lon, zonas)
    reglas = reglas_candidatas(conn, localidad.id, localidad.provincia_id)

    chequeos_distancia = []
    citas = []
    advertencias = []
    chequeos_no_realizados = []
    productos_info = []

    for nombre_producto in args.productos:
        resolucion = resolver_y_validar_producto(
            conn, modelo_embeddings, nombre_producto, args.cultivo,
            args.adversidad, args.dosis_valor, args.dosis_unidad, tolerancia_pct,
        )
        if resolucion.opciones_ambiguas or resolucion.motivo_no_resuelto is not None:
            # Ambigüedad o producto no encontrado corta la evaluación de riesgo
            # para este producto puntual, pero no rompe el resto del turno.
            chequeos_no_realizados.append(
                f"{nombre_producto}: no se pudo resolver contra el registro"
            )
            continue

        banda = resolucion.banda_toxicologica or "todas"
        productos_info.append({
            "nombre": resolucion.marca, "numero_inscripcion": resolucion.numero_inscripcion,
            "banda_toxicologica": resolucion.banda_toxicologica,
        })

        for zona in distancias:
            chequeo = evaluar_distancia_zona(
                zona.tipo, zona.nombre, zona.distancia_m, reglas, args.tipo_aplicacion, banda
            )
            if chequeo is None:
                continue
            chequeos_distancia.append(chequeo)
            citas.extend(chequeo.citas)
            advertencias.extend(chequeo.advertencias)

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

    observaciones_distancia = [c for c in chequeos_distancia if not c.cumple]
    datos = {
        "jurisdiccion_id": localidad.jurisdiccion_id,
        "productos": productos_info,
        "zonas_evaluadas": [
            {
                "tipo": c.zona_tipo, "nombre": c.zona_nombre, "distancia_m": c.distancia_real_m,
                "distancia_min_m": c.distancia_min_aplicable_m, "cumple": c.cumple,
            }
            for c in chequeos_distancia
        ],
    }

    estado = "observado" if observaciones_distancia else "ok"
    return ResultadoTool(
        estado=estado, datos=datos, citas=citas, advertencias=advertencias,
        chequeos_no_realizados=chequeos_no_realizados,
    )


@tool("evaluar_riesgo", args_schema=EvaluarRiesgoArgs, response_format="content_and_artifact")
def evaluar_riesgo(
    lat: float,
    lon: float,
    tipo_aplicacion: str,
    productos: list[str],
    cultivo: str,
    dosis_valor: float,
    dosis_unidad: str,
    adversidad: str | None = None,
) -> tuple[str, ResultadoTool]:
    """Evalúa el riesgo geográfico y de dosis de una aplicación: jurisdicción
    del lote, distancia a zonas protegidas, y dosis contra el rango
    registrado. Usar para consultas sueltas de riesgo; para el dictamen
    completo de una receta confirmada usar `evaluar_viabilidad_legal`.

    Args:
        lat: latitud del lote.
        lon: longitud del lote.
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
        lat=lat, lon=lon, tipo_aplicacion=tipo_aplicacion, productos=productos,
        cultivo=cultivo, dosis_valor=dosis_valor, dosis_unidad=dosis_unidad,
        adversidad=adversidad,
    )
    settings = get_settings()
    resultado = con_conexion_y_modelo(
        lambda conn, modelo: evaluar_riesgo_logica(
            args, conn, modelo, settings.radio_busqueda_zonas_m, settings.dosis_tolerancia_pct
        )
    )
    return f"evaluar_riesgo: estado={resultado.estado}", resultado
