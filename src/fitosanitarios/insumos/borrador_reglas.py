"""Borrador de filas para el `reglas.csv` de cada carpeta de `data/insumos/`,
armado con el extractor determinista de `servicios/extraccion_reglas.py`.

Es un punto de partida para que una persona lo revise, no una fuente de datos:
escribe en la carpeta `reglas.borrador.csv` (mismas columnas que `reglas.csv` más
`oracion`, la frase de la norma de la que salió cada fila; el loader ignora esa
columna) y `reglas.borrador-pendientes.txt` (las oraciones con distancia que el
extractor descartó y hay que decidir a mano). Nunca toca el `reglas.csv`: las
filas que sirvan se copian a mano y se recarga con `loader_reglas`. Si el
`reglas.csv` ya tiene filas de esa carpeta, imprime en qué difieren del borrador.

    uv run python -m fitosanitarios.insumos.borrador_reglas --data data/insumos
"""

import argparse
import csv
import logging
from dataclasses import dataclass
from pathlib import Path

from fitosanitarios.insumos.estructura import (
    alcance_de_carpeta,
    carpeta_nacional,
    carpetas_provincia,
    localidades,
)
from fitosanitarios.insumos.loader_normativa import chunkear_articulos, extraer_texto_o_ocr
from fitosanitarios.insumos.reglas_csv import COLUMNAS as COLUMNAS_REGLAS
from fitosanitarios.insumos.reglas_csv import FilaRegla, leer_reglas_csv
from fitosanitarios.servicios.extraccion_reglas import (
    extraer_reglas_de_articulo,
    oraciones_con_distancia_sin_extraer,
)

logger = logging.getLogger(__name__)

COLUMNAS = [*COLUMNAS_REGLAS, "oracion"]


@dataclass
class ResumenCarpeta:
    carpeta: Path
    filas: list[dict]
    pendientes: list[str]  # "norma art. N: oración"
    solo_en_borrador: list[dict]  # filas que el reglas.csv no tiene para esta carpeta
    solo_en_csv: list[dict]  # prohibiciones del reglas.csv que el extractor no toma
    tiene_csv: bool  # el reglas.csv tiene filas de esta carpeta
    sin_texto: list[str]  # PDFs sin capa de texto: hay que revisarlos a mano


def _numero(valor: float) -> str:
    return str(int(valor)) if float(valor).is_integer() else str(valor)


def filas_de_texto(norma: str, texto: str) -> tuple[list[dict], list[str]]:
    """(filas del borrador, pendientes) de un PDF ya convertido a texto. Sin
    `provincia` ni `jurisdiccion`: las completa `borrador_de_carpeta`."""
    filas: list[dict] = []
    pendientes: list[str] = []
    for numero, cuerpo in chunkear_articulos(texto):
        for r in extraer_reglas_de_articulo(norma, numero, cuerpo):
            filas.append({
                "tipo_zona": r.tipo_zona, "tipo_aplicacion": r.tipo_aplicacion,
                "banda_toxicologica": ";".join(r.bandas),
                "distancia_min_m": _numero(r.distancia_min_m), "permitido": "N",
                "condiciones": "", "norma": norma, "articulo": numero, "observaciones": "",
                "oracion": r.oracion,
            })
        pendientes.extend(
            f"{norma} art. {numero}: {o}" for o in oraciones_con_distancia_sin_extraer(cuerpo)
        )
    return filas, pendientes


def _clave(fila: dict) -> tuple:
    bandas = frozenset(b.strip().lower() for b in fila["banda_toxicologica"].split(";"))
    return (
        fila["tipo_zona"].strip().lower(), fila["tipo_aplicacion"].strip().lower(), bandas,
        float(fila["distancia_min_m"]), fila["norma"].strip(), str(fila["articulo"]).strip(),
    )


def _como_dict(fila: FilaRegla) -> dict:
    return {
        "provincia": fila.provincia or "", "jurisdiccion": fila.jurisdiccion,
        "tipo_zona": fila.tipo_zona, "tipo_aplicacion": fila.tipo_aplicacion,
        "banda_toxicologica": ";".join(fila.bandas),
        "distancia_min_m": _numero(fila.distancia_min_m),
        "permitido": "S" if fila.permitido else "N", "condiciones": fila.condiciones or "",
        "norma": fila.norma, "articulo": fila.articulo or "",
        "observaciones": fila.observaciones or "",
    }


def _provincia_y_jurisdiccion(alcance: tuple[str, ...]) -> tuple[str, str]:
    if alcance == ("nacional",):
        return "", "ARGENTINA"
    if alcance[0] == "provincial":
        return "", alcance[1]
    return alcance[1], alcance[2]


def borrador_de_carpeta(
    carpeta: Path, alcance: tuple[str, ...] | None = None, filas_csv: list[FilaRegla] = ()
) -> ResumenCarpeta | None:
    """`None` si la carpeta no tiene PDFs. `alcance` (`estructura.alcance_de_carpeta`)
    completa `provincia` y `jurisdiccion` de las filas; `filas_csv`: las filas del
    `reglas.csv` de esta carpeta, para compararlas con el borrador."""
    pdfs = sorted(carpeta.glob("*.pdf"))
    if not pdfs:
        return None
    filas: list[dict] = []
    pendientes: list[str] = []
    sin_texto: list[str] = []
    for pdf in pdfs:
        texto, requiere_revision = extraer_texto_o_ocr(pdf)
        if not texto or requiere_revision:
            sin_texto.append(pdf.name)
        f, p = filas_de_texto(pdf.stem, texto)
        filas.extend(f)
        pendientes.extend(p)

    if alcance is not None:
        provincia, jurisdiccion = _provincia_y_jurisdiccion(alcance)
        filas = [{"provincia": provincia, "jurisdiccion": jurisdiccion, **f} for f in filas]

    # El extractor solo lee prohibiciones: las condicionales (S) no se comparan.
    del_csv = [_como_dict(f) for f in filas_csv if not f.permitido]
    claves_csv = {_clave(f) for f in del_csv}
    claves_borrador = {_clave(f) for f in filas}
    solo_borrador = [f for f in filas if _clave(f) not in claves_csv] if filas_csv else []
    solo_csv = [f for f in del_csv if _clave(f) not in claves_borrador]
    return ResumenCarpeta(
        carpeta, filas, pendientes, solo_borrador, solo_csv, bool(filas_csv), sin_texto
    )


def escribir_borrador(resumen: ResumenCarpeta) -> None:
    ruta = resumen.carpeta / "reglas.borrador.csv"
    with ruta.open("w", encoding="utf-8", newline="") as f:
        escritor = csv.DictWriter(f, fieldnames=COLUMNAS, lineterminator="\n", restval="")
        escritor.writeheader()
        escritor.writerows(resumen.filas)
    ruta_pendientes = resumen.carpeta / "reglas.borrador-pendientes.txt"
    cabecera = (
        "Oraciones con una distancia que el extractor NO tomó como regla. Revisar cada una "
        "y, si corresponde, agregarla a reglas.csv a mano (excepciones como filas S, "
        "condiciones, rangos, clases sin traducción, tablas).\n\n"
    )
    ruta_pendientes.write_text(
        cabecera + "\n\n".join(resumen.pendientes) + ("\n" if resumen.pendientes else ""),
        encoding="utf-8",
    )


def carpetas_a_revisar(data_dir: Path) -> list[Path]:
    carpetas = [*carpetas_provincia(data_dir), *(loc for _, loc in localidades(data_dir))]
    nacional = carpeta_nacional(data_dir)
    if nacional.exists():
        carpetas.append(nacional)
    return carpetas


def _describir(fila: dict) -> str:
    return (
        f"{fila['tipo_zona']} · {fila['tipo_aplicacion']} · {fila['banda_toxicologica']} · "
        f"{fila['distancia_min_m']} m · {fila['norma']} art. {fila['articulo']}"
    )


def imprimir_resumen(resumen: ResumenCarpeta, data_dir: Path) -> None:
    print(f"\n{resumen.carpeta.relative_to(data_dir)}")
    print(f"  {len(resumen.filas)} reglas en el borrador, {len(resumen.pendientes)} pendientes")
    for pdf in resumen.sin_texto:
        print(f"  ! {pdf}: sin capa de texto, revisarlo a mano")
    if resumen.tiene_csv:
        print("  ya tiene filas en reglas.csv (comparación):")
        print(f"    el borrador tiene y el CSV no: {len(resumen.solo_en_borrador)}")
        for f in resumen.solo_en_borrador:
            print(f"      + {_describir(f)}")
        print(
            "    el CSV tiene (prohibiciones) y el extractor no toma: "
            f"{len(resumen.solo_en_csv)}"
        )
        for f in resumen.solo_en_csv:
            print(f"      - {_describir(f)}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, required=True)
    args = parser.parse_args()

    ruta_csv = args.data / "reglas.csv"
    filas_csv: list[FilaRegla] = []
    if ruta_csv.exists():
        filas_csv, errores = leer_reglas_csv(ruta_csv)
        for e in errores:
            print(f"reglas.csv {e}")
    for carpeta in carpetas_a_revisar(args.data):
        alcance = alcance_de_carpeta(args.data, carpeta)
        resumen = borrador_de_carpeta(
            carpeta, alcance, [f for f in filas_csv if f.alcance == alcance]
        )
        if resumen is None:
            continue
        escribir_borrador(resumen)
        imprimir_resumen(resumen, args.data)


if __name__ == "__main__":
    main()
