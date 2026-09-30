"""Limpieza y normalización de campos crudos de SENASA.

Fuente de los casos a cubrir: skill agente-fitosanitarios (sección "SENASA
(vademécum)") + verificación en vivo del 12/09/2026 (ver DECISIONES.md).
"""

import re

_TAG_HTML = re.compile(r"<[^>]+>")
_ESPACIOS_REPETIDOS = re.compile(r"\s+")

# Roman numeral / clase tal como viene en claseToxicologica.claseTox -> banda normalizada.
_MAPA_BANDA = {
    "IA": "Ia",
    "IB": "Ib",
    "II": "II",
    "III": "III",
    "IV": "IV",
}

# Colores esperados por banda + errores de tipeo relevados por la cátedra
# (ver skill: "AMAREILLO"). No se inventan variantes no observadas.
_MAPA_COLOR = {
    "ROJO": "rojo",
    "AMARILLO": "amarillo",
    "AMAREILLO": "amarillo",  # typo real documentado en la skill
    "AZUL": "azul",
    "VERDE": "verde",
}


def limpiar_html(texto: str) -> str:
    """Saca tags HTML simples (p. ej. <b>48%</b> en sustanciasActivas) y
    colapsa espacios. No interpreta el HTML, solo lo descarta."""
    sin_tags = _TAG_HTML.sub("", texto)
    return _ESPACIOS_REPETIDOS.sub(" ", sin_tags).strip()


def normalizar_nombre(texto: str) -> str:
    """Normaliza mayúsculas de nombres (marca, cultivo, etc.) a Title Case.

    Limitación conocida: no restituye tildes faltantes (SENASA suele mandar
    "ALGODON" sin tilde) -- eso requeriría un diccionario de dominio que no
    forma parte de esta fase. El nombre queda "Algodon", no "Algodón".
    """
    return " ".join(palabra.capitalize() for palabra in texto.strip().split())


def normalizar_banda(clase_tox_raw: str | None) -> str | None:
    """A partir de claseToxicologica.claseTox (ej. 'IV', 'Ia'). Devuelve None
    si no es una de las 5 bandas conocidas -- nunca se inventa una banda."""
    if not clase_tox_raw:
        return None
    return _MAPA_BANDA.get(clase_tox_raw.strip().upper())


def normalizar_color_banda(color_raw: str | None) -> str | None:
    """A partir de claseToxicologica.color. Devuelve None si no es un color
    conocido (incluye la variante con error de tipeo 'AMAREILLO' -> 'amarillo')."""
    if not color_raw:
        return None
    return _MAPA_COLOR.get(color_raw.strip().upper())
