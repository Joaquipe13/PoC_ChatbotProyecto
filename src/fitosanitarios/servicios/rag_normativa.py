"""RAG de normativa (ver skill, "RAG de normativa"): arma la respuesta con
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

logger = logging.getLogger(__name__)

_PATRON_NUMERO_ARTICULO = re.compile(r"\d+")


def _normalizar_numero_articulo(valor: str) -> str:
    """El contexto que se arma en `_armar_contexto` etiqueta cada fragmento
    como "art. {numero}", y el LLM tiende a copiar ese prefijo en
    "articulos_citados" en vez de devolver solo el número (ver
    DIFICULTADES.md). Sin normalizar, el matching exacto contra `numero`
    descarta citas válidas."""
    m = _PATRON_NUMERO_ARTICULO.search(valor)
    return m.group(0) if m else valor.strip()


@dataclass
class FragmentoNormativa:
    articulo_id: int
    numero: str
    texto: str
    norma: str
    ambito: str
    jurisdiccion_id: str
    score: float


PROMPT_SISTEMA_CONSULTA_NORMATIVA = (
    "Sos un asistente que responde preguntas sobre normativa de aplicación de "
    "fitosanitarios en Argentina, usando ÚNICAMENTE los fragmentos de artículo "
    "que se te dan en el mensaje. Nunca respondas con información que no esté "
    "en esos fragmentos, aunque la sepas de otra fuente. Si ningún fragmento "
    "responde la pregunta, decilo explícitamente.\n\n"
    "Respondé ÚNICAMENTE un JSON (sin texto alrededor, sin markdown) con esta "
    "forma exacta:\n"
    '{"veredicto": "Si" | "No" | "Depende", "regla": "una oración en español '
    'con la regla aplicable", "articulos_citados": [{"norma": string, '
    '"articulo": string}, ...]}\n\n'
    "\"articulos_citados\" tiene que listar exactamente los artículos (norma + "
    "número, tal como aparecen en los fragmentos) que usaste para responder. "
    "Si no hay fragmentos suficientes, poné \"veredicto\": \"Depende\", "
    "explicá en \"regla\" que no hay información suficiente, y dejá "
    "\"articulos_citados\" vacío."
)


def filtrar_por_umbral(
    fragmentos: list[FragmentoNormativa], umbral: float
) -> list[FragmentoNormativa]:
    return [f for f in fragmentos if f.score >= umbral]


def _armar_contexto(fragmentos: list[FragmentoNormativa]) -> str:
    bloques = [
        f"[{f.norma}, art. {f.numero}, jurisdicción: {f.jurisdiccion_id}]\n{f.texto}"
        for f in fragmentos
    ]
    return "\n\n".join(bloques)


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
    prompt = f"Pregunta: {pregunta}\n\nFragmentos disponibles:\n{contexto}"
    respuesta = cliente_llm.generar(prompt, system=PROMPT_SISTEMA_CONSULTA_NORMATIVA)

    datos = _parsear_json(respuesta)
    if datos is None:
        return RespuestaNormativa(
            veredicto="Depende",
            regla="No se pudo interpretar la respuesta del asistente.",
            citas=[], advertencias=["respuesta del LLM no era JSON válido"],
        )

    veredicto = datos.get("veredicto") or "Depende"
    regla = datos.get("regla") or ""
    articulos_citados = datos.get("articulos_citados") or []

    fragmentos_por_clave = {
        (f.norma, _normalizar_numero_articulo(str(f.numero))): f for f in fragmentos
    }
    citas: list[Cita] = []
    advertencias: list[str] = []

    for ac in articulos_citados:
        clave = (ac.get("norma"), _normalizar_numero_articulo(str(ac.get("articulo") or "")))
        fragmento = fragmentos_por_clave.get(clave)
        if fragmento is None:
            advertencias.append(
                f"El asistente citó {ac.get('norma')} art. {ac.get('articulo')}, que no "
                "está entre los fragmentos recuperados; se descartó esa cita."
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
