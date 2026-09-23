"""Auxiliares de `responder_consulta_normativa`. RAG de normativa (ver skill,
"RAG de normativa"): arma la respuesta con
el LLM usando ÚNICAMENTE los fragmentos recuperados, y verifica en código
que cada artículo citado por el LLM esté efectivamente entre esos
fragmentos -- si no, se descarta la cita y se agrega una advertencia. El LLM
nunca decide solo qué normativa aplica; solo redacta a partir de lo que ya
se recuperó por SQL + similitud.
"""

import json
import logging
import re
from dataclasses import dataclass

from fitosanitarios.dominio.modelos import Cita
from fitosanitarios.tools.responder_consulta_normativa import mensajes
from fitosanitarios.tools.responder_consulta_normativa.prompts import (
    PLANTILLA_FRAGMENTO,
    PLANTILLA_PROMPT_USUARIO,
    PROMPT_SISTEMA_CONSULTA_NORMATIVA,
)

logger = logging.getLogger(__name__)

_PATRON_NUMERO_ARTICULO = re.compile(r"\d+")


def _normalizar_numero_articulo(valor: str) -> str:
    """El contexto que se arma en `_armar_contexto` etiqueta cada fragmento
    como "art. {numero}", y el LLM tiende a copiar ese prefijo en
    "articulos_citados" en vez de devolver solo el número (ver
    DIFICULTADES.md). Sin normalizar, el matching exacto contra `numero`
    descarta citas válidas."""
    m = _PATRON_NUMERO_ARTICULO.search(valor)
    # Sin número ("", "sin artículo"): la cita es de un fragmento sin artículo (un fallo).
    return m.group(0) if m else ""


@dataclass
class FragmentoNormativa:
    articulo_id: int  # el id del fragmento o de la regla en su tabla
    numero: str | None  # el artículo; None en un fallo o una norma sin artículos
    texto: str
    norma: str
    ambito: str
    jurisdiccion_id: str
    score: float
    tipo: str = "fragmento"  # "fragmento" (texto de la norma) o "regla" (de reglas.csv)


def _referencia(f: FragmentoNormativa) -> str:
    if f.tipo == "regla":
        return f"regla cargada, art. {f.numero}" if f.numero else "regla cargada"
    return f"art. {f.numero}" if f.numero else "sin artículo"


def filtrar_por_umbral(
    fragmentos: list[FragmentoNormativa], umbral: float
) -> list[FragmentoNormativa]:
    return [f for f in fragmentos if f.score >= umbral]


def _armar_contexto(fragmentos: list[FragmentoNormativa]) -> str:
    return "\n\n".join(
        PLANTILLA_FRAGMENTO.format(
            norma=f.norma, referencia=_referencia(f), jurisdiccion_id=f.jurisdiccion_id,
            texto=f.texto,
        )
        for f in fragmentos
    )


def _parsear_json(respuesta: str) -> dict | None:
    texto = respuesta.strip()
    if texto.startswith("```"):
        texto = texto.strip("`")
        if texto.startswith("json"):
            texto = texto[4:]
        texto = texto.strip()
    try:
        datos = json.loads(texto)
    except json.JSONDecodeError:
        logger.warning("El LLM no devolvió JSON válido para consulta normativa")
        return None
    if not isinstance(datos, dict):
        return None
    return datos


@dataclass
class RespuestaNormativa:
    veredicto: str
    regla: str
    citas: list[Cita]
    advertencias: list[str]


def responder_con_fragmentos(
    pregunta: str, fragmentos: list[FragmentoNormativa], cliente_llm
) -> RespuestaNormativa:
    contexto = _armar_contexto(fragmentos)
    prompt = PLANTILLA_PROMPT_USUARIO.format(pregunta=pregunta, contexto=contexto)
    respuesta = cliente_llm.generar(prompt, system=PROMPT_SISTEMA_CONSULTA_NORMATIVA)

    datos = _parsear_json(respuesta)
    if datos is None:
        return RespuestaNormativa(
            veredicto="Depende",
            regla=mensajes.REGLA_RESPUESTA_ININTERPRETABLE,
            citas=[], advertencias=[mensajes.ADVERTENCIA_LLM_SIN_JSON],
        )

    veredicto = datos.get("veredicto") or "Depende"
    regla = datos.get("regla") or ""
    articulos_citados = datos.get("articulos_citados") or []

    # Un fragmento sin artículo (un fallo) se cita por la norma sola: su clave es "".
    fragmentos_por_clave = {
        (f.norma, _normalizar_numero_articulo(f.numero or "")): f for f in fragmentos
    }
    citas: list[Cita] = []
    advertencias: list[str] = []

    for ac in articulos_citados:
        clave = (ac.get("norma"), _normalizar_numero_articulo(str(ac.get("articulo") or "")))
        fragmento = fragmentos_por_clave.get(clave)
        if fragmento is None:
            advertencias.append(
                mensajes.advertencia_cita_descartada(ac.get("norma"), ac.get("articulo"))
            )
            continue
        citas.append(
            Cita(
                fuente="normativa", jurisdiccion_id=fragmento.jurisdiccion_id,
                norma=fragmento.norma, articulo=fragmento.numero,
            )
        )

    return RespuestaNormativa(
        veredicto=veredicto, regla=regla, citas=citas, advertencias=advertencias
    )
