"""Motor de reglas determinista: de las reglas de distancia candidatas (municipal +
provincial + nacional), cuáles aplican a un tipo de zona, de aplicación y banda.

Quien las usa se queda con la más restrictiva (mayor `distancia_min_m`) y cita todas
las que aplican, no solo la que ganó (ver skill, "Geo").
"""

import unicodedata
from dataclasses import dataclass

# Convención de `reglas.csv` para "prohibido en toda la jurisdicción, sin
# distancia máxima" (22/09/2026, ver DECISIONES.md, "Localidades y normas sin
# fuente oficial"): el modelo no tiene un valor "infinito", así que se carga
# como una distancia grande y se muestra distinto (ver
# `tools/listar_limitaciones/mensajes.py`).
DISTANCIA_SIN_LIMITE_M = 99999.0


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


