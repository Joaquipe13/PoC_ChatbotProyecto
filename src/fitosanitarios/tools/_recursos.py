"""Recursos compartidos por las tools que hablan con la base (conexión +
modelo de embeddings). Import diferido en cada tool para no disparar
conexión real al importar el módulo (los tests importan las tools sin base).

Nota para la Fase 7: acá se crea una conexión y se carga el modelo de
embeddings en cada llamada, lo cual es correcto pero no eficiente. El
orquestador real probablemente va a querer inyectar una conexión/pool y un
modelo ya cargado en vez de que cada tool arranque los suyos.
"""

from collections.abc import Callable


def con_conexion_y_modelo[T](funcion: Callable[..., T]) -> T:
    import psycopg
    from sentence_transformers import SentenceTransformer

    from fitosanitarios.config import get_settings

    settings = get_settings()
    modelo = SentenceTransformer(settings.embeddings_model)
    with psycopg.connect(settings.database_url) as conn:
        return funcion(conn, modelo)


def con_conexion[T](funcion: Callable[..., T]) -> T:
    """Como `con_conexion_y_modelo`, sin cargar el modelo de embeddings --
    para tools que no hacen matching semántico (Fase 9: `resolver_vehiculo`,
    `registrar_evento`, `consultar_agenda` resuelven contra un catálogo
    chico con trigram, ver DECISIONES.md)."""
    import psycopg

    from fitosanitarios.config import get_settings

    with psycopg.connect(get_settings().database_url) as conn:
        return funcion(conn)
