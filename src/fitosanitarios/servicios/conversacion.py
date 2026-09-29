"""Datos de la conversación en curso que las tools sacan del `config` o del estado del
turno (no de los argumentos que arma el LLM)."""

from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.runnables import RunnableConfig

from fitosanitarios.servicios.reglas import texto_plano


def thread_id_de_config(config: RunnableConfig | None) -> str:
    """El hilo de la conversación (un operario). Las tools de agenda y de registro
    de aplicaciones lo usan para saber de quién son las tareas."""
    thread_id = (config or {}).get("configurable", {}).get("thread_id")
    if not thread_id:
        raise ValueError("la tool necesita un thread_id en el config del turno")
    return thread_id


def _texto_de(contenido) -> str:
    if isinstance(contenido, str):
        return contenido
    if isinstance(contenido, list):  # un mensaje con foto: partes de texto e imagen
        return " ".join(
            p.get("text", "") if isinstance(p, dict) else str(p) for p in contenido
        )
    return ""


def lo_dicho_en_la_conversacion(mensajes: list) -> str:
    """Lo que dijo el operario y lo que devolvieron las tools (una receta leída trae el
    cultivo), en texto plano. Para verificar que un dato que pasó el LLM salió de algún
    lado: los argumentos que el propio LLM escribió no cuentan."""
    return texto_plano(" ".join(
        _texto_de(m.content) for m in mensajes if isinstance(m, HumanMessage | ToolMessage)
    ))


def se_menciona(valor: str, dicho: str) -> bool:
    """`valor` (o su raíz: "trigos", "soja/sojas") aparece en lo dicho."""
    plano = texto_plano(valor)
    return bool(plano) and (plano in dicho or (len(plano) > 5 and plano[:-1] in dicho))
