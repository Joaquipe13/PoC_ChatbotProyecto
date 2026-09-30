"""Retrievers SQL sobre el schema `territorio` (ver docs/modelo-datos.md).

La localidad se resuelve por nombre (`servicios/localidad.py`), no por la ubicación del
lote: acá no hay consultas geográficas.
"""

import psycopg

from fitosanitarios.datos.vectores import vector_literal
from fitosanitarios.servicios.localidad import Jurisdiccion
from fitosanitarios.servicios.reglas import ReglaCandidata


def reglas_candidatas(
    conn: psycopg.Connection,
    localidad_id: int | None,
    provincia_id: int | None,
    permitido: bool = False,
) -> list[ReglaCandidata]:
    """Reglas de la localidad del lote + provinciales de su provincia +
    nacionales (ver skill, "Geo": reglas candidatas). Por defecto solo las
    prohibiciones (`permitido=False`, las del dictamen); `permitido=True` trae las
    condicionales, para consultas."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT rd.tipo_zona, rd.tipo_aplicacion, rd.bandas, rd.distancia_min_m,
                   n.archivo, a.numero, l.jurisdiccion_id, rd.observaciones, rd.fuente,
                   rd.permitido, rd.condiciones
            FROM territorio.regla_distancia rd
            JOIN territorio.norma n ON n.id = rd.norma_id
            LEFT JOIN territorio.articulo a ON a.id = rd.articulo_id
            LEFT JOIN territorio.localidad l ON l.id = n.localidad_id
            WHERE rd.permitido = %(permitido)s
              AND ((n.ambito = 'municipal' AND n.localidad_id = %(localidad_id)s)
                OR (n.ambito = 'provincial' AND n.provincia_id = %(provincia_id)s)
                OR (n.ambito = 'nacional'))
            """,
            {"localidad_id": localidad_id, "provincia_id": provincia_id, "permitido": permitido},
        )
        filas = cur.fetchall()
    return [
        ReglaCandidata(
            tipo_zona=f[0], tipo_aplicacion=f[1], bandas=list(f[2]),
            distancia_min_m=float(f[3]), norma=f[4], articulo=f[5],
            jurisdiccion_id=f[6], observaciones=f[7], fuente=f[8],
            permitido=f[9], condiciones=f[10],
        )
        for f in filas
    ]


def listar_localidades(conn: psycopg.Connection) -> list[Jurisdiccion]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, jurisdiccion_id, nombre, provincia_id FROM territorio.localidad "
            "ORDER BY nombre"
        )
        return [
            Jurisdiccion(id=f[0], jurisdiccion_id=f[1], nombre=f[2], provincia_id=f[3])
            for f in cur.fetchall()
        ]


def localidad_tiene_normativa_municipal(conn: psycopg.Connection, localidad_id: int) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT EXISTS (SELECT 1 FROM territorio.norma "
            "WHERE ambito = 'municipal' AND localidad_id = %s)",
            (localidad_id,),
        )
        return cur.fetchone()[0]


def listar_provincias(conn: psycopg.Connection) -> list[Jurisdiccion]:
    """Provincias con normativa cargada, con la forma de `Jurisdiccion` para
    reusar `resolver_localidad` (nombre legible: "santa-fe" -> "Santa Fe")."""
    with conn.cursor() as cur:
        cur.execute("SELECT id, nombre FROM territorio.provincia ORDER BY nombre")
        return [
            Jurisdiccion(
                id=f[0], jurisdiccion_id=f[1], nombre=f[1].replace("-", " ").title(),
                provincia_id=f[0],
            )
            for f in cur.fetchall()
        ]


def listar_municipios(conn: psycopg.Connection) -> list[Jurisdiccion]:
    """Municipios y comunas de las provincias con normativa cargada (catálogo
    `territorio.municipio`), con la forma de `Jurisdiccion` para reusar
    `resolver_localidad`. Solo los de provincias que existen en
    `territorio.provincia`: sin normativa provincial no hay a qué recurrir."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT m.id, m.provincia, m.nombre, p.id FROM territorio.municipio m "
            "JOIN territorio.provincia p ON p.nombre = m.provincia ORDER BY m.nombre"
        )
        return [
            # `jurisdiccion_id` = el nombre: con el de la provincia, "Santa Fe"
            # coincidiría con todos los municipios a la vez.
            Jurisdiccion(id=f[0], jurisdiccion_id=f[2], nombre=f[2], provincia_id=f[3])
            for f in cur.fetchall()
        ]


def listar_jurisdicciones_cargadas(conn: psycopg.Connection) -> list[str]:
    """Localidades disponibles para repreguntar cuando la consulta normativa
    no trae jurisdicción explícita (ver skill, matriz de parámetros de
    `responder_consulta_normativa`: "jurisdicción: lista de las localidades
    cargadas")."""
    with conn.cursor() as cur:
        cur.execute("SELECT jurisdiccion_id FROM territorio.localidad ORDER BY nombre")
        return [f[0] for f in cur.fetchall()]


def contexto_normativo_por_similitud(
    conn: psycopg.Connection,
    embedding_pregunta,
    localidad_id: int | None,
    provincia_id: int | None,
    top_k: int = 8,
) -> list[dict]:
    """El retriever del RAG de normativa (23/09/2026, ver DECISIONES.md, "RAG de
    limitaciones"): los fragmentos de normas (artículos partidos y normas sin PDF, como
    los fallos) y las reglas de `reglas.csv` escritas como oración, de la localidad, su
    provincia y la nación, ordenados por similitud coseno con la pregunta. `tipo` dice
    de dónde sale cada uno ("fragmento" o "regla"); `numero` es el artículo, o `None`."""
    embedding = vector_literal(embedding_pregunta)
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT * FROM (
                SELECT 'fragmento' AS tipo, f.id, a.numero, f.texto, n.archivo, n.ambito,
                       COALESCE(l.jurisdiccion_id, pr.nombre, 'nacional') AS jurisdiccion_id,
                       1 - (f.embedding <=> %(emb)s::vector) AS score
                FROM territorio.fragmento_norma f
                JOIN territorio.norma n ON n.id = f.norma_id
                LEFT JOIN territorio.articulo a ON a.id = f.articulo_id
                LEFT JOIN territorio.localidad l ON l.id = n.localidad_id
                LEFT JOIN territorio.provincia pr ON pr.id = n.provincia_id
                WHERE {_ALCANCE_NORMAS}
                UNION ALL
                SELECT 'regla', r.id, a.numero, r.texto, n.archivo, n.ambito,
                       COALESCE(l.jurisdiccion_id, pr.nombre, 'nacional'),
                       1 - (r.embedding <=> %(emb)s::vector)
                FROM territorio.regla_distancia r
                JOIN territorio.norma n ON n.id = r.norma_id
                LEFT JOIN territorio.articulo a ON a.id = r.articulo_id
                LEFT JOIN territorio.localidad l ON l.id = n.localidad_id
                LEFT JOIN territorio.provincia pr ON pr.id = n.provincia_id
                WHERE r.embedding IS NOT NULL AND {_ALCANCE_NORMAS}
            ) contexto
            ORDER BY score DESC
            LIMIT %(top_k)s
            """,
            {
                "emb": embedding, "localidad_id": localidad_id,
                "provincia_id": provincia_id, "top_k": top_k,
            },
        )
        columnas = [d.name for d in cur.description]
        return [dict(zip(columnas, fila, strict=True)) for fila in cur.fetchall()]


_ALCANCE_NORMAS = """
    ((n.ambito = 'municipal' AND n.localidad_id = %(localidad_id)s)
  OR (n.ambito = 'provincial' AND n.provincia_id = %(provincia_id)s)
  OR (n.ambito = 'nacional'))
"""


def articulos_por_numero(
    conn: psycopg.Connection, numero: str, localidad_id: int | None, provincia_id: int | None
) -> list[dict]:
    """Los artículos con ese número en la normativa que corresponde (municipal de
    la localidad + provincial + nacional). Búsqueda exacta, no por similitud: un
    mismo número puede estar en varias normas y hasta repetirse dentro de una (el
    PDF trae anexos con numeración propia), así que devuelve todos, en el orden en
    que se cargaron."""
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT a.id, a.numero, a.texto, a.pagina, a.requiere_revision, n.archivo, n.ambito,
                   COALESCE(l.jurisdiccion_id, pr.nombre, 'nacional') AS jurisdiccion_id
            FROM territorio.articulo a
            JOIN territorio.norma n ON n.id = a.norma_id
            LEFT JOIN territorio.localidad l ON l.id = n.localidad_id
            LEFT JOIN territorio.provincia pr ON pr.id = n.provincia_id
            WHERE lower(a.numero) = lower(%(numero)s) AND {_ALCANCE_NORMAS}
            ORDER BY n.id, a.id
            """,
            {"numero": numero, "localidad_id": localidad_id, "provincia_id": provincia_id},
        )
        columnas = [d.name for d in cur.description]
        return [dict(zip(columnas, fila, strict=True)) for fila in cur.fetchall()]


def normas_de_alcance(
    conn: psycopg.Connection, localidad_id: int | None, provincia_id: int | None
) -> list[dict]:
    """Las normas cargadas que corresponden a esa localidad y provincia, más las
    nacionales: `archivo`, `ambito` y `jurisdiccion_id`."""
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT n.archivo, n.ambito,
                   COALESCE(l.jurisdiccion_id, pr.nombre, 'nacional') AS jurisdiccion_id
            FROM territorio.norma n
            LEFT JOIN territorio.localidad l ON l.id = n.localidad_id
            LEFT JOIN territorio.provincia pr ON pr.id = n.provincia_id
            WHERE {_ALCANCE_NORMAS}
            ORDER BY n.id
            """,
            {"localidad_id": localidad_id, "provincia_id": provincia_id},
        )
        columnas = [d.name for d in cur.description]
        return [dict(zip(columnas, fila, strict=True)) for fila in cur.fetchall()]


def centro_de_localidad(
    conn: psycopg.Connection, localidad_id: int
) -> tuple[float, float] | None:
    """(lat, lon) del centro de la localidad, para pedir el pronóstico; `None` si no se
    cargó (`data/insumos/localidades.csv`)."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT centro_lat, centro_lon FROM territorio.localidad WHERE id = %s",
            (localidad_id,),
        )
        fila = cur.fetchone()
    if fila is None or fila[0] is None or fila[1] is None:
        return None
    return float(fila[0]), float(fila[1])


def reglas_de_viento(
    conn: psycopg.Connection, localidad_id: int | None, provincia_id: int | None
) -> list[dict]:
    """Las normas que se refieren al viento, de la localidad y de su provincia."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT n.archivo AS norma, a.numero AS articulo, l.jurisdiccion_id,
                   rv.viento_max_kmh, rv.descripcion
            FROM territorio.regla_viento rv
            JOIN territorio.norma n ON n.id = rv.norma_id
            LEFT JOIN territorio.articulo a ON a.id = rv.articulo_id
            LEFT JOIN territorio.localidad l ON l.id = n.localidad_id
            WHERE (n.ambito = 'municipal' AND n.localidad_id = %(localidad_id)s)
               OR (n.ambito = 'provincial' AND n.provincia_id = %(provincia_id)s)
            ORDER BY rv.viento_max_kmh
            """,
            {"localidad_id": localidad_id, "provincia_id": provincia_id},
        )
        columnas = [d.name for d in cur.description]
        filas = [dict(zip(columnas, f, strict=True)) for f in cur.fetchall()]
    for f in filas:
        f["viento_max_kmh"] = float(f["viento_max_kmh"])
    return filas
