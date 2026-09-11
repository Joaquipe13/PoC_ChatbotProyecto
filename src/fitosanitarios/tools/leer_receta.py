"""Tool `leer_receta`: envuelve `servicios/extraccion_receta.py` para el
orquestador (Fase 7). Valida la entrada, llama al servicio y arma
`ResultadoTool`; no tiene lógica de negocio propia (ver skill, "Arquitectura":
"Las tools validan la entrada, llaman servicios y devuelven ResultadoTool").
"""

import base64

from langchain_core.tools import tool
from pydantic import BaseModel

from fitosanitarios.dominio.modelos import ResultadoTool
from fitosanitarios.dominio.motivos import MotivoNoResuelto
from fitosanitarios.servicios.extraccion_receta import (
    CacheExtraccion,
    convertir_a_receta_y_faltantes,
    extraer_receta_de_imagen,
)


class LeerRecetaArgs(BaseModel):
    imagen_base64: str  # imagen ya descargada del media de WhatsApp, en base64


def leer_receta_logica(
    imagen: bytes, cliente_llm, cache: CacheExtraccion | None = None
) -> ResultadoTool:
    """Lógica de la tool, testeable directamente sin pasar por el decorador
    de LangChain (que es lo que usan los tests con LLM fake)."""
    extraccion = extraer_receta_de_imagen(imagen, cliente_llm, cache=cache)
    if not extraccion.legible:
        return ResultadoTool(estado="no_resuelto", motivo=MotivoNoResuelto.IMAGEN_ILEGIBLE)

    receta, faltantes = convertir_a_receta_y_faltantes(extraccion)
    if faltantes:
        return ResultadoTool(
            estado="faltan_datos",
            datos=receta.model_dump(mode="json"),
            faltantes=faltantes,
        )
    return ResultadoTool(estado="ok", datos=receta.model_dump(mode="json"))


def _resumen_para_llm(resultado: ResultadoTool) -> str:
    if resultado.estado == "ok":
        return "Receta leída correctamente, todos los campos con confianza suficiente."
    if resultado.estado == "faltan_datos":
        campos = ", ".join(f.campo for f in resultado.faltantes)
        return f"Receta leída parcialmente. Faltan o no se leyeron con confianza: {campos}."
    return "No se pudo leer la imagen como una receta (no es legible)."


@tool("leer_receta", args_schema=LeerRecetaArgs, response_format="content_and_artifact")
def leer_receta(imagen_base64: str) -> tuple[str, ResultadoTool]:
    """Lee una foto de una receta agronómica y extrae sus datos estructurados.

    Usar cuando el operario manda una foto de una receta fitosanitaria nueva.
    No usar para preguntas de texto sobre productos o normativa, ni para
    confirmar/corregir una receta ya leída (eso lo maneja el orquestador
    sobre el estado, no esta tool de nuevo).

    Args:
        imagen_base64: la imagen de la receta, codificada en base64.
    """
    # Import diferido: evita que importar el módulo de la tool (para tests,
    # por ejemplo) dispare la carga de config/LLM real.
    from fitosanitarios.config import get_settings
    from fitosanitarios.llm.client import crear_cliente_llm

    imagen = base64.b64decode(imagen_base64)
    cliente_llm = crear_cliente_llm(get_settings())
    resultado = leer_receta_logica(imagen, cliente_llm)
    return _resumen_para_llm(resultado), resultado
