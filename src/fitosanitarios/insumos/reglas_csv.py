"""Lectura del `reglas.csv` único de `data/insumos/` (ver docs/contrato-insumos.md).

Un solo archivo para todas las jurisdicciones. Cada fila dice a cuál pertenece:

- municipal: `provincia` = carpeta de la provincia, `jurisdiccion` = carpeta de la localidad.
- provincial: `provincia` vacía, `jurisdiccion` = carpeta de la provincia.
- nacional: `provincia` vacía, `jurisdiccion` = ARGENTINA o NACIONAL.

`permitido`: `N` es una prohibición (dentro de `distancia_min_m` no se puede; es
lo único que usa el dictamen y el agendado). `S` es una regla condicional: a
partir de `distancia_min_m` se puede si se cumplen las `condiciones` (solo para
consultas, nunca bloquea).

Se aceptan mayúsculas o minúsculas y `_` por `-` en provincia y jurisdicción.
"""

import csv
from dataclasses import dataclass
from pathlib import Path

COLUMNAS = [
    "provincia", "jurisdiccion", "tipo_zona", "tipo_aplicacion", "banda_toxicologica",
    "distancia_min_m", "permitido", "condiciones", "norma", "articulo", "observaciones",
]
JURISDICCIONES_NACIONALES = {"argentina", "nacional"}
TIPOS_APLICACION = {"terrestre", "aerea", "todas"}
_BANDAS = {"ia": "Ia", "ib": "Ib", "ii": "II", "iii": "III", "iv": "IV"}
_SI = {"s", "si", "sí"}
_NO = {"n", "no"}


class ErrorFila(ValueError):
    """Una fila del `reglas.csv` no respeta el formato."""


@dataclass(frozen=True)
class FilaRegla:
    linea: int  # línea del archivo (1 = encabezado), para los mensajes de error
    provincia: str | None
    jurisdiccion: str
    tipo_zona: str
    tipo_aplicacion: str
    bandas: list[str]  # ["todas"] o subconjunto de {Ia, Ib, II, III, IV}
    distancia_min_m: float
    permitido: bool  # False = N (prohibición), True = S (regla condicional)
    condiciones: str | None
    norma: str
    articulo: str | None
    observaciones: str | None

    @property
    def alcance(self) -> tuple[str, ...]:
        """Misma forma que `estructura.alcance_de_carpeta`."""
        if self.jurisdiccion in JURISDICCIONES_NACIONALES:
            return ("nacional",)
        if self.provincia is None:
            return ("provincial", self.jurisdiccion)
        return ("municipal", self.provincia, self.jurisdiccion)


def _slug(valor: str | None) -> str | None:
    valor = (valor or "").strip().lower().replace("_", "-")
    return valor or None


def _texto(valor: str | None) -> str | None:
    return (valor or "").strip() or None


def _bandas(campo: str | None) -> list[str]:
    campo = (campo or "").strip()
    if not campo:
        raise ErrorFila("banda_toxicologica vacía (usar todas o Ia;Ib;II;III;IV)")
    if campo.lower() == "todas":
        return ["todas"]
    bandas = []
    for parte in campo.split(";"):
        parte = parte.strip()
        if parte.lower() not in _BANDAS:
            raise ErrorFila(f"banda '{parte}' desconocida (Ia, Ib, II, III, IV o todas)")
        bandas.append(_BANDAS[parte.lower()])
    return bandas


def _permitido(campo: str | None) -> bool:
    valor = (campo or "").strip().lower()
    if valor in _SI:
        return True
    if valor in _NO:
        return False
    raise ErrorFila(f"permitido '{campo}' inválido (S o N)")


def normalizar_fila(fila: dict, linea: int) -> FilaRegla:
    """Raises: `ErrorFila` con el motivo, sin el número de línea."""
    jurisdiccion = _slug(fila.get("jurisdiccion"))
    if jurisdiccion is None:
        raise ErrorFila("jurisdiccion vacía")
    provincia = _slug(fila.get("provincia"))
    if jurisdiccion in JURISDICCIONES_NACIONALES:
        provincia = None

    tipo_aplicacion = (fila.get("tipo_aplicacion") or "").strip().lower()
    if tipo_aplicacion not in TIPOS_APLICACION:
        raise ErrorFila(
            f"tipo_aplicacion '{fila.get('tipo_aplicacion')}' inválido (terrestre, aerea o todas)"
        )
    tipo_zona = (fila.get("tipo_zona") or "").strip().lower()
    if not tipo_zona:
        raise ErrorFila("tipo_zona vacío")
    try:
        distancia = float((fila.get("distancia_min_m") or "").strip())
    except ValueError:
        raise ErrorFila(
            f"distancia_min_m '{fila.get('distancia_min_m')}' no es un número"
        ) from None
    if distancia < 0:
        raise ErrorFila("distancia_min_m negativa")
    norma = (fila.get("norma") or "").strip()
    if not norma:
        raise ErrorFila("norma vacía (nombre del PDF sin extensión)")

    return FilaRegla(
        linea=linea, provincia=provincia, jurisdiccion=jurisdiccion, tipo_zona=tipo_zona,
        tipo_aplicacion=tipo_aplicacion, bandas=_bandas(fila.get("banda_toxicologica")),
        distancia_min_m=distancia, permitido=_permitido(fila.get("permitido")),
        condiciones=_texto(fila.get("condiciones")), norma=norma,
        articulo=_texto(fila.get("articulo")), observaciones=_texto(fila.get("observaciones")),
    )


def leer_reglas_csv(ruta: Path) -> tuple[list[FilaRegla], list[str]]:
    """(filas válidas, errores "línea N: motivo"). Un encabezado incompleto se
    informa una sola vez y no se lee ninguna fila."""
    with ruta.open(encoding="utf-8", newline="") as f:
        lector = csv.DictReader(f)
        faltantes = [c for c in COLUMNAS if c not in (lector.fieldnames or [])]
        if faltantes:
            return [], [f"línea 1: faltan las columnas {', '.join(faltantes)}"]
        filas: list[FilaRegla] = []
        errores: list[str] = []
        for fila in lector:
            i = lector.line_num  # línea física: el lector se saltea las vacías
            if not any(isinstance(v, str) and v.strip() for v in fila.values()):
                continue  # línea en blanco
            try:
                filas.append(normalizar_fila(fila, i))
            except ErrorFila as e:
                errores.append(f"línea {i}: {e}")
    return filas, errores
