"""Combina los chequeos de producto, riesgo geográfico y dosis en un
`Dictamen` final (ver skill, "Reglas del núcleo experto / Dictamen").

- **APTA**: todos los chequeos obligatorios corrieron y cumplen.
- **OBSERVADA**: al menos un chequeo no cumple. Se listan todas las
  observaciones, no solo la primera.
- **NO_EVALUABLE**: ninguno falla, pero al menos un obligatorio no pudo
  correr (ej. producto sin usos registrados: cultivo y dosis quedan "no
  verificados", nunca APTA por omisión).

Obligatorios: producto registrado y activo, cultivo autorizado, distancia
mínima a zonas protegidas, dosis dentro de rango.
"""

from dataclasses import dataclass, field

from fitosanitarios.dominio.modelos import Cita, Dictamen, Observacion
from fitosanitarios.servicios.dosis import ChequeoDosis
from fitosanitarios.servicios.reglas import ChequeoDistanciaZona


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
    chequeos_distancia: list[ChequeoDistanciaZona],
    chequeos_dosis: list[ChequeoDosis],
    chequeos_no_realizados: list[str] | None = None,
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

    for cd in chequeos_distancia:
        citas.extend(cd.citas)
        if not cd.cumple:
            observaciones.append(
                Observacion(
                    descripcion=(
                        f"Distancia a {cd.zona_tipo} ({cd.zona_nombre}) insuficiente: el "
                        f"lote está a {cd.distancia_real_m:.0f} m y el mínimo es "
                        f"{cd.distancia_min_aplicable_m:.0f} m."
                    ),
                    citas=cd.citas,
                )
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
            direccion = "por encima" if chd.porcentaje_desvio > 0 else "por debajo"
            observaciones.append(
                Observacion(
                    descripcion=(
                        f"Dosis {chd.valor_declarado} {chd.unidad_declarada}: {direccion} del "
                        f"rango registrado ({chd.valor_min_registrado}-"
                        f"{chd.valor_max_registrado} {chd.unidad_declarada}), "
                        f"{abs(chd.porcentaje_desvio):.0f}% de desvío."
                    )
                )
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
    )
