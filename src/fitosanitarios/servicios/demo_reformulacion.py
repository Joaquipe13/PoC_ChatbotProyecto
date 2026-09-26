"""Modo de prueba de la reformulación (`MODO_DEMO_REFORMULACION=true`), para la
presentación: la tool busca y responde dos veces, con la pregunta tal cual y con la
reformulada, y el operario ve las dos respuestas una debajo de la otra. Así se ve el
problema (el operario pregunta con otras palabras que el documento y no se recupera
nada, o se recupera otra cosa) y cómo lo resuelve la reformulación.

Lo usan `consultar_marbete` y `responder_consulta_normativa`. Cuesta una llamada más a
Gemini por consulta (la respuesta sobre la pregunta original). Ver DECISIONES.md,
"Reformulación de la pregunta".
"""

from collections.abc import Callable

from fitosanitarios.dominio.modelos import ResultadoTool
from fitosanitarios.servicios.reformulacion import consulta_de_busqueda

# La clave de `datos` con el texto ya armado: el formateador lo muestra tal cual.
CLAVE_DEMO = "demo_reformulacion"


def _como_lo_ve_el_operario(nombre_tool: str, resultado: ResultadoTool) -> str:
    # Import diferido: el formateador importa los mensajes de las tools, que importan esto.
    from fitosanitarios.orquestador.formateador import formatear_respuesta
    from fitosanitarios.orquestador.respuesta_directa import respuesta_de_las_tools

    respuesta = respuesta_de_las_tools([nombre_tool], [resultado])
    return "\n\n".join(formatear_respuesta(respuesta, [resultado]))


def comparar_con_y_sin_reformular(
    pregunta: str,
    cliente_llm,
    prompt_reformulacion: str,
    responder: Callable[[str | None], ResultadoTool],
    nombre_tool: str,
) -> ResultadoTool:
    """`responder(consulta)` busca con esa consulta y responde (con `None`, la pregunta
    quedó fuera de tema: sin respaldo). Devuelve el resultado con la reformulación, con el
    texto de la comparación en `datos[CLAVE_DEMO]`."""
    sin_reformular = responder(pregunta)
    consulta = consulta_de_busqueda(pregunta, cliente_llm, prompt_reformulacion)
    reformulado = responder(consulta)

    buscada = (
        consulta if consulta is not None
        else "FUERA (el modelo la considera ajena al tema: no se busca)"
    )
    texto = "\n\n".join([
        "🧪 *Modo prueba: reformulación de la pregunta*",
        f"*Pregunta original:* {pregunta}",
        "*Resultado con la pregunta original:*\n"
        + _como_lo_ve_el_operario(nombre_tool, sin_reformular),
        f"*Pregunta reformulada (lo que se busca):* {buscada}",
        "*Resultado con la pregunta reformulada:*\n"
        + _como_lo_ve_el_operario(nombre_tool, reformulado),
    ])
    return reformulado.model_copy(
        update={"datos": {**(reformulado.datos or {}), CLAVE_DEMO: texto}}
    )
