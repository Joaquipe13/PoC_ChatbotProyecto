"""Test de integración del loader contra Postgres real (Docker).

Se salta automáticamente si no hay una base disponible en DATABASE_URL (por
ejemplo en CI, que hoy no levanta un servicio de Postgres -- ver
plandefases.md Fase 5, que sí lo exige para los retrievers). Para correrlo:

    docker compose up -d db
    uv run pytest tests/senasa/test_loader.py -q

Usa el modelo de embeddings REAL (fixture compartida `modelo_embeddings` de
tests/conftest.py): este test hace upsert sobre `catalogo.producto` por
`numero_inscripcion`, así que si alguno de los 50 productos de la fixture ya
existe en la base (cargado de verdad en la Fase 2), un modelo fake le
pisaría el embedding real con uno dummy cada vez que corre la suite
completa -- exactamente lo que pasó con `territorio.articulo` en la Fase 6
(ver DIFICULTADES.md).
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


def test_cargar_catalogo_puebla_producto(conexion, modelo_embeddings):
    productos = leer_snapshot(FIXTURE)
    assert len(productos) == 50

    resumen = cargar_catalogo(conexion, productos, modelo_embeddings)

    assert resumen["productos"] == 50
    with conexion.cursor() as cur:
        cur.execute("SELECT count(*) FROM catalogo.producto")
        assert cur.fetchone()[0] >= 50


def test_cargar_catalogo_es_idempotente(conexion, modelo_embeddings):
    productos = leer_snapshot(FIXTURE)[:10]

    resumen_1 = cargar_catalogo(conexion, productos, modelo_embeddings)
    with conexion.cursor() as cur:
        cur.execute("SELECT count(*) FROM catalogo.producto")
        despues_de_primera_carga = cur.fetchone()[0]

    resumen_2 = cargar_catalogo(conexion, productos, modelo_embeddings)
    with conexion.cursor() as cur:
        cur.execute("SELECT count(*) FROM catalogo.producto")
        despues_de_segunda_carga = cur.fetchone()[0]

    assert resumen_1["productos"] == resumen_2["productos"] == 10
    assert despues_de_primera_carga == despues_de_segunda_carga


def test_cargar_catalogo_pobla_usos_registrados_con_aplicaciones_reales(
    conexion, modelo_embeddings
):
    productos = leer_snapshot(FIXTURE)
    con_aplicaciones = [
        (item, detalle)
        for item, detalle in productos
        if detalle and detalle.aplicaciones_por_producto
    ]
    assert con_aplicaciones, "la fixture debería tener al menos un producto con aplicaciones"

    cargar_catalogo(conexion, con_aplicaciones, modelo_embeddings)

    with conexion.cursor() as cur:
        cur.execute("SELECT count(*) FROM catalogo.uso_registrado")
        assert cur.fetchone()[0] > 0
        cur.execute(
            "SELECT fuente FROM catalogo.uso_registrado LIMIT 1",
        )
        assert cur.fetchone()[0] == "senasa_estructurado"


def test_recargar_no_duplica_usos_registrados(conexion, modelo_embeddings):
    productos = leer_snapshot(FIXTURE)
    con_aplicaciones = [
        (item, detalle)
        for item, detalle in productos
        if detalle and detalle.aplicaciones_por_producto
    ]
    registros = [item.numero_inscripcion for item, _ in con_aplicaciones]
    consulta = (
        "SELECT count(*) FROM catalogo.uso_registrado u"
        " JOIN catalogo.producto p ON p.id = u.producto_id"
        " WHERE p.numero_inscripcion = ANY(%s)"
    )

    resumen = cargar_catalogo(conexion, con_aplicaciones, modelo_embeddings)
    with conexion.cursor() as cur:
        cur.execute(consulta, (registros,))
        despues_de_primera_carga = cur.fetchone()[0]

    cargar_catalogo(conexion, con_aplicaciones, modelo_embeddings)
    with conexion.cursor() as cur:
        cur.execute(consulta, (registros,))
        despues_de_segunda_carga = cur.fetchone()[0]

    assert despues_de_primera_carga == resumen["usos_registrados"] > 0
    assert despues_de_segunda_carga == despues_de_primera_carga
