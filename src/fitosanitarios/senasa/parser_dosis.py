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
- abreviaturas reales del catálogo SENASA (22/09/2026): "1 litro/ha",
  "0,75 a 1 lt/ha", "3-4 lts/ha", "143gr/ha", "600-900 cm'/ha", "150-200 cc3/ha",
  la unidad entre paréntesis ("20-30 (g/ha)") y "por hectárea"
- "/hl" (hectolitro) como "/100L": "60-100 cm3/hl"

Solo se acepta una dosis por texto: si además del rango hay otra cantidad con
unidad ("600 cm3/ha (volumen: 250-300 Litros de agua/ha)", "1,4 kg/ha hasta 4
hojas – 2,5 kg/ha"), es ambiguo y no se parsea. Excepción: en una mezcla de
tanque ("150-200 cm3/ha + 240-320 cm3/ha de 2,4D") vale la dosis de antes del "+".
"""

import re
from typing import Literal

from pydantic import BaseModel

# Un número no empieza pegado a una letra ni a otro número: sin esto, el "3" de
# "cm3" arrancaba un rango ("1000 cm3/ ha  50 cm3/ hl" daba 3-50).
_NUM = r"(?<![a-z\d.,])(\d+(?:[.,]\d+)?)"
# La unidad no puede seguir con otra letra (ni "cm'" ni "gr" cierran con un
# borde de palabra, por eso no se usa \b); "(" opcional para "20-30 (g/ha)".
_UNIDAD_CANTIDAD = r"\(?\s*(l|lts?|ltrs?|litros?|ml|cm3|cm³|cm'|cc3?|g|grs?|kg)(?![a-z])"
_SEP_RANGO = r"(?:-|–|—|a)"

# Rango entre dos números, con lo que sea entre medio (ej. "150-200 cm3/ha" con
# nada entre medio, o "1,9 L/ha – 2,2 L/ha" con la unidad del primer número
# también presente). Solo se exige la unidad después del segundo número -- es
# la que siempre está en los datos reales relevados -- y se usa esa como
# unidad del rango completo; no se valida que la del primero (si aparece)
# coincida, es best-effort para un parser de POC, no un parser de lenguaje
# natural genérico.
_PATRON_RANGO = re.compile(
    rf"{_NUM}[^\d]*?{_SEP_RANGO}\s*{_NUM}\s*{_UNIDAD_CANTIDAD}",
    re.IGNORECASE,
)
_PATRON_SIMPLE = re.compile(rf"{_NUM}\s*{_UNIDAD_CANTIDAD}", re.IGNORECASE)
# "O,5 L/ha": una O pegada a ",dígito" es un cero mal tipeado en SENASA.
_PATRON_O_POR_CERO = re.compile(r"\bO(?=[.,]\d)")
_PATRON_HA = re.compile(r"(?:/\s*|\bpor\s+)(?:ha|hect[aá]rea)\b", re.IGNORECASE)
# Se saca del texto antes de buscar la cantidad: si no, "100 litros" se leería
# como una segunda dosis.
_PATRON_100L = re.compile(r"/\s*(?:100\s*(?:l|lts?|ltrs?|litros?)\b\.?|hl\b)", re.IGNORECASE)

_NORMALIZACION_UNIDAD_CANTIDAD = {
    "l": "L",
    "lt": "L",
    "lts": "L",
    "ltr": "L",
    "ltrs": "L",
    "litro": "L",
    "litros": "L",
    "ml": "ml",
    "cm3": "cm³",
    "cm³": "cm³",
    "cm'": "cm³",
    "cc": "cm³",
    "cc3": "cm³",
    "g": "g",
    "gr": "g",
    "grs": "g",
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
    resultado = _parsear(_PATRON_O_POR_CERO.sub("0", texto)) if texto else None
    if resultado is None and "+" in texto:
        # Mezcla de tanque: "150-200 cm3/ha + 240-320 cm3/ha de 2,4D". La dosis
        # del producto es la de antes del "+"; lo de después es de otro producto
        # (tiene que nombrarlo: "2 L/ha + 500 g/ha" sigue siendo ambiguo).
        propia, _, companero = _PATRON_O_POR_CERO.sub("0", texto).partition("+")
        if _nombra_otro_producto(companero):
            resultado = _parsear(propia)
    if resultado is None:
        return DosisParseada(texto_original=texto, parseable=False)
    valor_min, valor_max, unidad, base = resultado
    return DosisParseada(
        texto_original=texto,
        parseable=True,
        valor_min=valor_min,
        valor_max=valor_max,
        unidad=unidad,
        base=base,
    )


def _nombra_otro_producto(texto: str) -> bool:
    sin_cantidades = _PATRON_HA.sub(" ", _PATRON_SIMPLE.sub(" ", _PATRON_100L.sub(" ", texto)))
    return re.search(r"[^\W\d_]{2,}", sin_cantidades) is not None


def _parsear(texto: str) -> tuple[float, float, str, Literal["superficie", "volumen_caldo"]] | None:
    cantidades = _PATRON_100L.sub(" ", texto)
    match_rango = _PATRON_RANGO.search(cantidades)
    if match_rango:
        fuera_del_rango = cantidades[: match_rango.start()] + " " + cantidades[match_rango.end():]
        if _PATRON_SIMPLE.search(fuera_del_rango):
            # Otra cantidad con unidad además del rango: no se adivina cuál es la dosis.
            return None
        num1, num2, unidad2 = match_rango.groups()
        unidad_cantidad = _NORMALIZACION_UNIDAD_CANTIDAD[unidad2.lower()]
        valores = sorted([_a_float(num1), _a_float(num2)])
    else:
        coincidencias = list(_PATRON_SIMPLE.finditer(cantidades))
        if len(coincidencias) != 1:
            # 0 matches: no hay dosis reconocible. 2+ matches sin un separador
            # de rango explícito: ambiguo, no se adivina si es un rango o dos
            # dosis distintas.
            return None
        if re.search(r"[-–—]\s*$", cantidades[: coincidencias[0].start()]):
            # "0,.3 – 0,4 l/ha": un rango con el primer número roto, no una dosis sola.
            return None
        unidad_cantidad = _NORMALIZACION_UNIDAD_CANTIDAD[coincidencias[0].group(2).lower()]
        valor_unico = _a_float(coincidencias[0].group(1))
        valores = [valor_unico, valor_unico]

    if _PATRON_100L.search(texto):
        return valores[0], valores[-1], f"{unidad_cantidad}/100L", "volumen_caldo"
    if _PATRON_HA.search(texto):
        return valores[0], valores[-1], f"{unidad_cantidad}/ha", "superficie"
    return None
