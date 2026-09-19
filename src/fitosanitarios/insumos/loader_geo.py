"""Carga `localidad.geojson` a `territorio.localidad` y `territorio.zona_protegida`.

Sin PostGIS: las geometrías se guardan como GeoJSON en JSONB, más un bounding
box en columnas numéricas para prefiltrar (ver skill, "Base de datos" y
docs/modelo-datos.md). No valida el contrato -- eso ya lo hizo
`validador.py`; este loader asume que la carpeta pasó la validación (falla
si no, con un error de FK/constraint menos claro, por eso `--data` en el CLI
corre el validador primero).
"""

import argparse
import json
import logging
from pathlib import Path

import psycopg
from shapely.geometry import shape

from fitosanitarios.config import get_settings
from fitosanitarios.insumos.estructura import localidades
from fitosanitarios.insumos.validador import es_clave_de_localidad, validar_insumos

logger = logging.getLogger(__name__)


def _upsert_provincia(cur, nombre: str) -> int:
    cur.execute(
        """
        INSERT INTO territorio.provincia (nombre) VALUES (%s)
        ON CONFLICT (nombre) DO UPDATE SET nombre = EXCLUDED.nombre
        RETURNING id
        """,
        (nombre,),
    )
    return cur.fetchone()[0]


def cargar_localidad(cur, jurisdiccion_id: str, ruta_geojson: Path) -> int:
    with ruta_geojson.open(encoding="utf-8") as f:
        data = json.load(f)

    feature_limite = next(
        f for f in data["features"] if f["properties"].get("tipo") == "limite"
    )
    geom_limite = shape(feature_limite["geometry"])
    nombre = feature_limite["properties"]["nombre"]
    provincia_nombre = feature_limite["properties"]["provincia"]

    provincia_id = _upsert_provincia(cur, provincia_nombre)
    min_lon, min_lat, max_lon, max_lat = geom_limite.bounds

    cur.execute(
        """
        INSERT INTO territorio.localidad
            (jurisdiccion_id, nombre, provincia_id, limite,
             bbox_min_lon, bbox_min_lat, bbox_max_lon, bbox_max_lat)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (jurisdiccion_id) DO UPDATE SET
            nombre = EXCLUDED.nombre,
            provincia_id = EXCLUDED.provincia_id,
            limite = EXCLUDED.limite,
            bbox_min_lon = EXCLUDED.bbox_min_lon,
            bbox_min_lat = EXCLUDED.bbox_min_lat,
            bbox_max_lon = EXCLUDED.bbox_max_lon,
            bbox_max_lat = EXCLUDED.bbox_max_lat
        RETURNING id
        """,
        (
            jurisdiccion_id, nombre, provincia_id, json.dumps(feature_limite["geometry"]),
            min_lon, min_lat, max_lon, max_lat,
        ),
    )
    localidad_id = cur.fetchone()[0]

    # Reemplaza las zonas protegidas de esta localidad (idempotente: la carga
    # es la fuente de la verdad de los archivos, no un merge incremental).
    cur.execute("DELETE FROM territorio.zona_protegida WHERE localidad_id = %s", (localidad_id,))
    for feature in data["features"]:
        tipo = feature["properties"].get("tipo")
        if tipo == "limite":
            continue
        geom = shape(feature["geometry"])
        min_lon, min_lat, max_lon, max_lat = geom.bounds
        cur.execute(
            """
            INSERT INTO territorio.zona_protegida
                (localidad_id, tipo, nombre, geometria, propiedades,
                 bbox_min_lon, bbox_min_lat, bbox_max_lon, bbox_max_lat)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                localidad_id, tipo, feature["properties"].get("nombre", ""),
                json.dumps(feature["geometry"]), json.dumps(feature["properties"]),
                min_lon, min_lat, max_lon, max_lat,
            ),
        )

    return localidad_id


def cargar_localidades(conn: psycopg.Connection, data_dir: Path) -> dict[str, int]:
    resumen: dict[str, int] = {}
    with conn.cursor() as cur:
        for _provincia, carpeta in localidades(data_dir):
            geojson = carpeta / "localidad.geojson"
            if not geojson.exists():
                logger.warning("Carpeta %s sin localidad.geojson, se omite", carpeta)
                continue
            localidad_id = cargar_localidad(cur, carpeta.name, geojson)
            resumen[carpeta.name] = localidad_id
            logger.info("Localidad cargada: %s -> id %d", carpeta.name, localidad_id)
        conn.commit()
    return resumen


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, required=True, help="ruta a data/insumos")
    parser.add_argument("--database-url", type=str, default=None)
    parser.add_argument(
        "--forzar", action="store_true",
        help="cargar igual aunque el validador encuentre errores (no recomendado)",
    )
    args = parser.parse_args()

    resultados = validar_insumos(args.data)
    hay_errores = any(r.errores for k, r in resultados.items() if es_clave_de_localidad(k))
    if hay_errores and not args.forzar:
        for clave, resultado in resultados.items():
            for error in resultado.errores:
                logger.error("[%s] %s: %s", clave, error.codigo, error.mensaje)
        raise SystemExit("Hay errores de validación; corregí los insumos o corré con --forzar")

    settings = get_settings()
    db_url = args.database_url or settings.database_url
    with psycopg.connect(db_url) as conn:
        resumen = cargar_localidades(conn, args.data)
    logger.info("Carga terminada: %s", resumen)


if __name__ == "__main__":
    main()
