"""Clon de la base para las corridas de evaluación.

Los escenarios que escriben (agendar una aplicación, registrar un evento) no pueden
correr sobre la base de desarrollo. Este script clona la base de `DATABASE_URL` como
`<base>_eval` (con el catálogo, la normativa y el checkpointer) y la borra al terminar.
El harness (`evals/chat.py`) se niega a correr contra una base cuyo nombre no termine
en `_eval`.

    uv run python -m evals.base_eval crear    # clona (la base de origen no puede tener conexiones)
    uv run python -m evals.base_eval borrar
    uv run python -m evals.base_eval url      # la URL para EVAL_DATABASE_URL
"""

import argparse
import os
import sys

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

SUFIJO = "_eval"


def url_origen() -> str:
    from fitosanitarios.config import get_settings

    return os.environ.get("DATABASE_URL") or get_settings().database_url


def url_con_base(url: str, base: str) -> str:
    return make_conninfo(url, dbname=base)


def nombre_base(url: str) -> str:
    return conninfo_to_dict(url)["dbname"]


def url_eval(url_origen_: str | None = None) -> str:
    origen = url_origen_ or url_origen()
    base = nombre_base(origen)
    return origen if base.endswith(SUFIJO) else url_con_base(origen, base + SUFIJO)


def crear(url: str | None = None) -> str:
    origen = url or url_origen()
    base = nombre_base(origen)
    destino = base + SUFIJO
    with psycopg.connect(url_con_base(origen, "postgres"), autocommit=True) as conn:
        conn.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(destino)))
        conn.execute(
            sql.SQL("CREATE DATABASE {} TEMPLATE {}").format(
                sql.Identifier(destino), sql.Identifier(base)
            )
        )
    return url_con_base(origen, destino)


def borrar(url: str | None = None) -> None:
    origen = url or url_origen()
    destino = nombre_base(origen)
    destino = destino if destino.endswith(SUFIJO) else destino + SUFIJO
    with psycopg.connect(url_con_base(origen, "postgres"), autocommit=True) as conn:
        conn.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(destino)))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("accion", choices=["crear", "borrar", "url"])
    accion = parser.parse_args().accion
    if accion == "crear":
        crear()
        print(f"Base clonada: {nombre_base(url_origen())}{SUFIJO}")
    elif accion == "borrar":
        borrar()
        print("Base de evaluación borrada")
    else:
        print(url_eval())


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
