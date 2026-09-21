"""Auxiliares de `consultar_articulo`: qué número de artículo pidió el usuario, a
qué norma se refiere y cómo se limpia el texto de un artículo del PDF para mostrarlo.
(El nombre legible de una norma, "ley-11273-1995" -> "Ley 11273/1995", es común a
varias tools: `servicios/formato.py::norma_legible`.)
"""

import re
import unicodedata

_ARCHIVO = re.compile(r"(ordenanza|decreto|resolucion|ley)-(\w+)-(\d{4})")
_TIPOS = ("ordenanza", "decreto", "resolucion", "ley")


def _sin_tildes(texto: str) -> str:
    descompuesto = unicodedata.normalize("NFD", texto)
    return "".join(c for c in descompuesto if unicodedata.category(c) != "Mn").lower()


def numero_de_articulo(texto: str | None) -> str | None:
    """Lo que el usuario escribió como número de artículo ("art. 33", "33°",
    "artículo 5 bis") -> el número tal como se guarda ("33", "5 bis"). `None` si no
    hay ningún número."""
    if not texto:
        return None
    m = re.search(r"(\d+)\s*[°º]?\s*(bis|ter|quater)?\b", _sin_tildes(texto))
    if not m:
        return None
    return f"{int(m[1])} {m[2]}" if m[2] else str(int(m[1]))


def _quitar_ceros(numero: str) -> str:
    return numero.lstrip("0") or "0"


def filtrar_normas(archivos: list[str], texto: str | None) -> list[str]:
    """Los archivos (`ley-11273-1995`) a los que puede referirse `texto` ("ley
    11.273", "la ordenanza 841/2010", "decreto 552"). Compara el número (sin puntos ni
    ceros a la izquierda) y, si el texto menciona el tipo, que coincida; el año solo
    desempata si se escribió. Sin texto devuelve todos; si nada coincide, ninguno."""
    if not texto or not texto.strip():
        return list(archivos)
    limpio = _sin_tildes(re.sub(r"(?<=\d)\.(?=\d{3}\b)", "", texto))
    numeros = {_quitar_ceros(n) for n in re.findall(r"\d+", limpio)}
    tipos = {t for t in _TIPOS if t in limpio}
    coinciden = []
    for archivo in archivos:
        m = _ARCHIVO.fullmatch(archivo)
        if not m:
            continue
        tipo, numero, anio = m[1], _quitar_ceros(m[2]), m[3]
        if numero not in numeros:
            continue
        if tipos and tipo not in tipos:
            continue
        if anio not in numeros and any(len(n) == 4 and n != numero for n in numeros):
            continue  # escribió otro año: no es esta
        coinciden.append(archivo)
    return coinciden


_ITEM = re.compile(r"^\s*(?:[a-z]|\d{1,2})\)\s")


def limpiar_texto_articulo(texto: str) -> str:
    """El texto tal como sale del PDF trae saltos de línea de la maquetación y un
    símbolo suelto al principio. Se unen las líneas cortadas a mitad de oración y se
    deja un renglón por inciso (`a)`, `1)`)."""
    texto = re.sub(r"^[^\w¿¡(\[]+", "", texto.strip())
    renglones: list[str] = []
    for linea in (renglon.strip() for renglon in texto.splitlines()):
        if not linea:
            continue
        if renglones and not _ITEM.match(linea):
            renglones[-1] += " " + linea
        else:
            renglones.append(linea)
    return "\n".join(re.sub(r"\s+", " ", r) for r in renglones)
