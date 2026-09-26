"""Recursos compartidos por las tools que hablan con la base (conexión +
modelo de embeddings). Import diferido en cada tool para no disparar
conexión real al importar el módulo (los tests importan las tools sin base).

El modelo de embeddings se carga una sola vez por proceso (`modelo_embeddings`): antes
se cargaba en cada llamada a una tool, unos 10 s cada vez (medido el 23/09/2026), y era
buena parte de las demoras de 30-60 s por turno (hallazgo H6 de la evaluación
conversacional). Los canales lo precargan al arrancar. La conexión a la base sigue
siendo una por llamada.
"""

import threading
from collections.abc import Callable

_modelo = None
_lock_modelo = threading.Lock()


def modelo_embeddings():
    """El modelo de embeddings de `EMBEDDINGS_MODEL`, cargado la primera vez que se pide.
    El lock evita que dos mensajes que llegan juntos lo carguen dos veces."""
    global _modelo
    if _modelo is None:
        with _lock_modelo:
            if _modelo is None:
                from sentence_transformers import SentenceTransformer

                from fitosanitarios.config import get_settings

                _modelo = SentenceTransformer(get_settings().embeddings_model)
    return _modelo


def con_conexion_y_modelo[T](funcion: Callable[..., T]) -> T:
    import psycopg

    from fitosanitarios.config import get_settings

    modelo = modelo_embeddings()
    with psycopg.connect(get_settings().database_url) as conn:
        return funcion(conn, modelo)


def con_conexion[T](funcion: Callable[..., T]) -> T:
    """Como `con_conexion_y_modelo`, sin el modelo de embeddings -- para tools que no
    hacen matching semántico (Fase 9: `resolver_vehiculo`, `registrar_evento`,
    `consultar_agenda` resuelven contra un catálogo chico con trigram, ver
    DECISIONES.md)."""
    import psycopg

    from fitosanitarios.config import get_settings

    with psycopg.connect(get_settings().database_url) as conn:
        return funcion(conn)


def precargar_modelo_embeddings() -> None:
    """Para los canales, al arrancar: así el primer mensaje no paga la carga. Se avisa por
    stderr (como el chequeo de credenciales) porque uvicorn no muestra los INFO."""
    import sys
    import time

    inicio = time.monotonic()
    modelo_embeddings()
    print(
        f"Modelo de embeddings cargado ({time.monotonic() - inicio:.0f} s).",
        file=sys.stderr, flush=True,
    )


_cliente_meteo = None


def cliente_meteorologia(settings):
    """El cliente de Open-Meteo, uno por proceso (así su caché sirve entre turnos).
    `None` con `USE_FIXTURES=true`: todo el flujo corre sin red, sin pronóstico."""
    global _cliente_meteo
    if settings.use_fixtures:
        return None
    if _cliente_meteo is None:
        from fitosanitarios.servicios.meteorologia import ClienteOpenMeteo

        _cliente_meteo = ClienteOpenMeteo(settings.meteo_base_url)
    return _cliente_meteo
