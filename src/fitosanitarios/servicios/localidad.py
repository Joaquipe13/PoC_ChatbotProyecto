"""Resolución de la localidad/municipio donde se va a aplicar, a partir del
texto que dio el usuario (o que trae la receta).

Reemplaza a la resolución por punto en polígono: ya no se compara contra la
ubicación exacta del lote, alcanza con saber en qué localidad cargada cae la
aplicación para elegir las reglas de distancia que le corresponden.
"""

import unicodedata
from dataclasses import dataclass, field


@dataclass
class Jurisdiccion:
    id: int
    jurisdiccion_id: str
    nombre: str
    provincia_id: int


@dataclass
class Ubicacion:
    """Dónde se aplica, para elegir la normativa que corresponde. Si la
    localidad no está cargada solo se conoce la provincia (`localidad_id`
    None): se usa la normativa provincial y hay que aclararlo."""

    nombre: str
    provincia_id: int
    localidad_id: int | None = None
    jurisdiccion_id: str | None = None
    # La localidad existe pero no tiene ordenanzas cargadas, o no existe.
    con_normativa_municipal: bool = False


@dataclass
class ResolucionLocalidad:
    localidad: Jurisdiccion | None = None
    # Varias localidades coinciden con el texto: hay que preguntar, nunca elegir.
    ambiguas: list[Jurisdiccion] = field(default_factory=list)


def _normalizar(texto: str) -> str:
    sin_tildes = unicodedata.normalize("NFD", texto)
    sin_tildes = "".join(c for c in sin_tildes if unicodedata.category(c) != "Mn")
    return " ".join(sin_tildes.lower().replace("-", " ").replace(",", " ").split())


def resolver_localidad(texto: str, cargadas: list[Jurisdiccion]) -> ResolucionLocalidad:
    """Coincidencia exacta (por nombre o `jurisdiccion_id`, sin tildes ni
    mayúsculas) primero; si no hay, el nombre de la localidad contenido en el
    texto ("El Trébol, Santa Fe") o al revés. Sin coincidencia devuelve una
    resolución vacía (quien llama lo traduce a `JURISDICCION_NO_CUBIERTA`)."""
    buscado = _normalizar(texto)
    if not buscado:
        return ResolucionLocalidad()

    exactas = [
        j for j in cargadas
        if buscado in (_normalizar(j.nombre), _normalizar(j.jurisdiccion_id))
    ]
    if len(exactas) == 1:
        return ResolucionLocalidad(localidad=exactas[0])
    if len(exactas) > 1:
        return ResolucionLocalidad(ambiguas=exactas)

    parciales = [
        j for j in cargadas
        if f" {_normalizar(j.nombre)} " in f" {buscado} "
        or f" {buscado} " in f" {_normalizar(j.nombre)} "
    ]
    if len(parciales) == 1:
        return ResolucionLocalidad(localidad=parciales[0])
    return ResolucionLocalidad(ambiguas=parciales)
