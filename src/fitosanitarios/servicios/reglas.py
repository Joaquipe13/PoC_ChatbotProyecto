"""Motor de reglas determinista: dado un conjunto de reglas de distancia
candidatas y la distancia real a una zona protegida, decide si se cumple y
arma las citas correspondientes.

Con varias reglas aplicables (municipal + provincial + nacional, o varias de
la misma norma), gana la más restrictiva (mayor `distancia_min_m`), citando
todas las que aplican -- no solo la que ganó (ver skill, "Geo": "Con varias,
gana la más restrictiva, citando todas").
"""

import unicodedata
from dataclasses import dataclass

from fitosanitarios.dominio.modelos import Cita


@dataclass
class ReglaCandidata:
    tipo_zona: str
    tipo_aplicacion: str  # "terrestre" | "aerea" | "todas"
    bandas: list[str]  # ["todas"] o subconjunto de {Ia,Ib,II,III,IV}
    distancia_min_m: float
    norma: str
    articulo: str | None
    jurisdiccion_id: str | None  # None en reglas provinciales/nacionales
    observaciones: str | None = None
    fuente: str = "csv"  # "pdf_extraido": leída del texto de la norma, sin filas en reglas.csv
    # False (N): prohibición, es la única que usa el dictamen. True (S): regla
    # condicional, solo para consultas (ver `excepciones_aplicables`).
    permitido: bool = False
    condiciones: str | None = None


@dataclass
class ChequeoDistanciaZona:
    cumple: bool
    zona_tipo: str
    zona_nombre: str
    distancia_real_m: float
    distancia_min_aplicable_m: float
    citas: list[Cita]
    advertencias: list[str]


def texto_plano(texto: str) -> str:
    """Minúsculas, sin tildes y con `_ - , ;` como espacios: para comparar lo que escribe el
    LLM o el usuario con los valores del catálogo."""
    sin_tildes = "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )
    plano = sin_tildes.lower()
    for separador in "_-,;":
        plano = plano.replace(separador, " ")
    return " ".join(plano.split())


def normalizar_tipo_aplicacion(texto: str | None) -> str | None:
    """"aérea", "Aereo", "con avión", "terrestre" -> "aerea" / "terrestre"; `None` si no se
    reconoce. Las reglas se comparan con estos dos valores exactos: un "aérea" que llegara
    sin normalizar no coincidiría con ninguna y el dictamen ignoraría la distancia."""
    palabras = texto_plano(texto or "").split()
    if any(p.startswith(("aere", "avion", "dron")) for p in palabras):
        return "aerea"
    if any(p.startswith(("terre", "mosquito", "pulveriz", "mochila")) for p in palabras):
        return "terrestre"
    return None


def _coincide(r: ReglaCandidata, tipo_zona: str, tipo_aplicacion: str, banda: str) -> bool:
    return (
        r.tipo_zona == tipo_zona
        and r.tipo_aplicacion in (tipo_aplicacion, "todas")
        and (r.bandas == ["todas"] or banda in r.bandas)
    )


def reglas_aplicables(
    reglas: list[ReglaCandidata], tipo_zona: str, tipo_aplicacion: str, banda: str
) -> list[ReglaCandidata]:
    """Solo las prohibiciones (N): las condicionales (S) no bloquean nada."""
    return [
        r for r in reglas
        if not r.permitido and _coincide(r, tipo_zona, tipo_aplicacion, banda)
    ]


def excepciones_aplicables(
    reglas: list[ReglaCandidata],
    tipo_zona: str,
    tipo_aplicacion: str,
    banda: str,
    distancia_real_m: float,
) -> list[ReglaCandidata]:
    """Reglas condicionales (S) que habilitan aplicar a `distancia_real_m`: las
    que aplican a esa zona, aplicación y banda y cuya distancia mínima ya se
    respeta. Cada una trae sus `condiciones`. Para responder "¿puedo aplicar a X
    metros bajo alguna condición?"; el dictamen no las usa."""
    return [
        r for r in reglas
        if r.permitido
        and _coincide(r, tipo_zona, tipo_aplicacion, banda)
        and distancia_real_m >= r.distancia_min_m
    ]


def evaluar_distancia_zona(
    zona_tipo: str,
    zona_nombre: str,
    distancia_real_m: float,
    reglas: list[ReglaCandidata],
    tipo_aplicacion: str,
    banda: str,
) -> ChequeoDistanciaZona | None:
    """`None` si no hay ninguna regla aplicable a esta combinación de zona,
    aplicación y banda -- quien llama lo traduce a `SIN_REGLA_APLICABLE`."""
    candidatas = reglas_aplicables(reglas, zona_tipo, tipo_aplicacion, banda)
    if not candidatas:
        return None

    mas_restrictiva = max(candidatas, key=lambda r: r.distancia_min_m)
    cumple = distancia_real_m >= mas_restrictiva.distancia_min_m

    citas = [
        Cita(
            fuente="normativa",
            jurisdiccion_id=r.jurisdiccion_id,
            norma=r.norma,
            articulo=r.articulo,
        )
        for r in candidatas
    ]
    advertencias = [r.observaciones for r in candidatas if r.observaciones]

    return ChequeoDistanciaZona(
        cumple=cumple,
        zona_tipo=zona_tipo,
        zona_nombre=zona_nombre,
        distancia_real_m=distancia_real_m,
        distancia_min_aplicable_m=mas_restrictiva.distancia_min_m,
        citas=citas,
        advertencias=advertencias,
    )
