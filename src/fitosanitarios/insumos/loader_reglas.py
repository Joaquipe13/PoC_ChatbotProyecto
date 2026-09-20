"""Carga `reglas.csv` a `territorio.regla_distancia` (y, donde una carpeta no
trae `reglas.csv`, lee las distancias del texto de sus PDF, de forma
determinista: ver `servicios/extraccion_reglas.py`).

Resuelve la norma y el artículo citados contra lo que ya insertó
`loader_normativa.py` -- tiene que correr después de ese loader, no antes
(ver docs/contrato-insumos.md). Si una regla cita una norma o un artículo
que no está cargado, falla con un error explícito en vez de insertar una FK
inconsistente.
"""

import argparse
import csv
import logging
from pathlib import Path

import psycopg

from fitosanitarios.config import get_settings
from fitosanitarios.insumos.estructura import carpeta_nacional, carpetas_provincia, localidades
from fitosanitarios.servicios.extraccion_reglas import extraer_reglas_de_articulo

logger = logging.getLogger(__name__)


def _parsear_bandas(campo: str) -> list[str]:
    campo = campo.strip()
    if campo.lower() == "todas":
        return ["todas"]
    return [b.strip() for b in campo.split(";") if b.strip()]


def _normas_de_carpeta(cur, archivos: set[str]) -> dict[str, int]:
    if not archivos:
        return {}
    cur.execute(
        "SELECT archivo, id FROM territorio.norma WHERE archivo = ANY(%s)", (list(archivos),)
    )
    return dict(cur.fetchall())


def cargar_reglas_de_csv(cur, ruta_csv: Path, norma_id_por_archivo: dict[str, int]) -> int:
    n = 0
    with ruta_csv.open(encoding="utf-8") as f:
        lector = csv.DictReader(f)
        for fila in lector:
            archivo_norma = fila["norma"].strip()
            norma_id = norma_id_por_archivo.get(archivo_norma)
            if norma_id is None:
                raise ValueError(
                    f"{ruta_csv}: la regla cita la norma '{archivo_norma}', que no está "
                    "cargada (¿corriste loader_normativa.py antes?)"
                )
            articulo_id = _resolver_articulo(cur, ruta_csv, norma_id, archivo_norma, fila)

            cur.execute(
                """
                INSERT INTO territorio.regla_distancia
                    (norma_id, articulo_id, tipo_zona, tipo_aplicacion, bandas,
                     distancia_min_m, observaciones)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    norma_id, articulo_id, fila["tipo_zona"].strip(),
                    fila["tipo_aplicacion"].strip(), _parsear_bandas(fila["bandas"]),
                    float(fila["distancia_min_m"]),
                    (fila.get("observaciones") or "").strip() or None,
                ),
            )
            n += 1
    return n


def _resolver_articulo(
    cur, ruta_csv: Path, norma_id: int, archivo_norma: str, fila: dict
) -> int | None:
    articulo_num = (fila.get("articulo") or "").strip()
    if not articulo_num:
        return None
    cur.execute(
        "SELECT id FROM territorio.articulo WHERE norma_id = %s AND numero = %s",
        (norma_id, articulo_num),
    )
    row = cur.fetchone()
    if row is None:
        raise ValueError(
            f"{ruta_csv}: cita el artículo {articulo_num} de {archivo_norma}, "
            "que no se encontró chunkeado (¿el PDF usa un formato de encabezado no estándar?)"
        )
    return row[0]


def cargar_reglas(conn: psycopg.Connection, data_dir: Path) -> int:
    """`reglas.csv` es la fuente preferida. Donde una carpeta no lo trae, las
    distancias se leen del texto de sus PDF (`servicios/extraccion_reglas.py`)."""
    total = 0
    with conn.cursor() as cur:
        total += _cargar_reglas_localidades(cur, data_dir)
        total += _cargar_reglas_provinciales(cur, data_dir)
        total += _cargar_reglas_nacionales(cur, data_dir)
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


def _cargar_reglas_localidades(cur, data_dir: Path) -> int:
    total = 0
    for _provincia, carpeta in localidades(data_dir):
        reglas_csv = carpeta / "reglas.csv"
        cur.execute(
            "SELECT id FROM territorio.localidad WHERE jurisdiccion_id = %s", (carpeta.name,)
        )
        row = cur.fetchone()
        if row is None:
            logger.warning("%s sin localidad cargada, se omiten sus reglas", carpeta.name)
            continue
        if not reglas_csv.exists():
            total += extraer_reglas_de_pdfs(
                cur, "n.ambito = 'municipal' AND n.localidad_id = %s", (row[0],)
            )
            continue
        cur.execute(
            """
            DELETE FROM territorio.regla_distancia
            WHERE norma_id IN (SELECT id FROM territorio.norma WHERE localidad_id = %s)
            """,
            (row[0],),
        )
        mapa = _normas_de_carpeta(cur, {p.stem for p in carpeta.glob("*.pdf")})
        total += cargar_reglas_de_csv(cur, reglas_csv, mapa)
    return total


def _cargar_reglas_provinciales(cur, data_dir: Path) -> int:
    """`reglas.csv` y PDFs directamente en la carpeta de cada provincia."""
    total = 0
    for carpeta in carpetas_provincia(data_dir):
        reglas_csv = carpeta / "reglas.csv"
        cur.execute("SELECT id FROM territorio.provincia WHERE nombre = %s", (carpeta.name,))
        prov_row = cur.fetchone()
        if not reglas_csv.exists():
            if prov_row:
                total += extraer_reglas_de_pdfs(
                    cur, "n.ambito = 'provincial' AND n.provincia_id = %s", (prov_row[0],)
                )
            continue
        if prov_row:
            cur.execute(
                """
                DELETE FROM territorio.regla_distancia
                WHERE norma_id IN (
                    SELECT id FROM territorio.norma
                    WHERE ambito = 'provincial' AND provincia_id = %s
                )
                """,
                (prov_row[0],),
            )
        mapa = _normas_de_carpeta(cur, {p.stem for p in carpeta.glob("*.pdf")})
        total += cargar_reglas_de_csv(cur, reglas_csv, mapa)
    return total


def _cargar_reglas_nacionales(cur, data_dir: Path) -> int:
    nacional_dir = carpeta_nacional(data_dir)
    if not nacional_dir.exists():
        return 0
    reglas_csv = nacional_dir / "reglas.csv"
    if not reglas_csv.exists():
        return extraer_reglas_de_pdfs(cur, "n.ambito = 'nacional'", ())
    cur.execute(
        """
        DELETE FROM territorio.regla_distancia
        WHERE norma_id IN (SELECT id FROM territorio.norma WHERE ambito = 'nacional')
        """
    )
    mapa = _normas_de_carpeta(cur, {p.stem for p in nacional_dir.glob("*.pdf")})
    return cargar_reglas_de_csv(cur, reglas_csv, mapa)


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
