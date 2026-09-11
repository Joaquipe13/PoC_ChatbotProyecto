"""Test de integración del loader contra Postgres real (Docker).

Se salta automáticamente si no hay una base disponible en DATABASE_URL (por
ejemplo en CI, que hoy no levanta un servicio de Postgres -- ver
plandefases.md Fase 5, que sí lo exige para los retrievers). Para correrlo:

    docker compose up -d db
    uv run pytest tests/senasa/test_loader.py -q
"""

from pathlib import Path

import psycopg
import pytest

from fitosanitarios.config import get_settings
from fitosanitarios.senasa.loader import cargar_catalogo, leer_snapshot

FIXTURES_SENASA = Path(__file__).resolve().parent.parent / "fixtures" / "senasa"
FIXTURE = FIXTURES_SENASA / "muestra_50_productos.jsonl"


@pytest.fixture
def conexion():
    settings = get_settings()
    try:
        conn = psycopg.connect(settings.database_url, connect_timeout=3)
    except psycopg.OperationalError:
        pytest.skip("No hay Postgres disponible en DATABASE_URL (docker compose up -d db)")
    yield conn
    conn.rollback()
    conn.close()


@pytest.fixture
def modelo_embeddings_fake():
    """Evita bajar/correr sentence-transformers en este test: alcanza con
    vectores fake de la dimensión correcta para probar la carga a la base.
    Devuelve un array numpy, como el `SentenceTransformer.encode()` real
    (el loader llama `.tolist()` sobre el resultado)."""
    import numpy as np

    class _ModeloFake:
        def encode(self, texto):
            semilla = abs(hash(texto)) % 1000
            return np.array([((semilla + i) % 100) / 100.0 for i in range(768)])

    return _ModeloFake()


def test_cargar_catalogo_puebla_producto(conexion, modelo_embeddings_fake):
    productos = leer_snapshot(FIXTURE)
    assert len(productos) == 50

    resumen = cargar_catalogo(conexion, productos, modelo_embeddings_fake)

    assert resumen["productos"] == 50
    with conexion.cursor() as cur:
        cur.execute("SELECT count(*) FROM catalogo.producto")
        assert cur.fetchone()[0] >= 50


def test_cargar_catalogo_es_idempotente(conexion, modelo_embeddings_fake):
    productos = leer_snapshot(FIXTURE)[:10]

    resumen_1 = cargar_catalogo(conexion, productos, modelo_embeddings_fake)
    with conexion.cursor() as cur:
        cur.execute("SELECT count(*) FROM catalogo.producto")
        despues_de_primera_carga = cur.fetchone()[0]

    resumen_2 = cargar_catalogo(conexion, productos, modelo_embeddings_fake)
    with conexion.cursor() as cur:
        cur.execute("SELECT count(*) FROM catalogo.producto")
        despues_de_segunda_carga = cur.fetchone()[0]

    assert resumen_1["productos"] == resumen_2["productos"] == 10
    assert despues_de_primera_carga == despues_de_segunda_carga


def test_cargar_catalogo_pobla_usos_registrados_con_aplicaciones_reales(
    conexion, modelo_embeddings_fake
):
    productos = leer_snapshot(FIXTURE)
    con_aplicaciones = [
        (item, detalle)
        for item, detalle in productos
        if detalle and detalle.aplicaciones_por_producto
    ]
    assert con_aplicaciones, "la fixture debería tener al menos un producto con aplicaciones"

    cargar_catalogo(conexion, con_aplicaciones, modelo_embeddings_fake)

    with conexion.cursor() as cur:
        cur.execute("SELECT count(*) FROM catalogo.uso_registrado")
        assert cur.fetchone()[0] > 0
        cur.execute(
            "SELECT fuente FROM catalogo.uso_registrado LIMIT 1",
        )
        assert cur.fetchone()[0] == "senasa_estructurado"
