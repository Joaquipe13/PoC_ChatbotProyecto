"""Carga `localidad.geojson` a `territorio.localidad` y `territorio.zona_protegida`.

Sin PostGIS: las geometrías se guardan como GeoJSON en JSONB, más un bounding
box en columnas numéricas para prefiltrar (ver skill, "Base de datos" y
docs/modelo-datos.md). No valida el contrato -- eso ya lo hizo
`validador.py`; este loader asume que la carpeta pasó la validación (falla
si no, con un error de FK/constraint menos claro, por eso `--data` en el CLI
corre el validador primero).

**Localidades sin `localidad.geojson` (22/09/2026, ver DECISIONES.md,
"Localidades y normas sin fuente oficial: Sastre y San Jorge").** Es
opcional: una carpeta de localidad sin `localidad.geojson` igual se carga
en `territorio.localidad`, sin límite ni zonas protegidas (`limite` y el
bbox quedan `NULL`), solo para que le cuelguen normas y reglas de distancia
-- el dictamen ya no compara la ubicación del lote contra geometría
(Fase 12). El `nombre` sale de `territorio.municipio` si coincide con el
nombre de la carpeta; si no, del nombre de la carpeta capitalizado.
"""

import argparse
import json
import logging
import unicodedata
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


def _sin_tildes(texto: str) -> str:
    descompuesto = unicodedata.normalize("NFD", texto)
    return "".join(c for c in descompuesto if unicodedata.category(c) != "Mn").lower()


def _nombre_desde_municipios(cur, provincia_nombre: str, jurisdiccion_id: str) -> str | None:
    cur.execute(
        "SELECT nombre FROM territorio.municipio WHERE provincia = %s", (provincia_nombre,)
    )
    buscado = jurisdiccion_id.replace("-", " ")
    for (nombre,) in cur.fetchall():
        if _sin_tildes(nombre) == buscado:
            return nombre
    return None


def cargar_localidad_sin_geometria(cur, jurisdiccion_id: str, nombre: str, provincia_id: int) -> int:
    """Localidad sin `localidad.geojson` (22/09/2026, ver DECISIONES.md,
    "Localidades y normas sin fuente oficial"): sin límite ni zonas
    protegidas, solo sirve para que le cuelguen normas y reglas de distancia."""
    cur.execute(
        """
        INSERT INTO territorio.localidad
            (jurisdiccion_id, nombre, provincia_id, limite,
             bbox_min_lon, bbox_min_lat, bbox_max_lon, bbox_max_lat)
        VALUES (%s, %s, %s, NULL, NULL, NULL, NULL, NULL)
        ON CONFLICT (jurisdiccion_id) DO UPDATE SET
            nombre = EXCLUDED.nombre,
            provincia_id = EXCLUDED.provincia_id,
            limite = NULL,
            bbox_min_lon = NULL,
            bbox_min_lat = NULL,
            bbox_max_lon = NULL,
            bbox_max_lat = NULL
        RETURNING id
        """,
        (jurisdiccion_id, nombre, provincia_id),
    )
    localidad_id = cur.fetchone()[0]
    cur.execute("DELETE FROM territorio.zona_protegida WHERE localidad_id = %s", (localidad_id,))
    return localidad_id


def cargar_localidades(conn: psycopg.Connection, data_dir: Path) -> dict[str, int]:
    resumen: dict[str, int] = {}
    with conn.cursor() as cur:
        for provincia_dir, carpeta in localidades(data_dir):
            geojson = carpeta / "localidad.geojson"
            if geojson.exists():
                localidad_id = cargar_localidad(cur, carpeta.name, geojson)
            else:
                provincia_id = _upsert_provincia(cur, provincia_dir.name)
                nombre = (
                    _nombre_desde_municipios(cur, provincia_dir.name, carpeta.name)
                    or carpeta.name.replace("-", " ").title()
                )
                localidad_id = cargar_localidad_sin_geometria(
                    cur, carpeta.name, nombre, provincia_id
                )
                logger.warning(
                    "%s sin localidad.geojson: se carga sin límite ni zonas protegidas", carpeta
                )
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
