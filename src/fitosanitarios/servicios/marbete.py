"""Responder una pregunta con el marbete de un producto (RAG de marbetes, ver
DECISIONES.md): recupera los fragmentos de su marbete con búsqueda híbrida (similitud +
palabras, `servicios/busqueda_hibrida.py`), el LLM responde solo con ellos y cada página
que cita se verifica en código contra lo recuperado.

Lo usan `consultar_marbete` y `validar_producto_registro` (la dosis de un producto sin usos
registrados en SENASA: la busca en su marbete). Antes estaba dentro de `consultar_marbete`.
Los prompts de la respuesta viven acá porque los comparten las dos tools; el de la
reformulación de la pregunta es solo de `consultar_marbete`.
"""

import json
import logging
from dataclasses import dataclass, field

from fitosanitarios.datos.retrievers.catalogo import fragmentos_de_marbete, palabras_de
from fitosanitarios.servicios.busqueda_hibrida import seleccionar

logger = logging.getLogger(__name__)

TOP_K_FRAGMENTOS = 5

PROMPT_SISTEMA_MARBETE = (
    "Sos un asistente que responde preguntas sobre el marbete (la etiqueta aprobada por "
    "SENASA) de un producto fitosanitario, usando ÚNICAMENTE los fragmentos del marbete "
    "que se te dan en el mensaje. Nunca respondas con información que no esté en esos "
    "fragmentos, aunque la sepas de otra fuente. No copies el texto del marbete: resumilo "
    "en una o dos oraciones, con los números tal como aparecen.\n\n"
    "Respondé ÚNICAMENTE un JSON (sin texto alrededor, sin markdown) con esta forma "
    'exacta:\n{"respuesta": "una o dos oraciones en español", "paginas_citadas": '
    "[números de página de los fragmentos que usaste]}\n\n"
    "Si ningún fragmento responde la pregunta, poné en \"respuesta\" que el marbete no lo "
    "dice y dejá \"paginas_citadas\" vacío."
)

PLANTILLA_PROMPT_USUARIO = (
    "Producto: {producto}\nPregunta: {pregunta}\n\nFragmentos del marbete:\n{contexto}"
)
PLANTILLA_FRAGMENTO = "[página {pagina}]\n{texto}"


@dataclass
class RespuestaMarbete:
    """`paginas` vacía: el marbete no respalda ninguna respuesta (sin texto, ningún
    fragmento pasa el umbral o el LLM no citó ninguna página recuperada)."""

    respuesta: str = ""
    paginas: list[int] = field(default_factory=list)
    paginas_descartadas: list = field(default_factory=list)
    sin_json: bool = False


def _parsear_json(respuesta: str) -> dict | None:
    texto = respuesta.strip().removeprefix("```json").removeprefix("```").removesuffix("```")
    try:
        datos = json.loads(texto.strip())
    except json.JSONDecodeError:
        logger.warning("El LLM no devolvió JSON válido al responder con el marbete")
        return None
    return datos if isinstance(datos, dict) else None


def responder_con_el_marbete(
    pregunta: str, consulta: str, producto_id: int, marca: str, conn, modelo_embeddings,
    cliente_llm, umbral_similitud: float,
) -> RespuestaMarbete:
    """Busca en el marbete del producto con `consulta` y responde `pregunta`."""
    # Retrieval híbrido: los fragmentos del marbete de ese producto, rankeados por
    # similitud de significado y por palabras (BM25), fusionados.
    del_marbete = fragmentos_de_marbete(
        conn, modelo_embeddings.encode(consulta).tolist(), producto_id
    )
    elegidos = seleccionar(
        [f["score"] for f in del_marbete], [f["palabras"] for f in del_marbete],
        palabras_de(conn, consulta), umbral_similitud, TOP_K_FRAGMENTOS,
    )
    fragmentos = [del_marbete[p.indice] for p in elegidos]
    if not fragmentos:
        return RespuestaMarbete()

    # Generación: el LLM responde solo con esos fragmentos.
    contexto = "\n\n".join(
        PLANTILLA_FRAGMENTO.format(pagina=f["pagina"], texto=f["texto"]) for f in fragmentos
    )
    respuesta_llm = cliente_llm.generar(
        PLANTILLA_PROMPT_USUARIO.format(producto=marca, pregunta=pregunta, contexto=contexto),
        system=PROMPT_SISTEMA_MARBETE,
    )
    datos_llm = _parsear_json(respuesta_llm)
    if datos_llm is None:
        return RespuestaMarbete(sin_json=True)

    # Verificación: cada página citada tiene que estar entre los fragmentos recuperados.
    recuperadas = {f["pagina"] for f in fragmentos}
    resultado = RespuestaMarbete(respuesta=datos_llm.get("respuesta") or "")
    for pagina in datos_llm.get("paginas_citadas") or []:
        try:
            numero = int(pagina)
        except (TypeError, ValueError):
            numero = None
        if numero in recuperadas and numero not in resultado.paginas:
            resultado.paginas.append(numero)
        elif numero not in resultado.paginas:
            resultado.paginas_descartadas.append(pagina)
    resultado.paginas.sort()
    return resultado
