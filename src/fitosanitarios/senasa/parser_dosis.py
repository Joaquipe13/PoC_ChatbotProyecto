"""Parser de dosis en texto libre, tal como viene en `aplicacionesPorProducto[].dosis`.

Nunca inventa un valor: si el texto no matchea un patrón conocido, se devuelve
`parseable=False` con el texto original intacto, y el resto del pipeline lo
trata como "sin dosis registrada" (ver skill, sección "Dosis" y "Matching de
productos"; plandefases.md Fase 2, tarea 7).

Casos cubiertos, con ejemplos reales o citados en la skill:
- valor simple con unidad por hectárea: "2 L/ha"
- rango con guion/en-dash, unidad repetida o no: "1,9 L/ha – 2,2 L/ha"
- dosis por volumen de caldo (requiere volumen/ha para convertir, eso lo hace
  servicios/dosis.py en la Fase 5, no este parser): "17 ml/ 100 Litros"
  (dato real relevado del producto SENASA reg. 40465, "FOCUS MAX")
- unidades cm3/cc/g/kg además de L/ml
- coma decimal
"""

import re
from typing import Literal

from pydantic import BaseModel

_NUM = r"(\d+(?:[.,]\d+)?)"
_UNIDAD_CANTIDAD = r"(l|ml|cm3|cm³|cc|g|kg)"
_SEP_RANGO = r"(?:-|–|—|a)"

# Rango entre dos números, con lo que sea entre medio (ej. "150-200 cm3/ha" con
# nada entre medio, o "1,9 L/ha – 2,2 L/ha" con la unidad del primer número
# también presente). Solo se exige la unidad después del segundo número -- es
# la que siempre está en los datos reales relevados -- y se usa esa como
# unidad del rango completo; no se valida que la del primero (si aparece)
# coincida, es best-effort para un parser de POC, no un parser de lenguaje
# natural genérico.
_PATRON_RANGO = re.compile(
    rf"{_NUM}[^\d]*?{_SEP_RANGO}\s*{_NUM}\s*{_UNIDAD_CANTIDAD}\b",
    re.IGNORECASE,
)
_PATRON_SIMPLE = re.compile(rf"{_NUM}\s*{_UNIDAD_CANTIDAD}\b", re.IGNORECASE)
_PATRON_HA = re.compile(r"/\s*ha\b", re.IGNORECASE)
_PATRON_100L = re.compile(r"/\s*100\s*l(?:itros)?\b", re.IGNORECASE)

_NORMALIZACION_UNIDAD_CANTIDAD = {
    "l": "L",
    "ml": "ml",
    "cm3": "cm³",
    "cm³": "cm³",
    "cc": "cm³",
    "g": "g",
    "kg": "kg",
}


class DosisParseada(BaseModel):
    texto_original: str
    parseable: bool
    valor_min: float | None = None
    valor_max: float | None = None
    unidad: str | None = None  # ej. "L/ha", "ml/100L"
    base: Literal["superficie", "volumen_caldo"] | None = None


def _a_float(numero: str) -> float:
    return float(numero.replace(",", "."))


def parsear_dosis(texto: str | None) -> DosisParseada:
    texto = (texto or "").strip()
    if not texto:
        return DosisParseada(texto_original=texto, parseable=False)

    match_rango = _PATRON_RANGO.search(texto)
    if match_rango:
        num1, num2, unidad2 = match_rango.groups()
        unidad_cantidad = _NORMALIZACION_UNIDAD_CANTIDAD[unidad2.lower()]
        valores = sorted([_a_float(num1), _a_float(num2)])
    else:
        coincidencias = list(_PATRON_SIMPLE.finditer(texto))
        if len(coincidencias) != 1:
            # 0 matches: no hay dosis reconocible. 2+ matches sin un separador
            # de rango explícito: ambiguo, no se adivina si es un rango o dos
            # dosis distintas.
            return DosisParseada(texto_original=texto, parseable=False)
        unidad_cantidad = _NORMALIZACION_UNIDAD_CANTIDAD[coincidencias[0].group(2).lower()]
        valor_unico = _a_float(coincidencias[0].group(1))
        valores = [valor_unico, valor_unico]

    if _PATRON_100L.search(texto):
        base: Literal["superficie", "volumen_caldo"] = "volumen_caldo"
        unidad = f"{unidad_cantidad}/100L"
    elif _PATRON_HA.search(texto):
        base = "superficie"
        unidad = f"{unidad_cantidad}/ha"
    else:
        return DosisParseada(texto_original=texto, parseable=False)

    return DosisParseada(
        texto_original=texto,
        parseable=True,
        valor_min=valores[0],
        valor_max=valores[-1],
        unidad=unidad,
        base=base,
    )
