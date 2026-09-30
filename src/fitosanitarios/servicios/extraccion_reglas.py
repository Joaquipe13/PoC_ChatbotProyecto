"""Reglas de distancia leídas del texto de una norma (PDF) cuando su carpeta
no trae `reglas.csv`. Determinista: un parser sobre las oraciones del
artículo, sin LLM -- el mismo texto da siempre las mismas reglas.

El `reglas.csv` sigue siendo la fuente preferida (lo revisa una persona). Sin
él, se aceptan solo las **prohibiciones firmes**: una oración que prohíbe
aplicar, con una única distancia, una única zona y clases toxicológicas
explícitas (o ninguna, que vale para todas). Se descarta todo lo demás:
excepciones, permisos condicionados, trámites, rangos, varias distancias o
zonas en una misma oración, y cualquier redacción que el parser no entienda
del todo. Ante la duda, no se extrae.

Las clases toxicológicas se traducen a bandas con una tabla fija (A/B/C/D y
colores). Lo que se extrae se guarda con `fuente='pdf_extraido'` para que la
respuesta avise que hay que verificarlo con la norma.
"""

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Clasificación toxicológica: las leyes viejas usan A/B/C/D (o el color de la
# banda del marbete); SENASA usa Ia/Ib/II/III/IV. Correspondencia oficial por
# color: A roja (Ia, Ib), B amarilla (II), C azul (III), D verde (IV).
_CLASE_A_BANDAS = {
    "a": ["Ia", "Ib"], "roja": ["Ia", "Ib"], "rojo": ["Ia", "Ib"],
    "b": ["II"], "amarilla": ["II"], "amarillo": ["II"],
    "c": ["III"], "azul": ["III"],
    "d": ["IV"], "verde": ["IV"],
    "ia": ["Ia"], "ib": ["Ib"], "ii": ["II"], "iii": ["III"], "iv": ["IV"],
}

_ZONAS = {
    "zona_urbana": re.compile(
        r"(?i)plantas?\s+urbanas?|zonas?\s+urbanas?|n[uú]cleos?\s+urbanos?|"
        r"centros?\s+poblados?|ejidos?\s+urbanos?"
    ),
    "escuela": re.compile(r"(?i)\bescuelas?\b|establecimientos?\s+educativ"),
    "curso_agua": re.compile(r"(?i)cursos?\s+de\s+agua|\bcauces?\b|\barroyos?\b|\br[ií]os?\b"),
}

_PROHIBICION = re.compile(
    r"(?i)\bproh[ií]b|\bqueda\s+prohibid|\bprohibid[oa]s?\b|"
    r"\bno\s+(?:se\s+)?(?:podr[aá]n?|permitir[aá]n?)\s+(?:aplicarse|aplicar|realizarse)"
)

# Excepciones, permisos o remisiones a otra autoridad: la oración no es una
# prohibición firme.
_CONDICIONAL = re.compile(
    r"(?i)excepci|salvo|excepto|siempre\s+que|siempre\s+y\s+cuando|cuando\s+exista|"
    r"autoric|autoriz|previa|reglamentaci[oó]n|podr[aá]n?\s+(?:aplicarse|realizarse|efectuarse)|"
    r"se\s+podr[aá]|a\s+criterio|seg[uú]n\s+corresponda"
)

_DISTANCIA = re.compile(
    # `(?!\s*/)`: "8 km/hora" es una velocidad (viento), no una distancia.
    r"(\d{1,3}(?:\.\d{3})+|\d+)\s*\)?\s*(metros|mts|kil[oó]metros|km)\b(?!\s*/)", re.I
)
_NUMERO = re.compile(r"\d{1,3}(?:\.\d{3})+|\d+")
_FRASE_CLASES = re.compile(
    r"(?i:clases?|categor[ií]as?)\s+(?:(?i:toxicol[oó]gicas?)\s+)?"
    r"((?:[A-D]|Ia|Ib|II|III|IV)\b(?:\s*(?:,|y|o|e)\s*(?:[A-D]|Ia|Ib|II|III|IV)\b)*)"
)
_COLOR = re.compile(r"(?i)\b(?:banda|franja|color)\s+(roja|amarilla|azul|verde)\b")


@dataclass
class ReglaExtraida:
    tipo_zona: str
    tipo_aplicacion: str
    bandas: list[str]
    distancia_min_m: float
    oracion: str  # la oración de la norma de la que salió (para auditar)


def bandas_de_clases(clases: list[str]) -> list[str] | None:
    """`None` si alguna clase no se reconoce: nunca se adivina la banda."""
    bandas: list[str] = []
    for clase in clases:
        traducidas = _CLASE_A_BANDAS.get(str(clase).strip().lower())
        if traducidas is None:
            return None
        bandas.extend(b for b in traducidas if b not in bandas)
    return bandas or None


def _oraciones(texto: str) -> list[str]:
    limpio = texto.replace("­", "")  # guion blando que deja el PDF
    limpio = re.sub(r"\s+", " ", limpio).strip()
    # Se corta en ". " / "; " seguido de mayúscula: "3.000" no se parte.
    return [o.strip() for o in re.split(r"(?<=[.;])\s+(?=[A-ZÁÉÍÓÚÑ¿(])", limpio) if o.strip()]


def _tipo_aplicacion(oracion: str) -> str:
    aerea = re.search(r"(?i)\ba[eé]rea\b|aeroaplicaci|\baeronaves?\b|\bavi[oó]n", oracion)
    terrestre = re.search(r"(?i)\bterrestres?\b", oracion)
    if aerea and not terrestre:
        return "aerea"
    if terrestre and not aerea:
        return "terrestre"
    return "todas"


def _bandas(oracion: str) -> list[str] | None:
    """`["todas"]` si la oración no menciona clases; `None` si menciona
    clases que el parser no entiende (entonces no se extrae)."""
    encontradas: list[str] = []
    for m in _FRASE_CLASES.finditer(oracion):
        encontradas.extend(re.findall(r"Ia|Ib|III|II|IV|[A-D]", m.group(1)))
    encontradas.extend(m.group(1) for m in _COLOR.finditer(oracion))
    if not encontradas:
        if re.search(r"(?i)\bclases?\b|\bcategor[ií]as?\b|toxicol", oracion):
            return None
        return ["todas"]
    return bandas_de_clases(encontradas)


def _distancia_m(oracion: str) -> float | None:
    """La única distancia de la oración, en metros. `None` si no hay una o hay
    varias (un rango, dos radios): es ambiguo."""
    distancias = {
        (int(m.group(1).replace(".", "")) * (1000 if m.group(2).lower().startswith("k") else 1))
        for m in _DISTANCIA.finditer(oracion)
    }
    numeros = {int(n.replace(".", "")) for n in _NUMERO.findall(oracion)}
    # Cualquier otro número en la oración (otro radio, un artículo citado) la
    # vuelve ambigua, salvo el que es la propia distancia en km.
    if len(distancias) != 1:
        return None
    (distancia,) = distancias
    if len(numeros - {distancia, distancia // 1000}) > 0:
        return None
    return float(distancia)


def _zona(oracion: str) -> str | None:
    zonas = [z for z, patron in _ZONAS.items() if patron.search(oracion)]
    return zonas[0] if len(zonas) == 1 else None


def extraer_reglas_de_articulo(norma: str, numero: str, texto: str) -> list[ReglaExtraida]:
    reglas: list[ReglaExtraida] = []
    for oracion in _oraciones(texto):
        if not _PROHIBICION.search(oracion) or _CONDICIONAL.search(oracion):
            continue
        distancia = _distancia_m(oracion)
        zona = _zona(oracion)
        bandas = _bandas(oracion)
        if distancia is None or zona is None or bandas is None:
            logger.info("%s art. %s: oración descartada (ambigua): %s", norma, numero, oracion)
            continue
        reglas.append(
            ReglaExtraida(
                tipo_zona=zona, tipo_aplicacion=_tipo_aplicacion(oracion), bandas=bandas,
                distancia_min_m=distancia, oracion=oracion,
            )
        )
    return reglas


