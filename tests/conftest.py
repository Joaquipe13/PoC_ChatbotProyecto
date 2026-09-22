"""Fixtures compartidas para tests de integración contra Postgres real
(Docker). Se saltan automáticamente si no hay base disponible.

Corren siempre contra una base de test aparte, nunca contra la de
desarrollo: `redirigir_database_url_a_test()` (ver `db_test_infra.py`)
cambia `DATABASE_URL` apenas se importa este archivo, antes de que nada
(test o código de producción bajo prueba) llame a `get_settings()`.

`_base_de_test` deja la base lista una sola vez por sesión -- migraciones
aplicadas y las localidades sintéticas de `tests/fixtures/insumos/`
cargadas -- así ningún archivo de test depende de que otro haya corrido
antes para tenerlas (antes: DIFICULTADES.md, "el orden de los tests
importa"; `tests/datos/test_retrievers_*` fallaban si corrían antes que
`tests/insumos/test_loaders_integracion.py`).
`tests/insumos/test_loaders_integracion.py` no depende de `_base_de_test`:
tiene su propio `conexion` de función porque las reglas que prueba son
justamente los loaders."""

import psycopg
import pytest

from fitosanitarios.config import get_settings
from tests.db_test_infra import (
    aplicar_migraciones,
    cargar_fixtures_insumos,
    conectar_o_saltar,
    redirigir_database_url_a_test,
)

redirigir_database_url_a_test()


@pytest.fixture(scope="session")
def modelo_embeddings():
    """Modelo real (no fake): estos tests validan las consultas SQL reales
    de trigram + pgvector, que necesitan un embedding de verdad."""
    from sentence_transformers import SentenceTransformer

    settings = get_settings()
    return SentenceTransformer(settings.embeddings_model)


@pytest.fixture(scope="session")
def _base_de_test(modelo_embeddings) -> None:
    conn = conectar_o_saltar(get_settings().database_url)
    try:
        aplicar_migraciones(conn)
        cargar_fixtures_insumos(conn, modelo_embeddings)
    finally:
        conn.close()


@pytest.fixture(scope="module")
def conexion(_base_de_test) -> psycopg.Connection:
    conn = conectar_o_saltar(get_settings().database_url)
    yield conn
    conn.close()
