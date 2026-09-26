"""Reformular la pregunta antes de buscar en un RAG (el paso "contextualizar la pregunta"
del notebook de RAG de la cursada, `Ejemplos/NLP_3_langchain_conversaciones_rag_v2.ipynb`).

El operario pregunta con sus palabras ("¿cuándo puedo volver a entrar al lote?", "¿a
cuánto del pueblo puedo fumigar?") y el documento usa otras ("reingresar al área
tratada", "planta urbana"). El LLM escribe una línea con los términos que usaría el
documento, y se busca con la pregunta original más esa línea. La respuesta se sigue
redactando sobre la pregunta original.

Lo usan `consultar_marbete` y `responder_consulta_normativa`, cada uno con su prompt
(qué documento es y qué términos usa). Ver DECISIONES.md, "Reformulación de la pregunta".
"""

import logging

logger = logging.getLogger(__name__)

# Lo que responde el LLM si la pregunta no es del tema: "¿qué hora es?" se reformulaba como
# "tiempo de espera, días de carencia" y recuperaba páginas del marbete.
RESPUESTA_FUERA_DE_TEMA = "FUERA"
# Una línea de términos; más largo es el LLM divagando.
LARGO_MAXIMO_REFORMULACION = 400


def consulta_de_busqueda(pregunta: str, cliente_llm, prompt_reformulacion: str) -> str | None:
    """La pregunta más los términos que escribe el LLM. `None` si el LLM dice que la
    pregunta no es del tema; si falla (cuota, red, respuesta vacía), la pregunta tal cual:
    sin la reformulación se puede buscar igual."""
    try:
        reformulada = cliente_llm.generar(
            f"Pregunta: {pregunta}", system=prompt_reformulacion
        ).strip().splitlines()[0].strip()
    except Exception:
        logger.warning("No se pudo reformular la pregunta", exc_info=True)
        return pregunta
    if reformulada.upper().strip(" .") == RESPUESTA_FUERA_DE_TEMA:
        return None
    return f"{pregunta} {reformulada[:LARGO_MAXIMO_REFORMULACION]}"
