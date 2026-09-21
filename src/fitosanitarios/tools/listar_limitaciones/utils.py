"""Auxiliares de `listar_limitaciones`: las limitaciones que impone la normativa de una
localidad -- las prohibiciones (`N`) y las reglas condicionales (`S`) del `reglas.csv`--,
filtradas por lo que el usuario preguntó, y qué opciones hay a una distancia dada.

Todo determinista, a partir de las reglas cargadas: el LLM solo interpreta la
pregunta (qué filtros pasar), nunca decide qué limitaciones existen.
"""

from dataclasses import dataclass, field

from fitosanitarios.servicios.reglas import (
    ReglaCandidata,
    excepciones_aplicables,
    normalizar_tipo_aplicacion,  # noqa: F401 -- se reexporta para la tool
)
from fitosanitarios.servicios.reglas import (
    texto_plano as _plano,
)

BANDAS = ["Ia", "Ib", "II", "III", "IV"]
_COLOR = {
    "roja": ["Ia", "Ib"], "rojo": ["Ia", "Ib"], "amarilla": ["II"], "amarillo": ["II"],
    "azul": ["III"], "verde": ["IV"],
}
_ZONAS = {
    "zona_urbana": ("zona urbana", "urbana", "planta urbana", "casco urbano", "pueblo", "ciudad"),
    "escuela": ("escuela", "escuelas", "colegio", "establecimiento educativo", "educativo"),
    "curso_agua": ("curso de agua", "cursos de agua", "agua", "arroyo", "canal", "laguna"),
}


def normalizar_bandas(texto: str | None) -> list[str] | None:
    """"III", "banda azul", "roja" -> ["III"], ["III"], ["Ia", "Ib"]. `None` si no se
    indicó; `[]` si se indicó pero no se entiende (quien llama lo informa)."""
    if not texto or not texto.strip():
        return None
    plano = _plano(texto)
    encontradas: list[str] = []
    for palabra in plano.split():
        if palabra in _COLOR:
            encontradas.extend(_COLOR[palabra])
        elif palabra in {b.lower() for b in BANDAS}:
            encontradas.append(next(b for b in BANDAS if b.lower() == palabra))
    return list(dict.fromkeys(encontradas))


def normalizar_tipo_zona(texto: str | None) -> str | None:
    """"escuelas", "zona urbana", "un arroyo" -> "escuela", "zona_urbana", "curso_agua".
    Un valor que no se reconoce se devuelve como vino (con `_`): puede ser un tipo
    que solo existe en una norma."""
    if not texto or not texto.strip():
        return None
    plano = _plano(texto)
    for tipo, sinonimos in _ZONAS.items():
        if plano == tipo.replace("_", " ") or any(s in plano for s in sinonimos):
            return tipo
    return plano.replace(" ", "_")


def _coincide(
    r: ReglaCandidata, tipo_zona: str | None, tipo_aplicacion: str | None,
    bandas: list[str] | None,
) -> bool:
    if tipo_zona and r.tipo_zona != tipo_zona:
        return False
    if tipo_aplicacion and r.tipo_aplicacion not in (tipo_aplicacion, "todas"):
        return False
    if bandas and r.bandas != ["todas"] and not set(bandas) & set(r.bandas):
        return False
    return True


def filtrar_reglas(
    reglas: list[ReglaCandidata], tipo_zona: str | None = None,
    tipo_aplicacion: str | None = None, bandas: list[str] | None = None,
) -> list[ReglaCandidata]:
    return [r for r in reglas if _coincide(r, tipo_zona, tipo_aplicacion, bandas)]


def _es_municipal(r: ReglaCandidata) -> bool:
    return r.jurisdiccion_id is not None  # las provinciales y nacionales no tienen localidad


def _puede_levantar(excepcion: ReglaCandidata, prohibicion: ReglaCandidata) -> bool:
    """Una excepción no levanta una prohibición más local que ella: la ley provincial
    admite excepciones por ordenanza, pero si la ordenanza de la localidad prohíbe,
    esa excepción no está disponible. En cambio una ordenanza sí puede autorizar lo que
    la ley provincial prohíbe."""
    return _es_municipal(excepcion) or not _es_municipal(prohibicion)


@dataclass
class RestriccionADistancia:
    """Una prohibición que alcanza a la distancia consultada y las reglas
    condicionales (`S`) que permitirían aplicar igual a esa distancia."""

    prohibicion: ReglaCandidata
    excepciones: list[ReglaCandidata] = field(default_factory=list)


def restricciones_a_distancia(
    prohibiciones: list[ReglaCandidata],
    condicionales: list[ReglaCandidata],
    distancia_m: float,
    tipo_aplicacion: str | None = None,
    bandas: list[str] | None = None,
) -> list[RestriccionADistancia]:
    """Las prohibiciones cuya distancia mínima supera `distancia_m` (a esa distancia
    no se puede), cada una con las condicionales que habilitan aplicar ahí. Usa el
    mismo criterio que `excepciones_aplicables`: la `S` aplica a esa zona,
    aplicación y banda, su distancia mínima ya se respeta y no es de una norma más
    general que la prohibición (`_puede_levantar`). `tipo_aplicacion` y
    `bandas`, si la consulta los acotó, limitan también las excepciones."""
    resultado = []
    for p in prohibiciones:
        if p.distancia_min_m <= distancia_m:
            continue
        if tipo_aplicacion:
            aplicaciones = [tipo_aplicacion]
        elif p.tipo_aplicacion == "todas":
            aplicaciones = ["terrestre", "aerea"]
        else:
            aplicaciones = [p.tipo_aplicacion]
        alcanzadas = BANDAS if p.bandas == ["todas"] else p.bandas
        if bandas:
            alcanzadas = [b for b in alcanzadas if b in bandas]
        habilitantes: list[ReglaCandidata] = []
        for aplicacion in aplicaciones:
            for banda in alcanzadas:
                for e in excepciones_aplicables(
                    condicionales, p.tipo_zona, aplicacion, banda, distancia_m
                ):
                    if e not in habilitantes and _puede_levantar(e, p):
                        habilitantes.append(e)
        resultado.append(RestriccionADistancia(p, habilitantes))
    return resultado
