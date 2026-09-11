"""Carga `reglas.csv` a `territorio.regla_distancia`.

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
    total = 0
    with conn.cursor() as cur:
        total += _cargar_reglas_localidades(cur, data_dir / "localidades")
        total += _cargar_reglas_ambito_general(cur, data_dir / "normativa-general")
        conn.commit()
    return total


def _cargar_reglas_localidades(cur, localidades_dir: Path) -> int:
    if not localidades_dir.exists():
        return 0
    total = 0
    for carpeta in sorted(localidades_dir.iterdir()):
        reglas_csv = carpeta / "reglas.csv"
        if not carpeta.is_dir() or not reglas_csv.exists():
            continue
        cur.execute(
            "SELECT id FROM territorio.localidad WHERE jurisdiccion_id = %s", (carpeta.name,)
        )
        row = cur.fetchone()
        if row is None:
            logger.warning("%s sin localidad cargada, se omiten sus reglas", carpeta.name)
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


def _cargar_reglas_ambito_general(cur, normativa_general_dir: Path) -> int:
    total = 0

    provincial_dir = normativa_general_dir / "provincial"
    if provincial_dir.exists():
        for carpeta in sorted(provincial_dir.iterdir()):
            reglas_csv = carpeta / "reglas.csv"
            if not carpeta.is_dir() or not reglas_csv.exists():
                continue
            cur.execute("SELECT id FROM territorio.provincia WHERE nombre = %s", (carpeta.name,))
            prov_row = cur.fetchone()
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

    nacional_dir = normativa_general_dir / "nacional"
    reglas_csv = nacional_dir / "reglas.csv"
    if nacional_dir.exists() and reglas_csv.exists():
        cur.execute(
            """
            DELETE FROM territorio.regla_distancia
            WHERE norma_id IN (SELECT id FROM territorio.norma WHERE ambito = 'nacional')
            """
        )
        mapa = _normas_de_carpeta(cur, {p.stem for p in nacional_dir.glob("*.pdf")})
        total += cargar_reglas_de_csv(cur, reglas_csv, mapa)

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
