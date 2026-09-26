"""Tests de integración de articulos_por_similitud (territorio.py) contra
Postgres real, sobre la normativa real congelada en `tests/fixtures/insumos/`
(Ordenanza 841/2010 de El Trébol, Ley 11.273 y su decreto; las normas de Sastre y
San Jorge son `.md` sin artículos)."""

from fitosanitarios.datos.retrievers.territorio import (
    articulos_por_similitud,
    obtener_localidad_por_jurisdiccion_id,
)


def _normas(conexion, modelo_embeddings, jurisdiccion_id, pregunta):
    localidad = obtener_localidad_por_jurisdiccion_id(conexion, jurisdiccion_id)
    assert localidad is not None
    embedding = modelo_embeddings.encode(pregunta).tolist()
    filas = articulos_por_similitud(conexion, embedding, localidad.id, localidad.provincia_id)
    return filas, {f["archivo"] for f in filas}


def test_articulos_de_el_trebol_incluyen_su_ordenanza(conexion, modelo_embeddings):
    _, normas = _normas(
        conexion, modelo_embeddings, "el-trebol",
        "pulverizaciones con vientos que produzcan derivas hacia la planta urbana",
    )
    assert "ordenanza-841-2010" in normas


def test_articulos_de_otra_localidad_no_incluyen_la_ordenanza_de_el_trebol(
    conexion, modelo_embeddings
):
    _, normas = _normas(
        conexion, modelo_embeddings, "sastre",
        "pulverizaciones con vientos que produzcan derivas hacia la planta urbana",
    )
    assert "ordenanza-841-2010" not in normas


def test_articulos_incluye_normativa_provincial(conexion, modelo_embeddings):
    _, normas = _normas(
        conexion, modelo_embeddings, "el-trebol",
        "aplicación aérea dentro del radio de 3000 metros de las plantas urbanas",
    )
    assert "ley-11273-1995" in normas  # provincial de Santa Fe


def test_articulos_ordenados_por_similitud_descendente(conexion, modelo_embeddings):
    filas, _ = _normas(
        conexion, modelo_embeddings, "el-trebol",
        "¿a qué distancia del pueblo puedo aplicar por tierra?",
    )
    scores = [f["score"] for f in filas]
    assert scores == sorted(scores, reverse=True)


def test_obtener_localidad_inexistente_devuelve_none(conexion):
    assert obtener_localidad_por_jurisdiccion_id(conexion, "localidad-que-no-existe") is None
