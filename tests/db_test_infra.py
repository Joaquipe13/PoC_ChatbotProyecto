"""Infraestructura de la base de test para los tests de integración contra
Postgres real (Docker) -- ver DECISIONES.md, "Base de test aislada, no la
de desarrollo".

`redirigir_database_url_a_test()` cambia `DATABASE_URL` a la misma base con
`_test` agregado al nombre, **antes** de que nada llame a `get_settings()`
(que cachea con `lru_cache`): así tanto los tests como el código de
producción bajo prueba (`servicios/recursos.py::con_conexion`, que lee
`get_settings().database_url` en cada llamada) terminan usando la misma
base de test, sin que haga falta configurar nada aparte y sin arriesgar la
de desarrollo -- antes, un test que insertaba con el código de producción
(que sí leía `DATABASE_URL` tal cual) y verificaba con una conexión propia
apuntada a otra base no encontraba nada (ver DIFICULTADES.md).

No es un archivo de test (no matchea `test_*.py` ni `*_test.py`): pytest no
lo colecciona, hay que importarlo.
"""

import os
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest

RAIZ = Path(__file__).resolve().parent
FIXTURES_INSUMOS = RAIZ / "fixtures" / "insumos"
MIGRACIONES = RAIZ.parent / "src" / "fitosanitarios" / "datos" / "migraciones"


def _valor_actual_de_database_url() -> str | None:
    """El `DATABASE_URL` que resolvería `get_settings()` ahora mismo, sin
    llamarla (cachea con `lru_cache`, y no hay que ensuciar esa caché con el
    valor sin redirigir): una env var ya exportada gana, si no se lee del
    `.env` -- misma precedencia que usa pydantic-settings."""
    if os.environ.get("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    from dotenv import dotenv_values

    return dotenv_values(RAIZ.parent / ".env").get("DATABASE_URL")


def redirigir_database_url_a_test() -> None:
    original = _valor_actual_de_database_url()
    if not original:
        return
    partes = urlsplit(original)
    nueva = original if partes.path.endswith("_test") else urlunsplit(
        partes._replace(path=partes.path + "_test")
    )
    os.environ["DATABASE_URL"] = nueva  # gana sobre el .env (misma precedencia)

    from fitosanitarios.config import get_settings

    get_settings.cache_clear()  # por si algo ya la había llamado con el valor viejo


def conectar_o_saltar(database_url: str) -> psycopg.Connection:
    """La base de test, o `pytest.skip` con cómo crearla si no existe
    todavía (una sola vez, no en cada corrida)."""
    try:
        return psycopg.connect(database_url, connect_timeout=3)
    except psycopg.OperationalError as e:
        nombre = urlsplit(database_url).path.lstrip("/")
        pytest.skip(
            f"No hay base de test en {database_url} ({e}). Crearla una vez con:\n"
            f"docker exec fitosanitarios-db psql -U postgres -d postgres -c "
            f'"CREATE DATABASE {nombre} TEMPLATE fitosanitarios;"'
        )


def aplicar_migraciones(conn: psycopg.Connection) -> None:
    """Idempotente (`IF NOT EXISTS` / `ADD COLUMN IF NOT EXISTS` en cada
    migración): al día en cada corrida, sin depender de que alguien se
    acuerde de aplicarlas a mano en la base de test."""
    with conn.cursor() as cur:
        for migracion in sorted(MIGRACIONES.glob("*.sql")):
            cur.execute(migracion.read_text(encoding="utf-8"))
    conn.commit()


def cargar_fixtures_insumos(conn: psycopg.Connection, modelo_embeddings) -> None:
    """Reemplaza `territorio.*` por las localidades sintéticas de
    `tests/fixtures/insumos/` (San Carlos Centro, Colonia Vecina, la ley
    provincial y la nacional). No toca `catalogo.*` ni `operacion.*`."""
    from fitosanitarios.insumos.loader_geo import cargar_localidades
    from fitosanitarios.insumos.loader_normativa import cargar_normativa
    from fitosanitarios.insumos.loader_reglas import cargar_reglas

    with conn.cursor() as cur:
        cur.execute("DELETE FROM territorio.regla_distancia")
        cur.execute("DELETE FROM territorio.articulo")
        cur.execute("DELETE FROM territorio.norma")
        cur.execute("DELETE FROM territorio.zona_protegida")
        cur.execute("DELETE FROM territorio.localidad")
        cur.execute("DELETE FROM territorio.provincia")
    conn.commit()
    cargar_localidades(conn, FIXTURES_INSUMOS)
    cargar_normativa(conn, FIXTURES_INSUMOS, modelo_embeddings)
    cargar_reglas(conn, FIXTURES_INSUMOS)
