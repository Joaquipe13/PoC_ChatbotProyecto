"""Helper compartido para pasar embeddings a Postgres/pgvector."""


def vector_literal(embedding) -> str:
    """`embedding`: lista o array de floats. Devuelve el literal de texto que
    entiende `::vector` en SQL (`'[0.1,0.2,...]'`)."""
    return "[" + ",".join(repr(float(x)) for x in embedding) + "]"
