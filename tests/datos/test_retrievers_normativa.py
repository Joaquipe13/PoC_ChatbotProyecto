"""Tests de integración de articulos_por_similitud (territorio.py) contra
Postgres real, sobre la normativa sintética de la Fase 3 (San Carlos Centro,
Colonia Vecina, provincial Santa Fe)."""

from fitosanitarios.datos.retrievers.territorio import (
    articulos_por_similitud,
    obtener_localidad_por_jurisdiccion_id,
)


def test_articulos_de_san_carlos_no_incluye_los_de_colonia_vecina(conexion, modelo_embeddings):
    localidad = obtener_localidad_por_jurisdiccion_id(conexion, "san-carlos-centro")
    assert localidad is not None

    embedding = modelo_embeddings.encode("distancia minima a una escuela").tolist()
    filas = articulos_por_similitud(conexion, embedding, localidad.id, localidad.provincia_id)

    normas = {f["archivo"] for f in filas}
    assert "ordenanza-914-2018" in normas
    assert "ordenanza-45-2019" not in normas  # es de colonia-vecina, no debe aparecer


def test_articulos_incluye_normativa_provincial(conexion, modelo_embeddings):
    localidad = obtener_localidad_por_jurisdiccion_id(conexion, "san-carlos-centro")
    embedding = modelo_embeddings.encode("distancia a zona urbana").tolist()
    filas = articulos_por_similitud(conexion, embedding, localidad.id, localidad.provincia_id)
    normas = {f["archivo"] for f in filas}
    assert "ley-13740-2017" in normas  # provincial de Santa Fe


def test_articulos_ordenados_por_similitud_descendente(conexion, modelo_embeddings):
    localidad = obtener_localidad_por_jurisdiccion_id(conexion, "san-carlos-centro")
    embedding = modelo_embeddings.encode(
        "¿a qué distancia de una escuela puedo aplicar por tierra?"
    ).tolist()
    filas = articulos_por_similitud(conexion, embedding, localidad.id, localidad.provincia_id)
    scores = [f["score"] for f in filas]
    assert scores == sorted(scores, reverse=True)


def test_obtener_localidad_inexistente_devuelve_none(conexion):
    assert obtener_localidad_por_jurisdiccion_id(conexion, "localidad-que-no-existe") is None
