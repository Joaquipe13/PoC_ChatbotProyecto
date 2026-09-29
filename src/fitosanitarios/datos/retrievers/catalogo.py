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


@dataclass
class ListadoProductos:
    productos: list[dict]
    total: int  # los que cumplen los filtros, no solo los de esta página


def listar_productos_por_filtro(
    conn: psycopg.Connection,
    cultivo_id: int | None = None,
    adversidad_id: int | None = None,
    principio_activo_id: int | None = None,
    aptitudes: list[str] | None = None,
    firma_ids: list[int] | None = None,
    marca: str | None = None,
    bandas_permitidas: list[str] | None = None,
    limite: int = 10,
    offset: int = 0,
) -> ListadoProductos:
    """Retriever de `consultar_productos`: una fila por producto que cumple todos los
    filtros dados, en cualquier combinación. Cultivo, adversidad y principio activo llegan
    ya resueltos por embedding contra su tabla; la aptitud se filtra sobre el JSONB del
    registro (`crudo_api->'productos_aptitudes'`); la marca, por texto contenido.

    Con cultivo o adversidad, solo entran los productos con un uso registrado que coincida,
    y cada fila trae las dosis de esos usos y de cuántas plagas son. Antes era una fila por
    uso: el mismo producto salía diez veces, una por maleza, y el total era el `LIMIT`."""
    if not any((
        cultivo_id, adversidad_id, principio_activo_id, aptitudes, firma_ids, marca,
        bandas_permitidas,
    )):
        raise ValueError("listar_productos_por_filtro requiere al menos un filtro")

    with conn.cursor() as cur:
        cur.execute(
            """
            WITH usos AS (
                SELECT ur.producto_id,
                       array_remove(array_agg(DISTINCT NULLIF(ur.dosis->>'texto_original', '')),
                                    NULL) AS dosis,
                       count(DISTINCT ur.adversidad_id) AS adversidades
                FROM catalogo.uso_registrado ur
                WHERE %(con_usos)s
                  AND (%(cultivo_id)s::bigint IS NULL OR ur.cultivo_id = %(cultivo_id)s)
                  AND (%(adversidad_id)s::bigint IS NULL OR ur.adversidad_id = %(adversidad_id)s)
                GROUP BY ur.producto_id
            )
            SELECT p.id, p.numero_inscripcion, p.marca, p.banda_toxicologica,
                   f.nombre AS firma, u.dosis, u.adversidades,
                   count(*) OVER () AS total
            FROM catalogo.producto p
            LEFT JOIN catalogo.firma f ON f.id = p.firma_id
            LEFT JOIN usos u ON u.producto_id = p.id
            WHERE (NOT %(con_usos)s OR u.producto_id IS NOT NULL)
              AND (%(principio_id)s::bigint IS NULL OR EXISTS (
                    SELECT 1 FROM catalogo.producto_principio_activo ppa
                    WHERE ppa.producto_id = p.id
                      AND ppa.principio_activo_id = %(principio_id)s))
              AND (%(aptitudes)s::text[] IS NULL OR EXISTS (
                    SELECT 1
                    FROM jsonb_array_elements(
                        COALESCE(p.crudo_api->'productos_aptitudes', '[]'::jsonb)) apt
                    WHERE apt->'nomenclador'->>'descripcion' = ANY(%(aptitudes)s)))
              AND (%(firma_ids)s::bigint[] IS NULL OR p.firma_id = ANY(%(firma_ids)s))
              AND (%(marca)s::text IS NULL OR p.marca ILIKE '%%' || %(marca)s || '%%')
              AND (%(bandas)s::text[] IS NULL OR p.banda_toxicologica = ANY(%(bandas)s))
            ORDER BY p.marca, p.numero_inscripcion
            LIMIT %(limite)s OFFSET %(offset)s
            """,
            {
                "con_usos": cultivo_id is not None or adversidad_id is not None,
                "cultivo_id": cultivo_id, "adversidad_id": adversidad_id,
                "principio_id": principio_activo_id, "aptitudes": aptitudes or None,
                "firma_ids": firma_ids or None, "marca": marca or None,
                "bandas": bandas_permitidas, "limite": limite, "offset": offset,
            },
        )
        columnas = [d.name for d in cur.description]
        filas = [dict(zip(columnas, fila, strict=True)) for fila in cur.fetchall()]
    total = filas[0].pop("total") if filas else 0
    for f in filas[1:]:
        f.pop("total")
    return ListadoProductos(productos=filas, total=total)


def aptitudes_registradas(conn: psycopg.Connection) -> list[str]:
    """Las aptitudes que usa el registro ("Fungicida", "Terapico trat. semillas"...), para
    resolver lo que dijo el operario contra ellas."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT apt->'nomenclador'->>'descripcion'
            FROM catalogo.producto p,
                 jsonb_array_elements(
                     COALESCE(p.crudo_api->'productos_aptitudes', '[]'::jsonb)) apt
            WHERE apt->'nomenclador'->>'descripcion' IS NOT NULL
            """
        )
        return sorted(f[0] for f in cur.fetchall())


def resolver_firmas(conn: psycopg.Connection, nombre: str, umbral: float = 0.7) -> list[int]:
    """Las firmas cuyo nombre contiene lo que dijo el operario ("Syngenta" -> "SYNGENTA
    AGRO S.A." y cualquier otra razón social de la misma empresa). Por trigram de palabras:
    tolera un error de tipeo."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id FROM catalogo.firma
            WHERE word_similarity(%(nombre)s, nombre) >= %(umbral)s
            ORDER BY word_similarity(%(nombre)s, nombre) DESC
            """,
            {"nombre": nombre, "umbral": umbral},
        )
        return [f[0] for f in cur.fetchall()]


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


def fragmentos_de_marbete(
    conn: psycopg.Connection, embedding_pregunta, producto_id: int
) -> list[dict]:
    """El retriever del RAG de marbetes (ver DECISIONES.md, "RAG de marbetes" y "Búsqueda
    híbrida en los marbetes"): todos los fragmentos del marbete del producto (unos 25),
    con su similitud coseno con la pregunta y sus palabras llevadas a la raíz por el
    full-text en español de Postgres, una vez por cada aparición (para BM25). El ranking
    lo arma `servicios/busqueda_hibrida.py`. Vacío si el producto no tiene marbete con
    texto."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT f.id, f.pagina, f.texto,
                   1 - (f.embedding <=> %(emb)s::vector) AS score,
                   ARRAY(
                       SELECT u.lexeme
                       FROM unnest(to_tsvector('spanish', f.texto)) u,
                            generate_series(1, COALESCE(array_length(u.positions, 1), 1))
                   ) AS palabras
            FROM catalogo.fragmento_marbete f
            WHERE f.producto_id = %(producto_id)s
            ORDER BY f.pagina, f.orden
            """,
            {"emb": _vector_literal(embedding_pregunta), "producto_id": producto_id},
        )
        columnas = [d.name for d in cur.description]
        return [dict(zip(columnas, fila, strict=True)) for fila in cur.fetchall()]


def palabras_de(conn: psycopg.Connection, texto: str) -> list[str]:
    """Las palabras de un texto llevadas a la raíz, sin las vacías ("que", "para", "al"),
    con el mismo full-text en español que `fragmentos_de_marbete`."""
    with conn.cursor() as cur:
        cur.execute("SELECT tsvector_to_array(to_tsvector('spanish', %s))", (texto,))
        return list(cur.fetchone()[0] or [])
