"""Test de integración de los 3 loaders de insumos contra Postgres real (Docker).

Se salta automáticamente si no hay una base disponible en DATABASE_URL. Para
correrlo:

    docker compose up -d db
    uv run pytest tests/insumos/test_loaders_integracion.py -q

Usa el modelo de embeddings REAL (fixture compartida `modelo_embeddings` de
tests/conftest.py), no uno fake: este archivo hace un DELETE completo de
`territorio.*` y recarga desde las fixtures, y esa base es la misma que se
usa para verificación manual y para los tests de la Fase 6
(`tests/tools/responder_consulta_normativa/test_tool.py`, que necesitan
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
    assert reglas_1 == reglas_2 == 6  # 5 prohibiciones (N) + 1 condicional (S)


def test_regla_provincial_sin_localidad_asociada(conexion, modelo_embeddings):
    _cargar_todo(conexion, modelo_embeddings)
    with conexion.cursor() as cur:
        cur.execute(
            """
            SELECT rd.tipo_zona, rd.distancia_min_m FROM territorio.regla_distancia rd
            JOIN territorio.norma n ON n.id = rd.norma_id
            WHERE n.ambito = 'provincial' AND NOT rd.permitido
            """
        )
        fila = cur.fetchone()
    assert fila == ("zona_urbana", 300)


def test_la_regla_condicional_se_carga_aparte_con_sus_condiciones(conexion, modelo_embeddings):
    _cargar_todo(conexion, modelo_embeddings)
    with conexion.cursor() as cur:
        cur.execute(
            """
            SELECT rd.bandas, rd.distancia_min_m, rd.condiciones, a.numero
            FROM territorio.regla_distancia rd
            JOIN territorio.norma n ON n.id = rd.norma_id
            LEFT JOIN territorio.articulo a ON a.id = rd.articulo_id
            WHERE n.ambito = 'provincial' AND rd.permitido
            """
        )
        fila = cur.fetchone()
    assert fila == (["II"], 100, "con autorizacion del municipio", "2")


def test_norma_nacional_sin_filas_en_reglas_csv_no_rompe_la_carga_ni_da_reglas(
    conexion, modelo_embeddings
):
    # ley-27302-2016 (nacional) no tiene filas en reglas.csv: la normativa nacional es
    # para consultas, así que ni siquiera se le leen distancias del PDF.
    _cargar_todo(conexion, modelo_embeddings)
    with conexion.cursor() as cur:
        cur.execute("SELECT count(*) FROM territorio.norma WHERE ambito = 'nacional'")
        assert cur.fetchone()[0] == 1
        cur.execute(
            "SELECT count(*) FROM territorio.regla_distancia rd "
            "JOIN territorio.norma n ON n.id = rd.norma_id WHERE n.ambito = 'nacional'"
        )
        assert cur.fetchone()[0] == 0


# --- Localidad sin `localidad.geojson` y norma sin PDF (22/09/2026, ver
# DECISIONES.md, "Localidades y normas sin fuente oficial: Sastre y San
# Jorge") -- data sintética propia en tmp_path, no toca FIXTURES: los conteos
# de las otras pruebas de este archivo (2 localidades, 6 reglas) dependen de
# esa carpeta compartida.


def test_localidad_sin_geojson_se_carga_con_norma_sin_pdf(conexion, modelo_embeddings, tmp_path):
    localidad = tmp_path / "testprov" / "testville"
    localidad.mkdir(parents=True)
    (localidad / "fallo-testville-2020.md").write_text(
        "# Fallo de prueba\nTexto de referencia, sin encabezados de artículo.",
        encoding="utf-8",
    )
    (tmp_path / "reglas.csv").write_text(
        "provincia,jurisdiccion,tipo_zona,tipo_aplicacion,banda_toxicologica,distancia_min_m,"
        "permitido,condiciones,norma,articulo,observaciones\n"
        "testprov,testville,zona_urbana,terrestre,todas,500,N,,fallo-testville-2020,,\n",
        encoding="utf-8",
    )

    cargar_localidades(conexion, tmp_path)
    cargar_normativa(conexion, tmp_path, modelo_embeddings)
    total = cargar_reglas(conexion, tmp_path)

    assert total == 1
    with conexion.cursor() as cur:
        cur.execute(
            "SELECT limite, bbox_min_lon FROM territorio.localidad WHERE jurisdiccion_id = %s",
            ("testville",),
        )
        limite, bbox_min_lon = cur.fetchone()
        assert limite is None and bbox_min_lon is None

        cur.execute(
            "SELECT tipo FROM territorio.norma WHERE archivo = 'fallo-testville-2020'"
        )
        assert cur.fetchone() == ("fallo",)

        cur.execute(
            "SELECT count(*) FROM territorio.articulo a "
            "JOIN territorio.norma n ON n.id = a.norma_id "
            "WHERE n.archivo = 'fallo-testville-2020'"
        )
        assert cur.fetchone()[0] == 0  # sin encabezados reales: no se inventan artículos

        cur.execute(
            "SELECT rd.distancia_min_m FROM territorio.regla_distancia rd "
            "JOIN territorio.norma n ON n.id = rd.norma_id "
            "WHERE n.archivo = 'fallo-testville-2020'"
        )
        assert cur.fetchone() == (500,)

    # Este test usa una carpeta propia en vez de FIXTURES (`conexion` borró
    # todo `territorio.*` al empezar): se recarga FIXTURES para no dejar la
    # base sin las localidades sintéticas de las que dependen otros archivos
    # de test que no llaman a `_cargar_todo` por su cuenta (ver
    # DIFICULTADES.md, orden de `tests/insumos/test_loaders_integracion.py`).
    _cargar_todo(conexion, modelo_embeddings)
