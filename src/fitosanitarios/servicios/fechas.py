"""Fechas y horas en lenguaje natural, resueltas en código.

El LLM solo pasa el texto tal como lo dijo el operario ("martes", "mañana",
"25/09", "a las 8:30"): quién sabe qué día es hoy y cuál es "el próximo
martes" es este módulo, no el modelo (que no conoce la fecha actual con
confiabilidad). Todo recibe `hoy` como parámetro para poder testearse.
"""

import re
import unicodedata
from datetime import date, time, timedelta

DIAS_SEMANA = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]
_NOMBRE_DIA = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def _normalizar(texto: str) -> str:
    sin_tildes = "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )
    return " ".join(sin_tildes.lower().split())


def resolver_fecha(texto: str | None, hoy: date) -> date | None:
    """`None` si no se entiende. Un día de la semana es siempre el PRÓXIMO
    (si hoy es martes, "el martes" es dentro de 7 días)."""
    if not texto or not texto.strip():
        return None
    t = _normalizar(texto)

    if t in ("hoy", "para hoy"):
        return hoy
    if "pasado manana" in t:
        return hoy + timedelta(days=2)
    if "manana" in t:
        return hoy + timedelta(days=1)

    for indice, dia in enumerate(DIAS_SEMANA):
        if re.search(rf"\b{dia}\b", t):
            delta = (indice - hoy.weekday()) % 7 or 7
            return hoy + timedelta(days=delta)

    iso = re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", t)
    if iso:
        return _fecha_valida(int(iso[1]), int(iso[2]), int(iso[3]))

    dmy = re.search(r"\b(\d{1,2})[/\-.](\d{1,2})(?:[/\-.](\d{2,4}))?\b", t)
    if dmy:
        dia, mes = int(dmy[1]), int(dmy[2])
        if dmy[3]:
            anio = int(dmy[3])
            return _fecha_valida(anio + 2000 if anio < 100 else anio, mes, dia)
        candidata = _fecha_valida(hoy.year, mes, dia)
        if candidata is not None and candidata < hoy:
            return _fecha_valida(hoy.year + 1, mes, dia)
        return candidata
    return None


def _fecha_valida(anio: int, mes: int, dia: int) -> date | None:
    try:
        return date(anio, mes, dia)
    except ValueError:
        return None


def resolver_hora(texto: str | None) -> time | None:
    """"8", "8:30", "08.30", "8hs", "a las 14", "3 de la tarde", "9am"."""
    if not texto or not texto.strip():
        return None
    t = _normalizar(texto)
    m = re.search(r"\b(\d{1,2})(?:\s*[:.h]\s*(\d{2}))?\s*(am|pm|hs?|horas?)?\b", t)
    if not m:
        return None
    hora = int(m[1])
    minutos = int(m[2]) if m[2] else 0
    tarde = m[3] == "pm" or re.search(r"de la (tarde|noche)", t)
    manana = m[3] == "am" or "de la manana" in t
    if tarde and hora < 12:
        hora += 12
    elif manana and hora == 12:
        hora = 0
    if not (0 <= hora <= 23 and 0 <= minutos <= 59):
        return None
    return time(hora, minutos)


def fecha_legible(fecha: date) -> str:
    """"martes 22/09/2026" (fechas dd/mm/aaaa, ver skill)."""
    return f"{_NOMBRE_DIA[fecha.weekday()]} {fecha.strftime('%d/%m/%Y')}"


def hora_legible(hora: time) -> str:
    return hora.strftime("%H:%M")
