"""Fixtures compartidas para tests de integración contra Postgres real
(Docker). Se saltan automáticamente si no hay base disponible."""

import psycopg
import pytest

from fitosanitarios.config import get_settings


@pytest.fixture(scope="module")
def conexion():
    settings = get_settings()
    try:
        conn = psycopg.connect(settings.database_url, connect_timeout=3)
    except psycopg.OperationalError:
        pytest.skip("No hay Postgres disponible en DATABASE_URL (docker compose up -d db)")
    yield conn
    conn.close()


@pytest.fixture(scope="module")
def modelo_embeddings():
    """Modelo real (no fake): estos tests validan las consultas SQL reales
    de trigram + pgvector, que necesitan un embedding de verdad. Scope de
    módulo para no recargar el modelo en cada test."""
    from sentence_transformers import SentenceTransformer

    settings = get_settings()
    return SentenceTransformer(settings.embeddings_model)
