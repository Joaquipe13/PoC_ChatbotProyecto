"""Las limitaciones que impone la normativa de una
localidad -- las prohibiciones (`N`) y las reglas condicionales (`S`) del `reglas.csv`--,
filtradas por lo que el usuario preguntó, y qué opciones hay a una distancia dada.

Todo determinista, a partir de las reglas cargadas: el LLM solo interpreta la
pregunta (qué filtros pasar), nunca decide qué limitaciones existen.

Lo usan `listar_limitaciones` y `consultar_productos` (qué bandas se pueden a una
distancia de la zona urbana: "¿qué fungicidas puedo tirar con avión a 1500 m?"). Antes
estaba en `tools/listar_limitaciones/utils.py`.
"""

from dataclasses import dataclass, field

from fitosanitarios.servicios.reglas import (
    ReglaCandidata,
    excepciones_aplicables,
    normalizar_tipo_aplicacion,  # noqa: F401 -- se reexporta para la tool
    reglas_aplicables,
)
from fitosanitarios.servicios.reglas import (
    texto_plano as _plano,
)

BANDAS = ["Ia", "Ib", "II", "III", "IV"]

# Equipos que las normas cargadas no nombran: la ley y el decreto de Santa Fe hablan de
# aplicación aérea (aeronaves) y terrestre ("equipos mecánicos de arrastre o
# autopropulsados"). Se muestran con el tipo que corresponde y se avisa que es una
# suposición.
_EQUIPOS_SIN_NORMA = {"dron": "drone", "mochila": "mochila"}


def nombra_los_dos_tipos(texto: str | None) -> bool:
    """"aérea y terrestre", "avión o mosquito": el operario compara, no filtra. Gemini
    llegó a pasar "aerea y terrestre" y la normalización se quedaba con la primera."""
    palabras = _plano(texto or "").split()
    return (
        any(normalizar_tipo_aplicacion(p) == "aerea" for p in palabras)
        and any(normalizar_tipo_aplicacion(p) == "terrestre" for p in palabras)
    )


def equipo_sin_norma(texto: str | None) -> str | None:
    """"con el drone", "la mochila" -> "drone", "mochila"; `None` para los equipos que las
    normas sí contemplan (avión, mosquito, pulverizadora)."""
    for palabra in _plano(texto or "").split():
        for prefijo, equipo in _EQUIPOS_SIN_NORMA.items():
            if palabra.startswith(prefijo):
                return equipo
    return None
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


@dataclass
class TramoQueRige:
    """Bandas contiguas a las que rige la misma prohibición (la más restrictiva)."""

    bandas: list[str]
    regla: ReglaCandidata | None  # None: ninguna prohibición para esas bandas
    con_excepciones: bool = False


@dataclass
class DistanciaQueRige:
    tipo_zona: str
    tipo_aplicacion: str
    tramos: list[TramoQueRige] = field(default_factory=list)


def distancias_que_rigen(
    prohibiciones: list[ReglaCandidata],
    condicionales: list[ReglaCandidata],
    tipo_aplicacion: str | None = None,
    bandas: list[str] | None = None,
) -> list[DistanciaQueRige]:
    """Para cada zona, tipo de aplicación y banda, la prohibición más restrictiva: cuando
    rigen a la vez la ley (500 m) y una ordenanza (3000 m), manda la de 3000 m. Mismo
    criterio que el dictamen (`calcular_condiciones`). Las bandas seguidas con la misma
    regla se agrupan. `con_excepciones`: hay una condicional que cubre ese caso y puede
    levantar esa prohibición (`_puede_levantar`)."""
    if tipo_aplicacion:
        aplicaciones = [tipo_aplicacion]
    else:
        aplicaciones = [
            a for a in ("aerea", "terrestre")
            if any(p.tipo_aplicacion in (a, "todas") for p in prohibiciones)
        ]
    consultadas = [b for b in BANDAS if not bandas or b in bandas]
    resultado = []
    for zona in dict.fromkeys(p.tipo_zona for p in prohibiciones):
        for aplicacion in aplicaciones:
            tramos: list[TramoQueRige] = []
            for banda in consultadas:
                aplicables = reglas_aplicables(prohibiciones, zona, aplicacion, banda)
                # A igual distancia se cita la norma más local: es la que ninguna excepción
                # más general puede levantar.
                rige = max(
                    aplicables, key=lambda r: (r.distancia_min_m, _es_municipal(r))
                ) if aplicables else None
                # Una excepción cuenta si habilita más cerca que la distancia que rige y
                # levanta todas las prohibiciones que seguirían vigentes ahí (en Sastre, el
                # art. 51 no levanta los 3000 m de la ordenanza, aunque sí los de la ley; y
                # "banda II desde 1200 m con condiciones" no habilita nada antes de 1000 m).
                con_excepciones = rige is not None and any(
                    e.distancia_min_m < rige.distancia_min_m
                    and all(
                        _puede_levantar(e, p) for p in aplicables
                        if p.distancia_min_m > e.distancia_min_m
                    )
                    for e in excepciones_aplicables(
                        condicionales, zona, aplicacion, banda, float("inf")
                    )
                )
                if tramos and tramos[-1].regla == rige and (
                    tramos[-1].con_excepciones == con_excepciones
                ):
                    tramos[-1].bandas.append(banda)
                else:
                    tramos.append(TramoQueRige([banda], rige, con_excepciones))
            if any(t.regla is not None for t in tramos):
                resultado.append(DistanciaQueRige(zona, aplicacion, tramos))
    return resultado


@dataclass
class BandasADistancia:
    """Qué bandas se pueden aplicar a una distancia de la zona, con un tipo de aplicación.
    `con_excepcion`: solo si se cumple una regla condicional (`S`) que levanta cada
    prohibición que la alcanza. `reglas`: las que deciden (prohibiciones que alcanzan a esa
    distancia y sus excepciones), para citarlas."""

    tipo_aplicacion: str
    permitidas: list[str] = field(default_factory=list)
    con_excepcion: list[str] = field(default_factory=list)
    prohibidas: list[str] = field(default_factory=list)
    reglas: list[ReglaCandidata] = field(default_factory=list)


def _cubre(regla: ReglaCandidata, aplicacion: str, banda: str) -> bool:
    return regla.tipo_aplicacion in (aplicacion, "todas") and (
        regla.bandas == ["todas"] or banda in regla.bandas
    )


def bandas_a_distancia(
    prohibiciones: list[ReglaCandidata],
    condicionales: list[ReglaCandidata],
    distancia_m: float,
    tipo_aplicacion: str,
) -> BandasADistancia:
    """Decir una distancia y una localidad es decir qué bandas se pueden: las que ninguna
    prohibición alcanza a esa distancia. Mismo criterio que la línea "✅ III y IV · ❌ Ia,
    Ib y II" de `listar_limitaciones`. `prohibiciones` y `condicionales`, ya filtradas por
    zona."""
    resultado = BandasADistancia(tipo_aplicacion)
    restricciones = restricciones_a_distancia(
        prohibiciones, condicionales, distancia_m, tipo_aplicacion
    )
    for banda in BANDAS:
        alcanzan = [x for x in restricciones if _cubre(x.prohibicion, tipo_aplicacion, banda)]
        if not alcanzan:
            resultado.permitidas.append(banda)
            continue
        condicional = all(
            any(_cubre(e, tipo_aplicacion, banda) for e in x.excepciones) for x in alcanzan
        )
        (resultado.con_excepcion if condicional else resultado.prohibidas).append(banda)
        # Una excepción se cita solo si habilita esa banda: si no, no decide nada.
        for x in alcanzan:
            habilitantes = [e for e in x.excepciones if _cubre(e, tipo_aplicacion, banda)]
            for r in [x.prohibicion, *(habilitantes if condicional else [])]:
                if r not in resultado.reglas:
                    resultado.reglas.append(r)
    return resultado
