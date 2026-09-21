"""Confirmación de una receta leída de una foto, decidida en código.

La política (skill, "Reglas de repregunta") es que una receta de foto siempre se
confirma antes de evaluarla. Dejar que el LLM se acuerde no alcanza: con Gemini, el
usuario contestó solo el dato que faltaba ("el trebol") y el bot evaluó y dio APTA sin
que hubiera confirmado nada (`evals/runs/20260921-192037`, hallazgo H2). Acá se mira la
conversación: hay una confirmación pendiente si se mostró la de una receta y el usuario
todavía no la aceptó; contestar solo un dato pedido no es aceptarla.
"""

import re

from langchain_core.messages import AIMessage, HumanMessage

# Palabras con las que se acepta lo leído. Las cortas (si, ok) tienen que ser una palabra
# entera: "asi" no es un "si". Una lista generosa a propósito: si falla por no reconocer una
# aceptación, el bot vuelve a preguntar (falla segura); lo grave sería evaluar sin aceptación.
PALABRAS_DE_CONFIRMACION = (
    "confirm", "si", "sí", "sii", "dale", "ok", "oka", "okey", "correcto", "esta bien",
    "está bien", "bien", "perfecto", "listo", "joya", "de acuerdo", "adelante", "evalu",
    "procede", "proceda", "aprobado", "mandale", "hacelo",
)


def es_confirmacion(texto: str) -> bool:
    minusculas = texto.lower()
    palabras = set(re.findall(r"\w+", minusculas))
    return any(
        (p in palabras) if " " not in p and len(p) <= 4 else (p in minusculas)
        for p in PALABRAS_DE_CONFIRMACION
    )


def hay_receta_sin_confirmar(mensajes: list) -> bool:
    """`mensajes`: la conversación del agente (estado de LangGraph), con el mensaje actual
    del usuario y las llamadas a tools del turno en curso."""
    pendiente = False
    for m in mensajes:
        if isinstance(m, AIMessage):
            for llamada in m.tool_calls:
                es_confirmacion_mostrada = (
                    llamada.get("name") == "RespuestaAgente"
                    and (llamada.get("args") or {}).get("tipo") == "confirmacion_receta"
                )
                # `leer_receta` en este mismo turno: la confirmación todavía no se mostró
                if es_confirmacion_mostrada or llamada.get("name") == "leer_receta":
                    pendiente = True
        elif isinstance(m, HumanMessage) and pendiente and es_confirmacion(str(m.content)):
            pendiente = False
    return pendiente
