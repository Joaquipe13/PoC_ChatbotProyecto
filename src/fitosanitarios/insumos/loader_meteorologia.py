"""Carga lo que usa el pronóstico del tiempo al agendar (ver DECISIONES.md, "Pronóstico
del tiempo al agendar"), desde dos archivos opcionales de `data/insumos/`:

- `localidades.csv`: el centro (lat/lon) de cada localidad, para pedir el pronóstico.
  Columnas `provincia, jurisdiccion, centro_lat, centro_lon, fuente`.
- `reglas_viento.csv`: las normas que se refieren al viento, que se mencionan junto al
  pronóstico. Columnas `provincia, jurisdiccion, viento_max_kmh, norma, articulo,
  descripcion`; `provincia` vacía para una norma provincial (como en `reglas.csv`).

Tiene que correr después de `loader_geo.py` y `loader_normativa.py`: la localidad y la
norma citadas tienen que estar cargadas. Si no lo están, falla con un error explícito.
"""

import argparse
import csv
import logging
from pathlib import Path

import psycopg

from fitosanitarios.config import get_settings

logger = logging.getLogger(__name__)


def _filas(ruta: Path) -> list[dict]:
    if not ruta.exists():
        return []
    with ruta.open(encoding="utf-8", newline="") as archivo:
        return [
            {k: (v or "").strip() for k, v in fila.items()}
            for fila in csv.DictReader(archivo)
        ]


def cargar_centros(conn: psycopg.Connection, data_dir: Path) -> int:
    filas = _filas(data_dir / "localidades.csv")
    with conn.cursor() as cur:
        for linea, fila in enumerate(filas, start=2):
            cur.execute(
                "UPDATE territorio.localidad SET centro_lat = %s, centro_lon = %s "
                "WHERE jurisdiccion_id = %s",
                (float(fila["centro_lat"]), float(fila["centro_lon"]), fila["jurisdiccion"]),
            )
            if cur.rowcount == 0:
                raise ValueError(
                    f"localidades.csv línea {linea}: la localidad '{fila['jurisdiccion']}' "
                    "no está cargada (correr antes loader_geo)"
                )
    conn.commit()
    return len(filas)


def _norma_id(cur, fila: dict, linea: int) -> int:
    if fila["provincia"]:  # municipal: la norma de esa localidad
        cur.execute(
            "SELECT n.id FROM territorio.norma n "
            "JOIN territorio.localidad l ON l.id = n.localidad_id "
            "WHERE n.archivo = %s AND l.jurisdiccion_id = %s",
            (fila["norma"], fila["jurisdiccion"]),
        )
    else:  # provincial
        cur.execute(
            "SELECT n.id FROM territorio.norma n "
            "JOIN territorio.provincia p ON p.id = n.provincia_id "
            "WHERE n.archivo = %s AND n.ambito = 'provincial' AND p.nombre = %s",
            (fila["norma"], fila["jurisdiccion"]),
        )
    encontrada = cur.fetchone()
    if encontrada is None:
        raise ValueError(
            f"reglas_viento.csv línea {linea}: la norma '{fila['norma']}' de "
            f"'{fila['jurisdiccion']}' no está cargada (correr antes loader_normativa)"
        )
    return encontrada[0]


def _articulo_id(cur, norma_id: int, fila: dict, linea: int) -> int | None:
    if not fila["articulo"]:
        return None
    cur.execute(
        "SELECT id FROM territorio.articulo WHERE norma_id = %s AND numero = %s",
        (norma_id, fila["articulo"]),
    )
    encontrado = cur.fetchone()
    if encontrado is None:
        raise ValueError(
            f"reglas_viento.csv línea {linea}: no se encontró el artículo "
            f"{fila['articulo']} de {fila['norma']}"
        )
    return encontrado[0]


def cargar_reglas_viento(conn: psycopg.Connection, data_dir: Path) -> int:
    """Reemplaza todas las reglas de viento por las del archivo."""
    filas = _filas(data_dir / "reglas_viento.csv")
    with conn.cursor() as cur:
        a_insertar = []
        for linea, fila in enumerate(filas, start=2):
            norma_id = _norma_id(cur, fila, linea)
            a_insertar.append((
                norma_id, _articulo_id(cur, norma_id, fila, linea),
                float(fila["viento_max_kmh"]), fila["descripcion"],
            ))
        cur.execute("DELETE FROM territorio.regla_viento")
        cur.executemany(
            "INSERT INTO territorio.regla_viento "
            "(norma_id, articulo_id, viento_max_kmh, descripcion) VALUES (%s, %s, %s, %s)",
            a_insertar,
        )
    conn.commit()
    return len(filas)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, required=True, help="ruta a data/insumos")
    parser.add_argument("--database-url", type=str, default=None)
    args = parser.parse_args()
    with psycopg.connect(args.database_url or get_settings().database_url) as conn:
        centros = cargar_centros(conn, args.data)
        reglas = cargar_reglas_viento(conn, args.data)
    logger.info("Centros de localidad: %d; reglas de viento: %d", centros, reglas)


if __name__ == "__main__":
    main()
