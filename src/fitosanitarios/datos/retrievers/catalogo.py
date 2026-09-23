"""Retrievers SQL sobre el schema `catalogo` (ver docs/modelo-datos.md).

SQL parametrizado con joins + `pg_trgm` + `pgvector`; el LLM nunca escribe
SQL, solo elige la tool y sus parámetros (ver skill, "Base de datos").
"""

from dataclasses import dataclass, field

import psycopg

from fitosanitarios.datos.vectores import vector_literal as _vector_literal


@dataclass
class CandidatoProducto:
    id: int
    numero_inscripcion: str
    marca: str
    banda_toxicologica: str | None
    estado_producto: str | None
    score: float
    principios_activos: list[dict] = field(default_factory=list)
    usos_registrados: list[dict] = field(default_factory=list)


def buscar_productos_por_nombre(
    conn: psycopg.Connection,
    nombre_declarado: str,
    modelo_embeddings,
    top_k: int = 5,
    umbral_score: float = 0.3,
) -> list[CandidatoProducto]:
    """Candidatos por trigram + embedding de marca (ver skill, "Matching de
    productos"). `umbral_score` filtra candidatos débiles antes de rankear."""
    embedding = _vector_literal(modelo_embeddings.encode(nombre_declarado).tolist())
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                p.id, p.numero_inscripcion, p.marca, p.banda_toxicologica, p.estado_producto,
                (0.5 * similarity(p.marca, %(nombre)s)
                 + 0.5 * (1 - (p.embedding <=> %(emb)s::vector))) AS score,
                COALESCE(jsonb_agg(DISTINCT jsonb_build_object(
                    'principio_activo', pa.nombre,
                    'concentracion', ppa.concentracion,
                    'unidad', ppa.unidad
                )) FILTER (WHERE pa.id IS NOT NULL), '[]'::jsonb) AS principios_activos,
                COALESCE(jsonb_agg(DISTINCT jsonb_build_object(
                    'cultivo', c.nombre,
                    'adversidad', a.nombre_comun,
                    'dosis', ur.dosis,
                    'fuente', ur.fuente
                )) FILTER (WHERE ur.id IS NOT NULL), '[]'::jsonb) AS usos_registrados
            FROM catalogo.producto p
            LEFT JOIN catalogo.producto_principio_activo ppa ON ppa.producto_id = p.id
            LEFT JOIN catalogo.principio_activo pa ON pa.id = ppa.principio_activo_id
            LEFT JOIN catalogo.uso_registrado ur ON ur.producto_id = p.id
            LEFT JOIN catalogo.cultivo c ON c.id = ur.cultivo_id
            LEFT JOIN catalogo.adversidad a ON a.id = ur.adversidad_id
            WHERE p.marca %% %(nombre)s
               OR (1 - (p.embedding <=> %(emb)s::vector)) > %(umbral)s
            GROUP BY p.id
            HAVING (0.5 * similarity(p.marca, %(nombre)s)
                    + 0.5 * (1 - (p.embedding <=> %(emb)s::vector))) > %(umbral)s
            ORDER BY score DESC
            LIMIT %(top_k)s
            """,
            {
                "nombre": nombre_declarado, "emb": embedding,
                "umbral": umbral_score, "top_k": top_k,
            },
        )
        columnas = [d.name for d in cur.description]
        filas = cur.fetchall()

    return [
        CandidatoProducto(**dict(zip(columnas, fila, strict=True)))
        for fila in filas
    ]


def listar_productos_por_filtro(
    conn: psycopg.Connection,
    cultivo_id: int | None = None,
    adversidad_id: int | None = None,
    principio_activo_id: int | None = None,
    bandas_permitidas: list[str] | None = None,
    limite: int = 20,
    offset: int = 0,
) -> list[dict]:
    """Retriever de `consultar_productos`: al menos uno de
    cultivo_id/adversidad_id/principio_activo_id resuelto por embedding
    contra `catalogo.cultivo`/`adversidad`/`principio_activo` antes de
    llamar acá (ver skill, tool `consultar_productos`)."""
    if cultivo_id is None and adversidad_id is None and principio_activo_id is None:
        raise ValueError("listar_productos_por_filtro requiere al menos un filtro")

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT
                p.id, p.numero_inscripcion, p.marca, p.banda_toxicologica,
                ur.dosis, c.nombre AS cultivo, a.nombre_comun AS adversidad
            FROM catalogo.uso_registrado ur
            JOIN catalogo.producto p ON p.id = ur.producto_id
            JOIN catalogo.cultivo c ON c.id = ur.cultivo_id
            LEFT JOIN catalogo.adversidad a ON a.id = ur.adversidad_id
            LEFT JOIN catalogo.producto_principio_activo ppa ON ppa.producto_id = p.id
            LEFT JOIN catalogo.principio_activo pa ON pa.id = ppa.principio_activo_id
            WHERE (%(cultivo_id)s::bigint IS NULL OR c.id = %(cultivo_id)s)
              AND (%(adversidad_id)s::bigint IS NULL OR a.id = %(adversidad_id)s)
              AND (%(principio_id)s::bigint IS NULL OR pa.id = %(principio_id)s)
              AND (%(bandas)s::text[] IS NULL OR p.banda_toxicologica = ANY(%(bandas)s))
            ORDER BY p.marca
            LIMIT %(limite)s OFFSET %(offset)s
            """,
            {
                "cultivo_id": cultivo_id, "adversidad_id": adversidad_id,
                "principio_id": principio_activo_id, "bandas": bandas_permitidas,
                "limite": limite, "offset": offset,
            },
        )
        columnas = [d.name for d in cur.description]
        return [dict(zip(columnas, fila, strict=True)) for fila in cur.fetchall()]


def resolver_entidad_por_nombre(
    conn: psycopg.Connection,
    tabla: str,
    columna_nombre: str,
    nombre: str,
    modelo_embeddings,
    umbral_score: float = 0.4,
) -> int | None:
    """Resuelve un nombre libre (cultivo, adversidad, principio activo) al id
    de la fila más parecida en `catalogo.<tabla>`, combinando trigram +
    embedding. `tabla`/`columna_nombre` sin interpolar valores del usuario
    (son nombres de columna fijos por el código que llama, no user input)."""
    embedding = _vector_literal(modelo_embeddings.encode(nombre).tolist())
    consulta = f"""
        SELECT id,
               (0.5 * similarity({columna_nombre}, %(nombre)s)
                + 0.5 * (1 - (embedding <=> %(emb)s::vector))) AS score
        FROM catalogo.{tabla}
        ORDER BY score DESC
        LIMIT 1
    """
    with conn.cursor() as cur:
        cur.execute(consulta, {"nombre": nombre, "emb": embedding})
        fila = cur.fetchone()
    if fila is None or fila[1] < umbral_score:
        return None
    return fila[0]


def fragmentos_de_marbete_por_similitud(
    conn: psycopg.Connection, embedding_pregunta, producto_id: int, top_k: int = 5
) -> list[dict]:
    """El retriever del RAG de marbetes (ver DECISIONES.md, "RAG de marbetes"): los
    fragmentos del marbete del producto (filtro relacional primero), ordenados por
    similitud coseno con la pregunta. Vacío si el producto no tiene marbete con texto."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT f.id, f.pagina, f.texto, d.ruta_archivo,
                   1 - (f.embedding <=> %(emb)s::vector) AS score
            FROM catalogo.fragmento_marbete f
            JOIN catalogo.documento d ON d.id = f.documento_id
            WHERE f.producto_id = %(producto_id)s
            -- Por `score` y no por `embedding <=> ...`: así Postgres filtra por producto
            -- (unos 20 fragmentos) y ordena exacto, en vez de usar el índice HNSW sobre
            -- toda la tabla y filtrar después, que puede devolver menos filas o ninguna.
            ORDER BY score DESC
            LIMIT %(top_k)s
            """,
            {
                "emb": _vector_literal(embedding_pregunta), "producto_id": producto_id,
                "top_k": top_k,
            },
        )
        columnas = [d.name for d in cur.description]
        return [dict(zip(columnas, fila, strict=True)) for fila in cur.fetchall()]
