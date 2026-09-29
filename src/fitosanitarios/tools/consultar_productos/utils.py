"""Auxiliares de `consultar_productos`."""

import re

from fitosanitarios.servicios.reglas import texto_plano

# Bandas "hasta" una banda máxima (Ia es la más peligrosa, IV la menos): la banda
# máxima es la más peligrosa que se acepta, así que entran ella y las menos peligrosas
# ("III" = III y IV; "banda verde" = solo IV). Estaba al revés: "IV" traía todas.
_BANDAS_HASTA = {
    "Ia": ["Ia", "Ib", "II", "III", "IV"],
    "Ib": ["Ib", "II", "III", "IV"],
    "II": ["II", "III", "IV"],
    "III": ["III", "IV"],
    "IV": ["IV"],
}


def bandas_hasta(banda_maxima: str | None) -> list[str] | None:
    """Las bandas que entran cuando el operario pide "hasta" una banda máxima;
    `None` si no la pidió o no existe."""
    return _BANDAS_HASTA.get(banda_maxima) if banda_maxima else None


def intersectar_bandas(*grupos: list[str] | None) -> list[str] | None:
    """Las bandas que cumplen todos los filtros dados (`None` = ese filtro no se dio), en
    el orden de peligrosidad. `None` si no se dio ninguno."""
    dados = [g for g in grupos if g is not None]
    if not dados:
        return None
    return [b for b in _BANDAS_HASTA["Ia"] if all(b in g for g in dados)]


# Cómo lo dice el operario -> cómo lo nombra el registro (sin tildes, en minúscula).
_SINONIMOS_APTITUD = {
    "curasemilla": "terapico trat. semillas",
    "curasemillas": "terapico trat. semillas",
    "terapico": "terapico trat. semillas",
    "tratamiento de semillas": "terapico trat. semillas",
    "hormicida": "hormiguicida",
    "regulador de crecimiento": "fitoregulador",
    "fitorregulador": "fitoregulador",
    "antibabosas": "matababosas y caracoles",
}


def _variantes(palabra: str) -> set[str]:
    """"fungicidas" -> {"fungicidas", "fungicida", "fungicid"}: el singular de lo que dijo."""
    return {palabra, palabra[:-1], palabra[:-2]} if len(palabra) > 4 else {palabra}


def resolver_aptitudes(texto: str, registradas: list[str]) -> tuple[list[str], list[str]]:
    """Lo que dijo el operario ("fungicidas", "herbicidas o insecticidas", "curasemillas")
    contra las aptitudes del registro. Devuelve (las del registro que coinciden, las partes
    que no coincidieron con ninguna)."""
    por_plano = {texto_plano(r): r for r in registradas}
    elegidas: list[str] = []
    sin_resolver: list[str] = []
    for parte in re.split(r"\s+(?:y|o|e|u)\s+|/|,|;", texto, flags=re.IGNORECASE):
        parte = texto_plano(parte)
        if not parte:
            continue
        candidatos = set()
        for v in _variantes(parte):
            candidatos.add(_SINONIMOS_APTITUD.get(v, v))
        encontrada = next(
            (r for plano, r in por_plano.items() if plano in candidatos), None
        ) or next(
            (r for plano, r in por_plano.items()
             if any(len(c) >= 6 and plano.startswith(c) for c in candidatos)),
            None,
        )
        if encontrada is None:
            sin_resolver.append(parte)
        elif encontrada not in elegidas:
            elegidas.append(encontrada)
    return elegidas, sin_resolver
