"""Calcula (o recalcula) el embedding de cada fila de `catalogo.vehiculo`.

La tabla se siembra directamente en `001_catalogo.sql` (categorías genéricas
+ los 2 aviones de ejemplo con matrícula), pero el embedding no se puede
calcular en SQL plano -- este script lo hace con el mismo modelo que usa el
resto del proyecto (ver DECISIONES.md, "RAG de equipos").

Texto embebido por fila: nombre + sinónimos + modelo/motor de
`caracteristicas` si están presentes -- mismo criterio que
`catalogo.producto` (marca + principio activo), pensado para que una
descripción libre como "la avioneta grande" o "la dromader" tenga con qué
matchear semánticamente, no solo por sinónimo exacto.

Uso: uv run python scripts/cargar_vehiculos.py
"""

import logging

import psycopg
from sentence_transformers import SentenceTransformer

from fitosanitarios.config import get_settings
from fitosanitarios.datos.vectores import vector_literal

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _texto_para_embedding(nombre: str, sinonimos: list[str], caracteristicas: dict) -> str:
    partes = [nombre, *sinonimos]
    for clave in ("modelo", "motor"):
        if caracteristicas.get(clave):
            partes.append(str(caracteristicas[clave]))
    return ". ".join(partes)


def cargar_embeddings_vehiculo(conn: psycopg.Connection, modelo_embeddings) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT id, nombre, sinonimos, caracteristicas FROM catalogo.vehiculo")
        filas = cur.fetchall()

        n = 0
        for vehiculo_id, nombre, sinonimos, caracteristicas in filas:
            texto = _texto_para_embedding(nombre, sinonimos, caracteristicas)
            embedding = modelo_embeddings.encode(texto).tolist()
            cur.execute(
                "UPDATE catalogo.vehiculo SET embedding = %s::vector WHERE id = %s",
                (vector_literal(embedding), vehiculo_id),
            )
            n += 1
        conn.commit()
    return n


def main() -> None:
    settings = get_settings()
    modelo = SentenceTransformer(settings.embeddings_model)
    with psycopg.connect(settings.database_url) as conn:
        n = cargar_embeddings_vehiculo(conn, modelo)
    logger.info("Embeddings calculados para %d vehículos", n)


if __name__ == "__main__":
    main()
