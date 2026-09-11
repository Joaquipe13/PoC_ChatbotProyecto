"""Test de integración de los 3 loaders de insumos contra Postgres real (Docker).

Se salta automáticamente si no hay una base disponible en DATABASE_URL. Para
correrlo:

    docker compose up -d db
    uv run pytest tests/insumos/test_loaders_integracion.py -q

Usa el modelo de embeddings REAL (fixture compartida `modelo_embeddings` de
tests/conftest.py), no uno fake: este archivo hace un DELETE completo de
`territorio.*` y recarga desde las fixtures, y esa base es la misma que se
usa para verificación manual y para los tests de la Fase 6
(`tests/tools/test_responder_consulta_normativa.py`, que necesitan
similitud vectorial real). Usar un modelo fake acá corrompía esos datos con
embeddings dummy cada vez que corría la suite completa (ver DIFICULTADES.md).
"""

from pathlib import Path

import psycopg
import pytest

from fitosanitarios.config import get_settings
from fitosanitarios.insumos.loader_geo import cargar_localidades
from fitosanitarios.insumos.loader_normativa import cargar_normativa
from fitosanitarios.insumos.loader_reglas import cargar_reglas

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "insumos"


@pytest.fixture
def conexion():
    settings = get_settings()
    try:
        conn = psycopg.connect(settings.database_url, connect_timeout=3)
    except psycopg.OperationalError:
        pytest.skip("No hay Postgres disponible en DATABASE_URL (docker compose up -d db)")
    with conn.cursor() as cur:
        cur.execute("DELETE FROM territorio.regla_distancia")
        cur.execute("DELETE FROM territorio.articulo")
        cur.execute("DELETE FROM territorio.norma")
        cur.execute("DELETE FROM territorio.zona_protegida")
        cur.execute("DELETE FROM territorio.localidad")
        cur.execute("DELETE FROM territorio.provincia")
    conn.commit()
    yield conn
    conn.close()


def _cargar_todo(conn, modelo_embeddings):
    cargar_localidades(conn, FIXTURES)
    cargar_normativa(conn, FIXTURES, modelo_embeddings)
    return cargar_reglas(conn, FIXTURES)


def test_carga_completa_puebla_al_menos_2_localidades(conexion, modelo_embeddings):
    _cargar_todo(conexion, modelo_embeddings)
    with conexion.cursor() as cur:
        cur.execute("SELECT jurisdiccion_id FROM territorio.localidad ORDER BY jurisdiccion_id")
        jurisdicciones = [r[0] for r in cur.fetchall()]
    assert set(jurisdicciones) == {"san-carlos-centro", "colonia-vecina"}


def test_carga_completa_puebla_articulos_y_reglas_con_join(conexion, modelo_embeddings):
    _cargar_todo(conexion, modelo_embeddings)
    with conexion.cursor() as cur:
        cur.execute(
            """
            SELECT l.jurisdiccion_id, rd.tipo_zona, rd.distancia_min_m, n.archivo, a.numero
            FROM territorio.regla_distancia rd
            JOIN territorio.norma n ON n.id = rd.norma_id
            LEFT JOIN territorio.articulo a ON a.id = rd.articulo_id
            LEFT JOIN territorio.localidad l ON l.id = n.localidad_id
            WHERE l.jurisdiccion_id = 'san-carlos-centro' AND rd.tipo_zona = 'escuela'
              AND rd.tipo_aplicacion = 'terrestre'
            """
        )
        fila = cur.fetchone()
    assert fila is not None
    _, tipo_zona, distancia, archivo, articulo = fila
    assert distancia == 100
    assert archivo == "ordenanza-914-2018"
    assert articulo == "8"


def test_filtro_por_jurisdiccion_excluye_articulos_de_otra_localidad(conexion, modelo_embeddings):
    _cargar_todo(conexion, modelo_embeddings)
    with conexion.cursor() as cur:
        cur.execute(
            "SELECT id FROM territorio.localidad WHERE jurisdiccion_id = 'san-carlos-centro'"
        )
        (localidad_id,) = cur.fetchone()
        cur.execute(
            """
            SELECT a.numero FROM territorio.articulo a
            JOIN territorio.norma n ON n.id = a.norma_id
            WHERE n.localidad_id = %s
            """,
            (localidad_id,),
        )
        numeros = {r[0] for r in cur.fetchall()}
    # Los artículos de san-carlos-centro son 8, 9, 10 (ordenanza-914-2018);
    # el artículo 5 de colonia-vecina (ordenanza-45-2019) no debe aparecer acá.
    assert numeros == {"8", "9", "10"}


def test_carga_es_idempotente(conexion, modelo_embeddings):
    _cargar_todo(conexion, modelo_embeddings)
    with conexion.cursor() as cur:
        cur.execute("SELECT count(*) FROM territorio.localidad")
        localidades_1 = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM territorio.regla_distancia")
        reglas_1 = cur.fetchone()[0]

    _cargar_todo(conexion, modelo_embeddings)
    with conexion.cursor() as cur:
        cur.execute("SELECT count(*) FROM territorio.localidad")
        localidades_2 = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM territorio.regla_distancia")
        reglas_2 = cur.fetchone()[0]

    assert localidades_1 == localidades_2 == 2
    assert reglas_1 == reglas_2 == 5


def test_regla_provincial_sin_localidad_asociada(conexion, modelo_embeddings):
    _cargar_todo(conexion, modelo_embeddings)
    with conexion.cursor() as cur:
        cur.execute(
            """
            SELECT rd.tipo_zona, rd.distancia_min_m FROM territorio.regla_distancia rd
            JOIN territorio.norma n ON n.id = rd.norma_id
            WHERE n.ambito = 'provincial'
            """
        )
        fila = cur.fetchone()
    assert fila == ("zona_urbana", 300)


def test_norma_nacional_sin_reglas_csv_no_rompe_la_carga(conexion, modelo_embeddings):
    # ley-27302-2016 (nacional) no tiene reglas.csv -- es opcional (ver
    # docs/contrato-insumos.md). La carga completa no debe fallar por eso.
    _cargar_todo(conexion, modelo_embeddings)
    with conexion.cursor() as cur:
        cur.execute("SELECT count(*) FROM territorio.norma WHERE ambito = 'nacional'")
        assert cur.fetchone()[0] == 1
