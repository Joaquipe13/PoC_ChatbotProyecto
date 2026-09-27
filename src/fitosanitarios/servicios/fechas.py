"""Fechas y horas en lenguaje natural, resueltas en código.

El LLM solo pasa el texto tal como lo dijo el operario ("martes", "mañana",
"25/09", "a las 8:30"): quién sabe qué día es hoy y cuál es "el próximo
martes" es este módulo, no el modelo (que no conoce la fecha actual con
confiabilidad). Todo recibe `hoy` como parámetro para poder testearse.
"""

import re
import unicodedata
from datetime import date, datetime, time, timedelta, timezone

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


_MAX_DIAS_RANGO = 31
_RE_RANGO = re.compile(r"^(?:del?\s+)?(.+?)\s+(?:al|a|hasta(?:\s+el)?)\s+(.+)$")
_RE_SEPARADOR_DIAS = re.compile(r"\s*(?:,|\by\b|\be\b)\s*")


def resolver_dias(texto: str | None, hoy: date) -> list[date] | None:
    """Los días que pide el operario, en orden: "semana" (o "semanal") es de lunes a
    sábado de esta semana ("la semana que viene", de la próxima); "del lunes al
    miércoles" es un rango; "jueves y viernes", una lista; si no, un solo día como
    `resolver_fecha`. `None` si no se entiende. En un rango o una lista, cada día
    es el primero que cae desde el anterior: "jueves y viernes" es ese jueves y el
    viernes que le sigue."""
    if not texto or not texto.strip():
        return None
    t = _normalizar(texto)

    if "semana" in t:
        lunes = hoy - timedelta(days=hoy.weekday())
        if hoy.weekday() == 6 or re.search(r"que viene|proxima|siguiente", t):
            lunes += timedelta(days=7)
        return [lunes + timedelta(days=i) for i in range(6)]

    rango = _RE_RANGO.match(t)
    if rango:
        desde = resolver_fecha(rango[1], hoy)
        hasta = _desde(rango[2], desde, hoy) if desde else None
        if desde and hasta and 0 <= (hasta - desde).days < _MAX_DIAS_RANGO:
            return [desde + timedelta(days=i) for i in range((hasta - desde).days + 1)]

    partes = [p for p in _RE_SEPARADOR_DIAS.split(t) if p]
    if len(partes) > 1:
        dias: list[date] = []
        for parte in partes:
            dia = _desde(parte, dias[-1], hoy) if dias else resolver_fecha(parte, hoy)
            if dia is None:
                break
            dias.append(dia)
        else:
            return sorted(set(dias))

    dia = resolver_fecha(texto, hoy)
    return [dia] if dia else None


def _desde(texto: str, desde: date, hoy: date) -> date | None:
    """Como `resolver_fecha`, pero un día de la semana es el primero desde `desde`
    inclusive, no desde el día siguiente a hoy ("mañana" o "25/09" siguen siendo
    relativos a hoy)."""
    for indice, dia in enumerate(DIAS_SEMANA):
        if re.search(rf"\b{dia}\b", texto):
            return desde + timedelta(days=(indice - desde.weekday()) % 7)
    return resolver_fecha(texto, hoy)


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


# Argentina no tiene horario de verano: UTC-3 todo el año.
HORA_ARGENTINA = timezone(timedelta(hours=-3))


def momento_legible(momento: datetime) -> str:
    """"sábado 26/09/2026, 23:31", en hora de Argentina. La base guarda los eventos en
    UTC y se mostraban así ("2026-09-27T02:31:15+00:00": otro día y otra hora)."""
    if momento.tzinfo is not None:
        momento = momento.astimezone(HORA_ARGENTINA)
    return f"{fecha_legible(momento.date())}, {momento.strftime('%H:%M')}"
