"""Carga el `reglas.csv` único de `data/insumos/` a `territorio.regla_distancia`
(y, donde una jurisdicción no tiene filas, lee las distancias del texto de sus
PDF, de forma determinista: ver `servicios/extraccion_reglas.py`). La normativa
nacional nunca se lee del PDF: está para consultas, no para el dictamen.

Resuelve la norma y el artículo citados contra lo que ya insertó
`loader_normativa.py` -- tiene que correr después de ese loader, no antes
(ver docs/contrato-insumos.md). Si una regla cita una norma o un artículo
que no está cargado, falla con un error explícito en vez de insertar una FK
inconsistente. Todo el archivo se valida antes de tocar la base.
"""

import argparse
import logging
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import psycopg

from fitosanitarios.config import get_settings
from fitosanitarios.insumos.estructura import carpeta_nacional, carpetas_provincia, localidades
from fitosanitarios.insumos.reglas_csv import FilaRegla, leer_reglas_csv
from fitosanitarios.servicios.extraccion_reglas import extraer_reglas_de_articulo

logger = logging.getLogger(__name__)


@dataclass
class _Alcance:
    """Una jurisdicción cargada: qué normas de la base son suyas."""

    clave: tuple[str, ...]  # como `FilaRegla.alcance`
    filtro_normas: str  # SQL sobre `territorio.norma n`
    params: tuple
    con_extraccion: bool  # sin filas en el CSV, leer las distancias del PDF


def _resolver_articulo(cur, fila: FilaRegla, norma_id: int) -> int | None:
    if not fila.articulo:
        return None
    cur.execute(
        "SELECT id FROM territorio.articulo WHERE norma_id = %s AND numero = %s",
        (norma_id, fila.articulo),
    )
    row = cur.fetchone()
    if row is None:
        raise ValueError(
            f"reglas.csv línea {fila.linea}: cita el artículo {fila.articulo} de {fila.norma}, "
            "que no se encontró chunkeado (¿el PDF usa un formato de encabezado no estándar?)"
        )
    return row[0]


def cargar_reglas_de_alcance(cur, alcance: _Alcance, filas: list[FilaRegla]) -> int:
    """Reemplaza las reglas del alcance por las del CSV."""
    cur.execute(
        "DELETE FROM territorio.regla_distancia WHERE norma_id IN "
        f"(SELECT n.id FROM territorio.norma n WHERE {alcance.filtro_normas})",
        alcance.params,
    )
    cur.execute(
        f"SELECT n.archivo, n.id FROM territorio.norma n WHERE {alcance.filtro_normas}",
        alcance.params,
    )
    norma_id_por_archivo = dict(cur.fetchall())
    for fila in filas:
        norma_id = norma_id_por_archivo.get(fila.norma)
        if norma_id is None:
            raise ValueError(
                f"reglas.csv línea {fila.linea}: la regla cita la norma '{fila.norma}', que no "
                f"está cargada para {'/'.join(alcance.clave)} (¿corriste loader_normativa.py "
                "antes?)"
            )
        articulo_id = _resolver_articulo(cur, fila, norma_id)
        cur.execute(
            """
            INSERT INTO territorio.regla_distancia
                (norma_id, articulo_id, tipo_zona, tipo_aplicacion, bandas,
                 distancia_min_m, permitido, condiciones, observaciones)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                norma_id, articulo_id, fila.tipo_zona, fila.tipo_aplicacion, fila.bandas,
                fila.distancia_min_m, fila.permitido, fila.condiciones, fila.observaciones,
            ),
        )
    return len(filas)


def _alcances_cargados(cur, data_dir: Path) -> list[_Alcance]:
    """Las jurisdicciones con carpeta en `data/insumos/` que ya están en la base."""
    alcances: list[_Alcance] = []
    for provincia in carpetas_provincia(data_dir):
        cur.execute("SELECT id FROM territorio.provincia WHERE nombre = %s", (provincia.name,))
        fila = cur.fetchone()
        if fila is None:
            logger.warning("%s sin provincia cargada, se omiten sus reglas", provincia.name)
        else:
            alcances.append(_Alcance(
                ("provincial", provincia.name),
                "n.ambito = 'provincial' AND n.provincia_id = %s", (fila[0],), True,
            ))
    for provincia, localidad in localidades(data_dir):
        cur.execute(
            "SELECT id FROM territorio.localidad WHERE jurisdiccion_id = %s", (localidad.name,)
        )
        fila = cur.fetchone()
        if fila is None:
            logger.warning("%s sin localidad cargada, se omiten sus reglas", localidad.name)
        else:
            alcances.append(_Alcance(
                ("municipal", provincia.name, localidad.name),
                "n.ambito = 'municipal' AND n.localidad_id = %s", (fila[0],), True,
            ))
    if carpeta_nacional(data_dir).exists():
        alcances.append(_Alcance(("nacional",), "n.ambito = 'nacional'", (), False))
    return alcances


def cargar_reglas(conn: psycopg.Connection, data_dir: Path) -> int:
    """`data_dir/reglas.csv` es la fuente preferida. Donde una jurisdicción no
    tiene filas, las distancias se leen del texto de sus PDF
    (`servicios/extraccion_reglas.py`), salvo las nacionales."""
    ruta_csv = data_dir / "reglas.csv"
    filas: list[FilaRegla] = []
    if ruta_csv.exists():
        filas, errores = leer_reglas_csv(ruta_csv)
        if errores:
            raise ValueError("reglas.csv con errores:\n" + "\n".join(errores))
    por_alcance: dict[tuple, list[FilaRegla]] = defaultdict(list)
    for fila in filas:
        por_alcance[fila.alcance].append(fila)

    total = 0
    with conn.cursor() as cur:
        alcances = _alcances_cargados(cur, data_dir)
        # Antes de tocar la base: una fila de una jurisdicción sin carpeta es un error del CSV.
        sin_carpeta = set(por_alcance) - {a.clave for a in alcances}
        if sin_carpeta:
            detalle = ", ".join("/".join(c) for c in sorted(sin_carpeta))
            raise ValueError(
                f"reglas.csv tiene filas de jurisdicciones sin carpeta cargada: {detalle}"
            )
        for alcance in alcances:
            del_csv = por_alcance.get(alcance.clave)
            if del_csv:
                total += cargar_reglas_de_alcance(cur, alcance, del_csv)
            elif alcance.con_extraccion:
                total += extraer_reglas_de_pdfs(cur, alcance.filtro_normas, alcance.params)
            else:
                cur.execute(
                    "DELETE FROM territorio.regla_distancia WHERE norma_id IN "
                    f"(SELECT n.id FROM territorio.norma n WHERE {alcance.filtro_normas})",
                    alcance.params,
                )
        conn.commit()
    return total


def extraer_reglas_de_pdfs(cur, filtro_normas: str, params: tuple) -> int:
    """Reemplaza las reglas del alcance (`filtro_normas`, sobre `territorio.norma n`)
    por las que se leen de sus artículos. Cada regla se guarda con
    `fuente='pdf_extraido'` y el artículo del que salió."""
    cur.execute(
        "DELETE FROM territorio.regla_distancia WHERE norma_id IN "
        f"(SELECT n.id FROM territorio.norma n WHERE {filtro_normas})",
        params,
    )
    cur.execute(
        "SELECT a.id, a.numero, a.texto, n.id, n.archivo FROM territorio.articulo a "
        f"JOIN territorio.norma n ON n.id = a.norma_id WHERE {filtro_normas} "
        "ORDER BY n.id, a.id",
        params,
    )
    articulos = cur.fetchall()
    total = 0
    for articulo_id, numero, texto, norma_id, archivo in articulos:
        for regla in extraer_reglas_de_articulo(archivo, numero, texto):
            cur.execute(
                """
                INSERT INTO territorio.regla_distancia
                    (norma_id, articulo_id, tipo_zona, tipo_aplicacion, bandas,
                     distancia_min_m, observaciones, fuente)
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'pdf_extraido')
                """,
                (
                    norma_id, articulo_id, regla.tipo_zona, regla.tipo_aplicacion,
                    regla.bandas, regla.distancia_min_m, None,
                ),
            )
            logger.info("%s art. %s: %s", archivo, numero, regla.oracion)
            total += 1
    logger.info("%d reglas leídas de %d artículos (%s)", total, len(articulos), params)
    return total


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--database-url", type=str, default=None)
    args = parser.parse_args()

    settings = get_settings()
    db_url = args.database_url or settings.database_url
    with psycopg.connect(db_url) as conn:
        total = cargar_reglas(conn, args.data)
    logger.info("Reglas cargadas: %d", total)


if __name__ == "__main__":
    main()
