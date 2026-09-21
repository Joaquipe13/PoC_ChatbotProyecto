"""Condiciones de la aplicación según la normativa de la localidad.

Ya no se compara contra la ubicación del lote: con los productos de la
receta se determina la banda toxicológica de la aplicación completa (la más
peligrosa de la mezcla) y con ella, el tipo de aplicación y las reglas de la
localidad se informa la distancia mínima a cada tipo de zona (zona urbana,
escuela, curso de agua...). Función pura, sin base ni red.
"""

from fitosanitarios.dominio.modelos import Cita, CondicionesAplicacion, DistanciaMinima
from fitosanitarios.servicios.reglas import (
    ReglaCandidata,
    normalizar_tipo_aplicacion,
    reglas_aplicables,
)

# De más a menos peligrosa (Ia/Ib roja, II amarilla, III azul, IV verde).
ORDEN_BANDAS = ["Ia", "Ib", "II", "III", "IV"]
COLOR_BANDA = {"Ia": "roja", "Ib": "roja", "II": "amarilla", "III": "azul", "IV": "verde"}


def banda_de_la_aplicacion(bandas: list[str | None]) -> str | None:
    """La más peligrosa de las bandas conocidas; `None` si no hay ninguna."""
    conocidas = [b for b in bandas if b in ORDEN_BANDAS]
    if not conocidas:
        return None
    return min(conocidas, key=ORDEN_BANDAS.index)


def calcular_condiciones(
    localidad: str,
    tipo_aplicacion: str,
    banda_por_producto: dict[str, str | None],
    reglas: list[ReglaCandidata],
    con_normativa_municipal: bool = True,
) -> CondicionesAplicacion:
    tipo_aplicacion = normalizar_tipo_aplicacion(tipo_aplicacion) or tipo_aplicacion
    banda = banda_de_la_aplicacion(list(banda_por_producto.values()))
    sin_banda = [p for p, b in banda_por_producto.items() if b not in ORDEN_BANDAS]
    advertencias: list[str] = []
    if not con_normativa_municipal:
        advertencias.append(
            f"No se cuenta con la normativa municipal de {localidad}: la distancia "
            "se basa en la normativa provincial"
        )

    # Sin banda conocida solo aplican las reglas "todas": nunca se asume una banda.
    banda_para_reglas = banda or "todas"
    distancias: list[DistanciaMinima] = []
    for tipo_zona in dict.fromkeys(r.tipo_zona for r in reglas):
        aplicables = reglas_aplicables(reglas, tipo_zona, tipo_aplicacion, banda_para_reglas)
        if not aplicables:
            continue
        mas_restrictiva = max(aplicables, key=lambda r: r.distancia_min_m)
        distancias.append(
            DistanciaMinima(
                tipo_zona=tipo_zona,
                distancia_min_m=mas_restrictiva.distancia_min_m,
                norma_limitante=_cita(mas_restrictiva),
                extraida_de_pdf=mas_restrictiva.fuente == "pdf_extraido",
                citas=[_cita(r) for r in aplicables],
                advertencias=[r.observaciones for r in aplicables if r.observaciones],
            )
        )

    if not distancias:
        advertencias.append(
            f"No hay una distancia mínima cargada para {localidad} con aplicación "
            f"{tipo_aplicacion}"
            + (f" y banda {banda}" if banda else "")
            + ": consultá la ordenanza vigente o al área de ambiente del municipio"
        )

    return CondicionesAplicacion(
        localidad=localidad,
        tipo_aplicacion=tipo_aplicacion,
        banda=banda,
        banda_color=COLOR_BANDA.get(banda) if banda else None,
        productos_por_banda=banda_por_producto,
        productos_sin_banda=sin_banda,
        sin_normativa_municipal=not con_normativa_municipal,
        distancias_minimas=distancias,
        advertencias=advertencias,
    )


def _cita(regla: ReglaCandidata) -> Cita:
    return Cita(
        fuente="normativa", jurisdiccion_id=regla.jurisdiccion_id,
        norma=regla.norma, articulo=regla.articulo,
    )
