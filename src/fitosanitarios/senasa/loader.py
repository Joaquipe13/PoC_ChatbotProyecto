"""Carga el snapshot de SENASA (JSON Lines versionado) al schema `catalogo`.

No consulta la red: opera sobre el snapshot local (ver skill, "SENASA
(vademécum)": "el sistema nunca consulta SENASA en vivo"). El snapshot es un
`.jsonl` -- no `.parquet` como sugería el ejemplo original del plan -- porque
la estructura por producto es profundamente anidada y de longitud variable
(N principios activos, N usos registrados, N documentos); aplanarla a un
esquema columnar habría requerido una normalización previa que el propio
snapshot ya hace de forma más simple como texto línea a línea. Decisión
documentada en DECISIONES.md.

Uso:
    uv run python -m fitosanitarios.senasa.loader --snapshot data/senasa/snapshot/productos.jsonl
"""

import argparse
import json
import logging
from pathlib import Path

import psycopg

from fitosanitarios.config import get_settings
from fitosanitarios.senasa.cliente import DetalleProducto, ProductoListado
from fitosanitarios.senasa.crawler import leer_detalle_jsonl, leer_listado_jsonl
from fitosanitarios.senasa.normalizador import limpiar_html, normalizar_banda, normalizar_nombre
from fitosanitarios.senasa.parser_dosis import parsear_dosis

logger = logging.getLogger(__name__)

ProductoConDetalle = tuple[ProductoListado, DetalleProducto | None]


def construir_snapshot(ruta_listado: Path, ruta_detalle: Path, ruta_snapshot: Path) -> int:
    """Une listado + detalle por id en un único JSONL versionado (una línea
    por producto: {"listado": {...}, "detalle": {...} | null}). Es el "dump"
    de la sección 5 del plan; se versiona por nombre de archivo/fecha, no
    dentro del propio archivo."""
    listado = leer_listado_jsonl(ruta_listado)
    detalles_por_id: dict[int, DetalleProducto] = {}
    if ruta_detalle.exists():
        detalles_por_id = {d.id: d for d in leer_detalle_jsonl(ruta_detalle)}

    ruta_snapshot.parent.mkdir(parents=True, exist_ok=True)
    with ruta_snapshot.open("w", encoding="utf-8") as f:
        for item in listado:
            detalle = detalles_por_id.get(item.id)
            linea = {
                "listado": item.model_dump(by_alias=True),
                "detalle": detalle.model_dump(by_alias=True) if detalle else None,
            }
            f.write(json.dumps(linea, ensure_ascii=False) + "\n")
    return len(listado)


def leer_snapshot(ruta_snapshot: Path) -> list[ProductoConDetalle]:
    resultado: list[ProductoConDetalle] = []
    with ruta_snapshot.open(encoding="utf-8") as f:
        for linea in f:
            if not linea.strip():
                continue
            data = json.loads(linea)
            item = ProductoListado.model_validate(data["listado"])
            detalle = DetalleProducto.model_validate(data["detalle"]) if data["detalle"] else None
            resultado.append((item, detalle))
    return resultado


def _vector_literal(embedding: list[float]) -> str:
    return "[" + ",".join(repr(float(x)) for x in embedding) + "]"


def cargar_catalogo(
    conn: psycopg.Connection,
    productos: list[ProductoConDetalle],
    modelo_embeddings,  # sentence_transformers.SentenceTransformer; sin import duro acá
) -> dict[str, int]:
    """Puebla `catalogo.*` a partir del snapshot ya parseado. Idempotente vía
    `ON CONFLICT` sobre las claves únicas de cada tabla (ver migraciones)."""
    resumen = {
        "firmas": 0, "productos": 0, "principios_activos": 0,
        "cultivos": 0, "adversidades": 0, "usos_registrados": 0,
    }
    cache_firma: dict[str, int] = {}
    cache_principio: dict[str, int] = {}
    cache_cultivo: dict[str, int] = {}
    cache_adversidad: dict[str, int] = {}

    with conn.cursor() as cur:
        for item, detalle in productos:
            firma_id = _upsert_firma(cur, item.nombre_firma, cache_firma, resumen)
            producto_id = _upsert_producto(cur, item, detalle, firma_id, modelo_embeddings, resumen)
            if detalle is None:
                continue
            _cargar_principios_activos(
                cur, detalle, producto_id, modelo_embeddings, cache_principio, resumen
            )
            _cargar_usos_registrados(
                cur, detalle, producto_id, modelo_embeddings,
                cache_cultivo, cache_adversidad, resumen,
            )
        conn.commit()
    return resumen


def _upsert_firma(cur, nombre_firma_crudo: str, cache: dict[str, int], resumen: dict) -> int:
    nombre = normalizar_nombre(nombre_firma_crudo) or "Sin dato"
    if nombre in cache:
        return cache[nombre]
    cur.execute(
        """
        INSERT INTO catalogo.firma (nombre, datos) VALUES (%s, '{}'::jsonb)
        ON CONFLICT (nombre) DO UPDATE SET nombre = EXCLUDED.nombre
        RETURNING id
        """,
        (nombre,),
    )
    firma_id = cur.fetchone()[0]
    cache[nombre] = firma_id
    resumen["firmas"] += 1
    return firma_id


def _upsert_producto(cur, item: ProductoListado, detalle: DetalleProducto | None,
                      firma_id: int, modelo_embeddings, resumen: dict) -> int:
    marca = normalizar_nombre(item.marca)
    sustancias_limpias = limpiar_html(item.sustancias_activas)
    texto_embedding = f"{marca} {sustancias_limpias}".strip() or marca or item.numero_inscripcion
    embedding = _vector_literal(modelo_embeddings.encode(texto_embedding).tolist())

    banda = None
    estado_producto = None
    toxicidad: dict = {}
    crudo_api: dict = {}
    if detalle is not None:
        clase_tox = detalle.clase_toxicologica.clase_tox if detalle.clase_toxicologica else None
        banda = normalizar_banda(clase_tox)
        estado_producto = (
            detalle.estado_producto.descripcion if detalle.estado_producto else None
        )
        toxicidad = {
            "abejas": detalle.toxicidad_abejas.clase_tox if detalle.toxicidad_abejas else None,
            "peces": detalle.toxicidad_peces.clase_tox if detalle.toxicidad_peces else None,
            "aves": detalle.toxicidad_aves.clase_tox if detalle.toxicidad_aves else None,
        }
        # productoDocumentos.contenido (PDFs en base64) nunca va a JSONB (ver skill).
        crudo_api = detalle.model_dump(mode="json", exclude={"producto_documentos"})

    cur.execute(
        """
        INSERT INTO catalogo.producto
            (firma_id, numero_inscripcion, marca, clase_toxicologica,
             banda_toxicologica, estado_producto, toxicidad, crudo_api, embedding)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::vector)
        ON CONFLICT (numero_inscripcion) DO UPDATE SET
            marca = EXCLUDED.marca,
            clase_toxicologica = EXCLUDED.clase_toxicologica,
            banda_toxicologica = EXCLUDED.banda_toxicologica,
            estado_producto = EXCLUDED.estado_producto,
            toxicidad = EXCLUDED.toxicidad,
            crudo_api = EXCLUDED.crudo_api,
            embedding = EXCLUDED.embedding
        RETURNING id
        """,
        (
            firma_id, item.numero_inscripcion, marca, item.clase_toxicologica,
            banda, estado_producto, json.dumps(toxicidad), json.dumps(crudo_api), embedding,
        ),
    )
    resumen["productos"] += 1
    return cur.fetchone()[0]


def _cargar_principios_activos(cur, detalle: DetalleProducto, producto_id: int,
                                modelo_embeddings, cache: dict[str, int], resumen: dict) -> None:
    for pa in detalle.principios_activos:
        nombre = normalizar_nombre(pa.nomenclador.descripcion)
        if not nombre:
            continue
        principio_id = cache.get(nombre)
        if principio_id is None:
            embedding = _vector_literal(modelo_embeddings.encode(nombre).tolist())
            cur.execute(
                """
                INSERT INTO catalogo.principio_activo (nombre, embedding)
                VALUES (%s, %s::vector)
                ON CONFLICT (nombre) DO UPDATE SET nombre = EXCLUDED.nombre
                RETURNING id
                """,
                (nombre, embedding),
            )
            principio_id = cur.fetchone()[0]
            cache[nombre] = principio_id
            resumen["principios_activos"] += 1
        cur.execute(
            """
            INSERT INTO catalogo.producto_principio_activo
                (producto_id, principio_activo_id, concentracion, unidad)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (producto_id, principio_activo_id) DO UPDATE SET
                concentracion = EXCLUDED.concentracion, unidad = EXCLUDED.unidad
            """,
            (producto_id, principio_id, pa.concentracion,
             pa.unidad_medida.sigla if pa.unidad_medida else None),
        )


def _cargar_usos_registrados(cur, detalle: DetalleProducto, producto_id: int, modelo_embeddings,
                              cache_cultivo: dict[str, int], cache_adversidad: dict[str, int],
                              resumen: dict) -> None:
    for aplicacion in detalle.aplicaciones_por_producto:
        if not aplicacion.cultivo:
            continue
        nombre_cultivo = normalizar_nombre(aplicacion.cultivo.nombre_comun)
        cultivo_id = cache_cultivo.get(nombre_cultivo)
        if cultivo_id is None:
            embedding = _vector_literal(modelo_embeddings.encode(nombre_cultivo).tolist())
            cur.execute(
                """
                INSERT INTO catalogo.cultivo (nombre, embedding) VALUES (%s, %s::vector)
                ON CONFLICT (nombre) DO UPDATE SET nombre = EXCLUDED.nombre
                RETURNING id
                """,
                (nombre_cultivo, embedding),
            )
            cultivo_id = cur.fetchone()[0]
            cache_cultivo[nombre_cultivo] = cultivo_id
            resumen["cultivos"] += 1

        adversidad_id = None
        if aplicacion.adversidad:
            nombre_adv = normalizar_nombre(aplicacion.adversidad.nombre_comun)
            adversidad_id = cache_adversidad.get(nombre_adv)
            if adversidad_id is None:
                texto_adv = f"{nombre_adv} {aplicacion.adversidad.nombre_cientifico or ''}".strip()
                embedding = _vector_literal(modelo_embeddings.encode(texto_adv).tolist())
                cur.execute(
                    """
                    INSERT INTO catalogo.adversidad (nombre_comun, nombre_cientifico, embedding)
                    VALUES (%s, %s, %s::vector)
                    ON CONFLICT (nombre_comun) DO UPDATE SET nombre_comun = EXCLUDED.nombre_comun
                    RETURNING id
                    """,
                    (nombre_adv, aplicacion.adversidad.nombre_cientifico, embedding),
                )
                adversidad_id = cur.fetchone()[0]
                cache_adversidad[nombre_adv] = adversidad_id
                resumen["adversidades"] += 1

        dosis_parseada = parsear_dosis(aplicacion.dosis)
        condiciones = {
            "momento": aplicacion.momento_aplicacion,
            "volumen_por_aplicacion": aplicacion.volumen_por_aplicacion,
            "periodo_carencia": aplicacion.periodo_carencia,
        }
        cur.execute(
            """
            INSERT INTO catalogo.uso_registrado
                (producto_id, cultivo_id, adversidad_id, fuente, confianza, dosis, condiciones)
            VALUES (%s, %s, %s, 'senasa_estructurado', 1.0, %s, %s)
            """,
            (
                producto_id, cultivo_id, adversidad_id,
                json.dumps(dosis_parseada.model_dump()), json.dumps(condiciones),
            ),
        )
        resumen["usos_registrados"] += 1


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--database-url", type=str, default=None)
    args = parser.parse_args()

    from sentence_transformers import SentenceTransformer

    settings = get_settings()
    db_url = args.database_url or settings.database_url

    productos = leer_snapshot(args.snapshot)
    logger.info("Snapshot leído: %d productos (%s)", len(productos), args.snapshot)

    modelo = SentenceTransformer(settings.embeddings_model)

    with psycopg.connect(db_url) as conn:
        resumen = cargar_catalogo(conn, productos, modelo)
    logger.info("Carga terminada: %s", resumen)


if __name__ == "__main__":
    main()
