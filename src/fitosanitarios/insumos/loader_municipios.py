"""Carga el catálogo de municipios y comunas de una provincia
(`territorio.municipio`) desde un CSV `nombre,categoria`. Idempotente: borra
y reinserta los de esa provincia.

    uv run python -m fitosanitarios.insumos.loader_municipios \\
        --csv data/referencia/municipios-santa-fe.csv --provincia santa-fe
"""

import argparse
import csv
import logging
from pathlib import Path

import psycopg

from fitosanitarios.config import get_settings

logger = logging.getLogger(__name__)


def cargar_municipios(conn: psycopg.Connection, ruta_csv: Path, provincia: str) -> int:
    with ruta_csv.open(encoding="utf-8", newline="") as f:
        filas = [
            (provincia, r["nombre"].strip(), r["categoria"].strip()) for r in csv.DictReader(f)
        ]
    with conn.cursor() as cur:
        cur.execute("DELETE FROM territorio.municipio WHERE provincia = %s", (provincia,))
        cur.executemany(
            "INSERT INTO territorio.municipio (provincia, nombre, categoria) VALUES (%s, %s, %s)",
            filas,
        )
    conn.commit()
    return len(filas)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--provincia", type=str, required=True)
    parser.add_argument("--database-url", type=str, default=None)
    args = parser.parse_args()
    with psycopg.connect(args.database_url or get_settings().database_url) as conn:
        total = cargar_municipios(conn, args.csv, args.provincia)
    logger.info("Municipios y comunas cargados en %s: %d", args.provincia, total)


if __name__ == "__main__":
    main()
