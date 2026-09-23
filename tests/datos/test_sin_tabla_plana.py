"""Criterio de aceptación transversal de la cátedra (ver plandefases.md,
"Reglas para escribir el plan"): no existe ninguna tabla genérica de
documentos + embedding + metadata (ni la `langchain_pg_embedding` del
PGVector legacy, ni una tabla ancha "documento" propia). Cada entidad que se
busca por significado tiene su propia tabla relacional con sus propias
columnas para filtrar."""

# Nombres de tabla que delatarían una tabla genérica de vector store en vez
# de entidades propias del dominio (nombres reservados de PGVector legacy;
# NO se incluye "documento" acá porque catalogo.documento es legítima --
# está ligada a producto_id, no es un id+embedding+metadata genérico, ver
# el segundo test de este archivo).
NOMBRES_PROHIBIDOS = {
    "langchain_pg_embedding",
    "langchain_pg_collection",
}


def test_no_existe_ninguna_tabla_generica_de_vector_store(conexion):
    with conexion.cursor() as cur:
        cur.execute(
            """
            SELECT table_schema, table_name
            FROM information_schema.tables
            WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
            """
        )
        tablas = cur.fetchall()

    nombres = {nombre for _, nombre in tablas}
    interseccion = nombres & NOMBRES_PROHIBIDOS
    assert not interseccion, f"tabla genérica de vector store encontrada: {interseccion}"


def test_cada_tabla_con_columna_vector_es_una_entidad_propia_del_dominio(conexion):
    """Cada tabla que tiene una columna `vector` tiene que ser una entidad
    de dominio con sus propias columnas para filtrar (no un par
    id+contenido+embedding+metadata genérico)."""
    with conexion.cursor() as cur:
        cur.execute(
            """
            SELECT table_schema, table_name
            FROM information_schema.columns
            WHERE udt_name = 'vector'
            """
        )
        tablas_con_vector = {(schema, tabla) for schema, tabla in cur.fetchall()}

    esperadas = {
        ("catalogo", "producto"),
        ("catalogo", "principio_activo"),
        ("catalogo", "cultivo"),
        ("catalogo", "adversidad"),
        ("catalogo", "vehiculo"),  # RAG de equipos (matricula + caracteristicas propias)
        ("territorio", "articulo"),
        # RAG de limitaciones (23/09/2026): fragmentos de cada norma (FK a norma y
        # artículo) y cada regla de distancia escrita como oración (la propia entidad).
        ("territorio", "fragmento_norma"),
        ("territorio", "regla_distancia"),
        # RAG de marbetes: cada fragmento cuelga de su documento y su producto.
        ("catalogo", "fragmento_marbete"),
    }
    assert tablas_con_vector == esperadas


def test_cada_tabla_de_entidad_tiene_columnas_relacionales_propias(conexion):
    """Verifica que catalogo.producto (una de las tablas con vector) no es
    un par id+embedding: tiene columnas propias para filtrar/joinear."""
    with conexion.cursor() as cur:
        cur.execute(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = 'catalogo' AND table_name = 'producto'
            """
        )
        columnas = {r[0] for r in cur.fetchall()}

    columnas_relacionales_esperadas = {
        "id", "firma_id", "numero_inscripcion", "marca", "banda_toxicologica",
    }
    assert columnas_relacionales_esperadas.issubset(columnas)


def test_fragmento_norma_esta_ligado_a_su_norma_y_su_articulo(conexion):
    """No es un vector store genérico: cada fragmento cuelga de una norma (y de un
    artículo, salvo en las normas sin PDF) por clave foránea."""
    with conexion.cursor() as cur:
        cur.execute(
            """
            SELECT kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON kcu.constraint_name = tc.constraint_name
            WHERE tc.table_schema = 'territorio' AND tc.table_name = 'fragmento_norma'
              AND tc.constraint_type = 'FOREIGN KEY'
            """
        )
        assert {r[0] for r in cur.fetchall()} == {"norma_id", "articulo_id"}
