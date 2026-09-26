"""Auxiliares de `consultar_productos`."""

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
