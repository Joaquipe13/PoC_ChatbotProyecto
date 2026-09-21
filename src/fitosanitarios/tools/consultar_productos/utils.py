"""Auxiliares de `consultar_productos`."""

# Bandas "hasta" una banda máxima (Ia es la más peligrosa, IV la menos).
_BANDAS_HASTA = {
    "Ia": ["Ia"],
    "Ib": ["Ia", "Ib"],
    "II": ["Ia", "Ib", "II"],
    "III": ["Ia", "Ib", "II", "III"],
    "IV": ["Ia", "Ib", "II", "III", "IV"],
}


def bandas_hasta(banda_maxima: str | None) -> list[str] | None:
    """Las bandas que entran cuando el operario pide "hasta" una banda máxima;
    `None` si no la pidió o no existe."""
    return _BANDAS_HASTA.get(banda_maxima) if banda_maxima else None
