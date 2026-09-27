"""Combina los chequeos de producto, riesgo geográfico y dosis en un
`Dictamen` final (ver skill, "Reglas del núcleo experto / Dictamen").

- **APTA**: todos los chequeos obligatorios corrieron y cumplen.
- **OBSERVADA**: al menos un chequeo no cumple. Se listan todas las
  observaciones, no solo la primera.
- **NO_EVALUABLE**: ninguno falla, pero al menos un obligatorio no pudo
  correr (ej. producto sin usos registrados: cultivo y dosis quedan "no
  verificados", nunca APTA por omisión).

Obligatorios: producto registrado y activo, cultivo autorizado y dosis
dentro de rango. La distancia mínima a zonas protegidas ya no se compara
contra la ubicación del lote: se informa como `condiciones` (banda de la
aplicación y distancias mínimas de la localidad) y no cambia el resultado.
Lo único que sí lo condiciona es una banda de producto desconocida: sin ella
la banda de la aplicación podría ser más restrictiva, así que queda NO_EVALUABLE.
"""

from dataclasses import dataclass, field

from fitosanitarios.dominio.modelos import Cita, CondicionesAplicacion, Dictamen, Observacion
from fitosanitarios.servicios.dosis import ChequeoDosis
from fitosanitarios.servicios.formato import num


def observacion_de_dosis(chd: ChequeoDosis) -> str:
    """La dosis declarada fuera del rango registrado. La usan el dictamen y
    `evaluar_riesgo`, que también compara la dosis."""
    direccion = "por encima" if chd.porcentaje_desvio > 0 else "por debajo"
    return (
        f"Dosis {num(chd.valor_declarado)} {chd.unidad_declarada}: {direccion} del rango "
        f"registrado ({num(chd.valor_min_registrado)}-{num(chd.valor_max_registrado)} "
        f"{chd.unidad_declarada}), {abs(chd.porcentaje_desvio):.0f}% de desvío."
    )


@dataclass
class ChequeoProducto:
    """Resultado de validar un producto contra el registro."""

    producto_nombre: str
    registrado: bool
    activo: bool | None = None
    # None: no se pudo verificar (el producto no tiene usos registrados) ->
    # NO_EVALUABLE, no un "no cumple" (ver skill).
    cultivo_autorizado: bool | None = None
    banda_toxicologica: str | None = None
    citas: list[Cita] = field(default_factory=list)


def armar_dictamen(
    chequeos_producto: list[ChequeoProducto],
    chequeos_dosis: list[ChequeoDosis],
    chequeos_no_realizados: list[str] | None = None,
    condiciones: CondicionesAplicacion | None = None,
) -> Dictamen:
    observaciones: list[Observacion] = []
    citas: list[Cita] = []
    no_realizados = list(chequeos_no_realizados or [])

    for cp in chequeos_producto:
        citas.extend(cp.citas)
        if not cp.registrado:
            observaciones.append(
                Observacion(descripcion=f"{cp.producto_nombre}: no está registrado en SENASA.")
            )
            continue
        if cp.activo is False:
            observaciones.append(
                Observacion(descripcion=f"{cp.producto_nombre}: el registro no está activo.")
            )
        if cp.cultivo_autorizado is False:
            observaciones.append(
                Observacion(
                    descripcion=(
                        f"{cp.producto_nombre}: no está autorizado para el cultivo declarado."
                    ),
                    citas=cp.citas,
                )
            )
        elif cp.cultivo_autorizado is None:
            no_realizados.append(
                f"{cp.producto_nombre}: cultivo y dosis no verificados "
                "(el producto no tiene usos registrados)"
            )

    for chd in chequeos_dosis:
        if not chd.comparable:
            if chd.requiere_volumen_caldo:
                no_realizados.append(
                    f"Dosis {chd.valor_declarado} {chd.unidad_declarada}: no se pudo "
                    "convertir a dosis por hectárea sin el volumen de caldo aplicado"
                )
            else:
                no_realizados.append(
                    f"Dosis {chd.valor_declarado} {chd.unidad_declarada}: "
                    f"{chd.motivo_no_comparable or 'no comparable con el registro'}"
                )
        elif not chd.cumple:
            observaciones.append(Observacion(descripcion=observacion_de_dosis(chd)))

    if condiciones is not None:
        for distancia in condiciones.distancias_minimas:
            citas.extend(distancia.citas)
        no_realizados.extend(
            f"{producto}: no figura su banda toxicológica en SENASA; la de la aplicación "
            "podría ser más restrictiva"
            for producto in condiciones.productos_sin_banda
        )

    if observaciones:
        resultado = "OBSERVADA"
    elif no_realizados:
        resultado = "NO_EVALUABLE"
    else:
        resultado = "APTA"

    return Dictamen(
        resultado=resultado,
        observaciones=observaciones,
        chequeos_no_realizados=no_realizados,
        citas=citas,
        condiciones=condiciones,
    )
