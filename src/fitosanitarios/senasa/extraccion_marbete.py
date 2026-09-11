"""Extracción de usos (cultivo, adversidad, dosis) desde el texto de un marbete.

Dos pasos: texto con pdfplumber (determinista), estructura con el LLM (no
determinista, se cachea por n° de registro -- ver skill, sección "SENASA").
Se corre solo para los productos y cultivos del caso de estudio, no para todo
el catálogo (plandefases.md, Fase 2, tarea 3): es cara en tokens/tiempo y la
mayoría de los productos no tiene marbete de todos modos.

Verificado en vivo (12/09/2026) contra un marbete real (SENASA reg. 36.515,
"DECIS 10 EC"): la tabla de dosis por cultivo/plaga en el PDF original tiene
columnas que `pdfplumber.extract_text()` reordena de forma poco legible como
texto plano (columnas de cultivo/plaga/dosis intercaladas) -- confirma por
qué la skill pide extracción por LLM en vez de un parser de tablas
determinista para este caso. Ver DECISIONES.md para el resultado de la
revisión manual de una muestra (tarea 8 de la Fase 2).
"""

import io
import json
import logging

import pdfplumber
from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)


class UsoExtraidoLLM(BaseModel):
    cultivo: str
    adversidad: str | None = None
    dosis: str  # texto libre tal como aparece; se parsea después con parser_dosis
    confianza: float  # 0-1, autoevaluada por el LLM


PROMPT_SISTEMA_EXTRACCION = (
    "Sos un asistente que extrae, del texto de un marbete (etiqueta) de un "
    "producto fitosanitario argentino, los usos autorizados. Para cada "
    "combinación de cultivo y adversidad (plaga, maleza o enfermedad) que "
    "encuentres, extraé la dosis tal como figura en el texto, sin convertir "
    "unidades ni inventar datos que no estén escritos.\n"
    "Respondé ÚNICAMENTE una lista JSON (sin texto alrededor, sin markdown) "
    "de objetos con las claves: cultivo, adversidad (string o null si el "
    "texto no la nombra), dosis (string, tal como aparece), confianza "
    "(número de 0 a 1: qué tan clara y completa te resultó la fila para ese "
    "cultivo). Si no encontrás ningún uso en el texto, respondé []."
)


def extraer_texto_pdf(contenido_pdf: bytes) -> str:
    with pdfplumber.open(io.BytesIO(contenido_pdf)) as pdf:
        paginas = [pagina.extract_text() or "" for pagina in pdf.pages]
    return "\n".join(paginas).strip()


def extraer_usos_desde_texto(texto_marbete: str, cliente_llm) -> list[UsoExtraidoLLM]:
    """`cliente_llm` es cualquier objeto con `.generar(prompt, *, system=None) -> str`
    (ver llm/client.py y llm/fake.py): real o fake, según USE_FIXTURES."""
    texto = texto_marbete.strip()
    if not texto:
        return []

    respuesta = cliente_llm.generar(texto[:8000], system=PROMPT_SISTEMA_EXTRACCION)
    datos = _parsear_json_lista(respuesta)
    if datos is None:
        return []

    usos: list[UsoExtraidoLLM] = []
    for item in datos:
        try:
            usos.append(UsoExtraidoLLM.model_validate(item))
        except ValidationError:
            logger.warning("Uso extraído con forma inválida, se descarta: %r", item)
    return usos


def _parsear_json_lista(respuesta: str) -> list | None:
    """El LLM a veces envuelve el JSON en ```json ... ``` pese a la
    instrucción de no hacerlo; se tolera ese caso antes de descartar."""
    texto = respuesta.strip()
    if texto.startswith("```"):
        texto = texto.strip("`")
        if texto.startswith("json"):
            texto = texto[4:]
        texto = texto.strip()
    try:
        datos = json.loads(texto)
    except json.JSONDecodeError:
        logger.warning("El LLM no devolvió JSON válido para extracción de marbete")
        return None
    if not isinstance(datos, list):
        logger.warning("El LLM devolvió JSON pero no una lista: %r", type(datos))
        return None
    return datos
