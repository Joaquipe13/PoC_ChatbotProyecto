"""Datos de la conversación en curso que las tools sacan del `config` del turno
(no de los argumentos que arma el LLM)."""

from langchain_core.runnables import RunnableConfig


def thread_id_de_config(config: RunnableConfig | None) -> str:
    """El hilo de la conversación (un operario). Las tools de agenda y de registro
    de aplicaciones lo usan para saber de quién son las tareas."""
    thread_id = (config or {}).get("configurable", {}).get("thread_id")
    if not thread_id:
        raise ValueError("la tool necesita un thread_id en el config del turno")
    return thread_id
