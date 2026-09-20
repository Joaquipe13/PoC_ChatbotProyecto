"""Retrievers SQL sobre el schema `territorio` (ver docs/modelo-datos.md).

Prefiltro por bounding box en SQL; el punto-en-polígono y las distancias
exactas se calculan en Python (`servicios/geo.py`) sobre lo que devuelven
estos retrievers -- sin PostGIS (ver skill, "Base de datos").
"""

import math

import psycopg

from fitosanitarios.datos.vectores import vector_literal
from fitosanitarios.servicios.geo import LocalidadCandidata, ZonaCandidata
from fitosanitarios.servicios.localidad import Jurisdiccion
from fitosanitarios.servicios.reglas import ReglaCandidata

METROS_POR_GRADO_LAT = 111_320


def radio_metros_a_grados(radio_m: float, lat: float) -> float:
    """Conversión aproximada solo para el prefiltro de bbox (no para la
    distancia final, que se calcula reproyectando a un CRS métrico). Usa la
    conversión de longitud (más grados por metro a medida que crece |lat|),
    así el margen nunca queda más chico de lo necesario."""
    metros_por_grado_lon = METROS_POR_GRADO_LAT * max(math.cos(math.radians(lat)), 0.01)
    return radio_m / metros_por_grado_lon


def localidades_candidatas_por_punto(
    conn: psycopg.Connection, lat: float, lon: float
) -> list[LocalidadCandidata]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, jurisdiccion_id, nombre, provincia_id, limite
            FROM territorio.localidad
            WHERE %(lon)s BETWEEN bbox_min_lon AND bbox_max_lon
              AND %(lat)s BETWEEN bbox_min_lat AND bbox_max_lat
            """,
            {"lat": lat, "lon": lon},
        )
        filas = cur.fetchall()
    return [
        LocalidadCandidata(
            id=f[0], jurisdiccion_id=f[1], nombre=f[2], provincia_id=f[3], limite=f[4]
        )
        for f in filas
    ]


def zonas_protegidas_en_radio(
    conn: psycopg.Connection, lat: float, lon: float, radio_m: float
) -> list[ZonaCandidata]:
    """Incluye zonas de localidades vecinas dentro del radio (ver skill,
    "Geo": "una escuela del pueblo de al lado puede estar a 50 m")."""
    radio_grados = radio_metros_a_grados(radio_m, lat)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT zp.id, zp.tipo, zp.nombre, l.jurisdiccion_id, zp.geometria
            FROM territorio.zona_protegida zp
            JOIN territorio.localidad l ON l.id = zp.localidad_id
            WHERE zp.bbox_min_lon <= %(lon)s + %(radio)s
              AND zp.bbox_max_lon >= %(lon)s - %(radio)s
              AND zp.bbox_min_lat <= %(lat)s + %(radio)s
              AND zp.bbox_max_lat >= %(lat)s - %(radio)s
            """,
            {"lat": lat, "lon": lon, "radio": radio_grados},
        )
        filas = cur.fetchall()
    return [
        ZonaCandidata(id=f[0], tipo=f[1], nombre=f[2], jurisdiccion_id=f[3], geometria=f[4])
        for f in filas
    ]


def reglas_candidatas(
    conn: psycopg.Connection, localidad_id: int | None, provincia_id: int | None
) -> list[ReglaCandidata]:
    """Reglas de la localidad del lote + provinciales de su provincia +
    nacionales (ver skill, "Geo": reglas candidatas)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT rd.tipo_zona, rd.tipo_aplicacion, rd.bandas, rd.distancia_min_m,
                   n.archivo, a.numero, l.jurisdiccion_id, rd.observaciones, rd.fuente
            FROM territorio.regla_distancia rd
            JOIN territorio.norma n ON n.id = rd.norma_id
            LEFT JOIN territorio.articulo a ON a.id = rd.articulo_id
            LEFT JOIN territorio.localidad l ON l.id = n.localidad_id
            WHERE (n.ambito = 'municipal' AND n.localidad_id = %(localidad_id)s)
               OR (n.ambito = 'provincial' AND n.provincia_id = %(provincia_id)s)
               OR (n.ambito = 'nacional')
            """,
            {"localidad_id": localidad_id, "provincia_id": provincia_id},
        )
        filas = cur.fetchall()
    return [
        ReglaCandidata(
            tipo_zona=f[0], tipo_aplicacion=f[1], bandas=list(f[2]),
            distancia_min_m=float(f[3]), norma=f[4], articulo=f[5],
            jurisdiccion_id=f[6], observaciones=f[7], fuente=f[8],
        )
        for f in filas
    ]


def obtener_localidad_por_jurisdiccion_id(
    conn: psycopg.Connection, jurisdiccion_id: str
) -> Jurisdiccion | None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, jurisdiccion_id, nombre, provincia_id FROM territorio.localidad "
            "WHERE jurisdiccion_id = %(jid)s",
            {"jid": jurisdiccion_id},
        )
        fila = cur.fetchone()
    if fila is None:
        return None
    return Jurisdiccion(id=fila[0], jurisdiccion_id=fila[1], nombre=fila[2], provincia_id=fila[3])


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


def listar_jurisdicciones_cargadas(conn: psycopg.Connection) -> list[str]:
    """Localidades disponibles para repreguntar cuando la consulta normativa
    no trae jurisdicción explícita (ver skill, matriz de parámetros de
    `responder_consulta_normativa`: "jurisdicción: lista de las localidades
    cargadas")."""
    with conn.cursor() as cur:
        cur.execute("SELECT jurisdiccion_id FROM territorio.localidad ORDER BY nombre")
        return [f[0] for f in cur.fetchall()]


def articulos_por_similitud(
    conn: psycopg.Connection,
    embedding_pregunta,
    localidad_id: int | None,
    provincia_id: int | None,
    top_k: int = 8,
) -> list[dict]:
    """Filtro relacional primero (jurisdicción del lote/consulta + provincia
    + nacional), similitud vectorial después (ver skill, "RAG de
    normativa"). `score` es similitud coseno (1 = idéntico)."""
    embedding = vector_literal(embedding_pregunta)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT a.id, a.numero, a.texto, a.pagina, n.archivo, n.ambito,
                   COALESCE(l.jurisdiccion_id, pr.nombre, 'nacional') AS jurisdiccion_id,
                   1 - (a.embedding <=> %(emb)s::vector) AS score
            FROM territorio.articulo a
            JOIN territorio.norma n ON n.id = a.norma_id
            LEFT JOIN territorio.localidad l ON l.id = n.localidad_id
            LEFT JOIN territorio.provincia pr ON pr.id = n.provincia_id
            WHERE (n.ambito = 'municipal' AND n.localidad_id = %(localidad_id)s)
               OR (n.ambito = 'provincial' AND n.provincia_id = %(provincia_id)s)
               OR (n.ambito = 'nacional')
            ORDER BY a.embedding <=> %(emb)s::vector
            LIMIT %(top_k)s
            """,
            {
                "emb": embedding, "localidad_id": localidad_id,
                "provincia_id": provincia_id, "top_k": top_k,
            },
        )
        columnas = [d.name for d in cur.description]
        return [dict(zip(columnas, fila, strict=True)) for fila in cur.fetchall()]
