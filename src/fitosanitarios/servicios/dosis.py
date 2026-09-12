"""Comparación de dosis declarada contra el rango registrado, con tolerancia
configurable (ver skill, "Dosis").

Reutiliza la unidad ya normalizada por `senasa/parser_dosis.py` ("L/ha",
"kg/ha", "ml/100L", etc.). Este servicio no vuelve a parsear texto libre:
recibe valores y unidades ya estructurados, tanto de la receta como del
registro.
"""

from dataclasses import dataclass

# cantidad -> (factor a la unidad base de su familia, familia)
_FAMILIAS_UNIDAD = {
    "L": (1.0, "volumen"),
    "ml": (0.001, "volumen"),
    "cm³": (0.001, "volumen"),
    # Alias sin el superíndice unicode: el LLM orquestador recibe el texto
    # tal cual lo escribió el operario (típicamente desde el teclado de un
    # celular, sin "³") y lo pasa como argumento de tool sin normalizar --
    # ver skill, "Dosis": la normalización de unidades es del núcleo, no del
    # LLM. Hallazgo real de la Fase 10: "170 cm3/ha" (como typea cualquier
    # operario) daba "unidad no reconocida" -> NO_EVALUABLE, reproducido en
    # los evals (Fase 7) y en la demo (Fase 8/9), mal catalogado como
    # limitación aceptada en vez de bug. Ver DECISIONES.md.
    "cm3": (0.001, "volumen"),
    "kg": (1.0, "masa"),
    "g": (0.001, "masa"),
}


@dataclass
class ChequeoDosis:
    cumple: bool
    comparable: bool
    valor_declarado: float
    unidad_declarada: str
    valor_min_registrado: float | None
    valor_max_registrado: float | None
    porcentaje_desvio: float | None  # positivo = por encima, negativo = por debajo
    motivo_no_comparable: str | None = None
    requiere_volumen_caldo: bool = False


def _normalizar_por_ha(valor: float, unidad: str) -> tuple[float, str] | None:
    """`unidad` en la forma "L/ha", "kg/ha", etc. Devuelve
    (valor_normalizado_a_la_unidad_base_de_su_familia, familia), o `None`
    si la unidad no es reconocida o no es por hectárea."""
    if not unidad.endswith("/ha"):
        return None
    cantidad = unidad[: -len("/ha")]
    info = _FAMILIAS_UNIDAD.get(cantidad)
    if info is None:
        return None
    factor, familia = info
    return valor * factor, familia


def comparar_dosis(
    valor_declarado: float,
    unidad_declarada: str,
    valor_min_registrado: float | None,
    valor_max_registrado: float | None,
    unidad_registrada: str | None,
    tolerancia_pct: float,
) -> ChequeoDosis:
    """`unidad_declarada`/`unidad_registrada` como las normaliza
    `parser_dosis.py`: "L/ha", "kg/ha", "ml/100L", etc.

    Si la unidad declarada es "por 100 L de agua" (`base=volumen_caldo` en
    `DosisParseada`), no se puede convertir a por-hectárea sin el volumen de
    caldo aplicado por hectárea -- se devuelve `requiere_volumen_caldo=True`
    en vez de intentar adivinar (ver skill: "'Cada 100 L de agua' requiere
    volumen de caldo; si no está, faltan_datos")."""
    if unidad_declarada.endswith("/100L"):
        return ChequeoDosis(
            cumple=False, comparable=False,
            valor_declarado=valor_declarado, unidad_declarada=unidad_declarada,
            valor_min_registrado=valor_min_registrado,
            valor_max_registrado=valor_max_registrado,
            porcentaje_desvio=None, requiere_volumen_caldo=True,
        )

    if valor_min_registrado is None or unidad_registrada is None:
        return ChequeoDosis(
            cumple=False, comparable=False,
            valor_declarado=valor_declarado, unidad_declarada=unidad_declarada,
            valor_min_registrado=valor_min_registrado,
            valor_max_registrado=valor_max_registrado,
            porcentaje_desvio=None, motivo_no_comparable="sin rango registrado",
        )

    declarado = _normalizar_por_ha(valor_declarado, unidad_declarada)
    minimo = _normalizar_por_ha(valor_min_registrado, unidad_registrada)
    if declarado is None or minimo is None:
        return ChequeoDosis(
            cumple=False, comparable=False,
            valor_declarado=valor_declarado, unidad_declarada=unidad_declarada,
            valor_min_registrado=valor_min_registrado,
            valor_max_registrado=valor_max_registrado,
            porcentaje_desvio=None, motivo_no_comparable="unidad no reconocida",
        )
    valor_d, familia_d = declarado
    valor_min_n, familia_min = minimo
    if familia_d != familia_min:
        return ChequeoDosis(
            cumple=False, comparable=False,
            valor_declarado=valor_declarado, unidad_declarada=unidad_declarada,
            valor_min_registrado=valor_min_registrado,
            valor_max_registrado=valor_max_registrado,
            porcentaje_desvio=None,
            motivo_no_comparable=f"familias distintas ({familia_d} vs {familia_min})",
        )

    if valor_max_registrado is not None:
        valor_max_n, _ = _normalizar_por_ha(valor_max_registrado, unidad_registrada)
    else:
        valor_max_n = valor_min_n

    tolerancia_min = valor_min_n * (1 - tolerancia_pct / 100)
    tolerancia_max = valor_max_n * (1 + tolerancia_pct / 100)
    cumple = tolerancia_min <= valor_d <= tolerancia_max

    if valor_d > valor_max_n:
        desvio = (valor_d - valor_max_n) / valor_max_n * 100
    elif valor_d < valor_min_n:
        desvio = (valor_d - valor_min_n) / valor_min_n * 100
    else:
        desvio = 0.0

    return ChequeoDosis(
        cumple=cumple, comparable=True,
        valor_declarado=valor_declarado, unidad_declarada=unidad_declarada,
        valor_min_registrado=valor_min_registrado, valor_max_registrado=valor_max_registrado,
        porcentaje_desvio=desvio,
    )
