"""Extracción multimodal de datos de una receta agronómica desde una foto,
con confianza por campo (ver skill, RF1/RF2 y contrato `Receta`).

El LLM nunca decide solo: acá se convierte su salida en `Receta` + lista de
`CampoFaltante` para los campos con confianza baja o ausentes, que es lo que
el orquestador (Fase 7) va a usar para armar la repregunta o la confirmación
(ver skill, "Reglas de repregunta": "Receta leída de foto: siempre
confirmación (Confirmar / Corregir) antes de evaluar").
"""

import hashlib
import json
import logging
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, Field, ValidationError

from fitosanitarios.dominio.modelos import CampoFaltante, Receta, RecetaItem

logger = logging.getLogger(__name__)

UMBRAL_CONFIANZA_CAMPO = 0.6

_TIPO_ENTRADA_POR_CAMPO = {
    "cultivo": "texto",
    "lote": "texto",
    "adversidad": "texto",
    "tipo_aplicacion": "botones",
    "superficie_ha": "texto",
    "productos": "texto",
}
_OPCIONES_POR_CAMPO: dict[str, list[str]] = {
    "tipo_aplicacion": ["Terrestre", "Aérea"],
}
_PREGUNTA_POR_CAMPO = {
    "cultivo": "¿Qué cultivo es?",
    "lote": "¿Cuál es el número o nombre del lote?",
    "adversidad": "¿Contra qué plaga, maleza o enfermedad es la aplicación?",
    "tipo_aplicacion": "¿La aplicación es terrestre o aérea?",
    "superficie_ha": "¿Cuántas hectáreas tiene el lote?",
    "productos": "¿Qué producto(s) y dosis indica la receta?",
}


class ProductoExtraidoLLM(BaseModel):
    producto_nombre: str
    dosis_declarada: str | None = None
    confianza: float = 0.0


class RecetaExtraidaLLM(BaseModel):
    """Salida cruda del LLM, antes de convertirla a `Receta` + faltantes."""

    legible: bool = True
    numero: str | None = None
    cultivo: str | None = None
    confianza_cultivo: float = 0.0
    lote: str | None = None
    confianza_lote: float = 0.0
    adversidad: str | None = None
    confianza_adversidad: float = 0.0
    productos: list[ProductoExtraidoLLM] = Field(default_factory=list)
    superficie_ha: float | None = None
    confianza_superficie_ha: float = 0.0
    tipo_aplicacion: str | None = None  # "terrestre" | "aerea" | None
    confianza_tipo_aplicacion: float = 0.0


class ClienteLLMMultimodalProtocolo(Protocol):
    def generar_con_imagen(
        self, imagen: bytes, prompt: str, *, system: str | None = None
    ) -> str: ...


PROMPT_SISTEMA_EXTRACCION = (
    "Sos un asistente que lee fotos de recetas agronómicas argentinas (recetas "
    "fitosanitarias firmadas por un ingeniero agrónomo) y extrae sus datos "
    "estructurados. Nunca inventes un dato que no puedas leer con claridad en "
    "la imagen: si un campo no está o no se lee bien, dejalo en null (o la "
    "lista de productos vacía) y poné su confianza en 0.\n\n"
    "Si la imagen no es una receta legible (está borrosa, no es un documento, "
    "etc.), respondé unicamente {\"legible\": false}.\n\n"
    "Si es legible, respondé ÚNICAMENTE un JSON (sin texto alrededor, sin "
    "markdown) con esta forma exacta:\n"
    "{\n"
    '  "legible": true,\n'
    '  "numero": string o null,\n'
    '  "cultivo": string o null, "confianza_cultivo": 0 a 1,\n'
    '  "lote": string o null, "confianza_lote": 0 a 1,\n'
    '  "adversidad": string o null, "confianza_adversidad": 0 a 1,\n'
    '  "productos": [{"producto_nombre": string, "dosis_declarada": string o '
    'null, "confianza": 0 a 1}, ...],\n'
    '  "superficie_ha": numero o null, "confianza_superficie_ha": 0 a 1,\n'
    '  "tipo_aplicacion": "terrestre" | "aerea" | null, '
    '"confianza_tipo_aplicacion": 0 a 1\n'
    "}\n"
    "La confianza es tu propia evaluación de qué tan claro se lee ese campo "
    "específico en la imagen, no una opinión general sobre la receta."
)


class CacheExtraccion(Protocol):
    def get(self, clave: str) -> str | None: ...
    def __setitem__(self, clave: str, valor: str) -> None: ...


class CacheDiscoJSON:
    """Cache en disco, un archivo por clave. Evita re-llamar al LLM para la
    misma imagen (ver skill: "Cachear leer_receta por hash de imagen")."""

    def __init__(self, directorio: Path) -> None:
        self._directorio = directorio
        self._directorio.mkdir(parents=True, exist_ok=True)

    def get(self, clave: str) -> str | None:
        ruta = self._directorio / f"{clave}.json"
        return ruta.read_text(encoding="utf-8") if ruta.exists() else None

    def __setitem__(self, clave: str, valor: str) -> None:
        (self._directorio / f"{clave}.json").write_text(valor, encoding="utf-8")


def _hash_imagen(imagen: bytes) -> str:
    return hashlib.sha256(imagen).hexdigest()


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
        logger.warning("El LLM no devolvió JSON válido para leer_receta")
        return None
    if not isinstance(datos, dict):
        return None
    return datos


def extraer_receta_de_imagen(
    imagen: bytes,
    cliente_llm: ClienteLLMMultimodalProtocolo,
    cache: CacheExtraccion | None = None,
) -> RecetaExtraidaLLM:
    """Llama al LLM (o usa la caché por hash de imagen) y devuelve la
    extracción cruda, sin convertir todavía a `Receta`/`CampoFaltante`."""
    clave = _hash_imagen(imagen)
    if cache is not None:
        cacheado = cache.get(clave)
        if cacheado is not None:
            datos = _parsear_json(cacheado)
            if datos is not None:
                return _validar_o_no_legible(datos)

    respuesta = cliente_llm.generar_con_imagen(imagen, "", system=PROMPT_SISTEMA_EXTRACCION)
    if cache is not None:
        cache[clave] = respuesta

    datos = _parsear_json(respuesta)
    if datos is None:
        return RecetaExtraidaLLM(legible=False)
    return _validar_o_no_legible(datos)


def _validar_o_no_legible(datos: dict) -> RecetaExtraidaLLM:
    try:
        return RecetaExtraidaLLM.model_validate(datos)
    except ValidationError:
        logger.warning("Extracción con forma inválida, se trata como no legible: %r", datos)
        return RecetaExtraidaLLM(legible=False)


def convertir_a_receta_y_faltantes(
    extraccion: RecetaExtraidaLLM, umbral: float = UMBRAL_CONFIANZA_CAMPO
) -> tuple[Receta, list[CampoFaltante]]:
    """Separa lo que se leyó con confianza suficiente (va a la `Receta`) de lo
    que no (va a `CampoFaltante`, para que el orquestador repregunte)."""
    faltantes: list[CampoFaltante] = []
    confianza_por_campo: dict[str, float] = {}

    def _campo_o_faltante(nombre: str, valor):
        confianza = getattr(extraccion, f"confianza_{nombre}", 0.0)
        confianza_por_campo[nombre] = confianza
        if valor is None or confianza < umbral:
            faltantes.append(
                CampoFaltante(
                    campo=nombre,
                    motivo="no se pudo leer con confianza suficiente en la imagen",
                    pregunta_sugerida=_PREGUNTA_POR_CAMPO[nombre],
                    tipo_entrada=_TIPO_ENTRADA_POR_CAMPO[nombre],
                    opciones=_OPCIONES_POR_CAMPO.get(nombre),
                )
            )
            return None
        return valor

    cultivo = _campo_o_faltante("cultivo", extraccion.cultivo)
    lote = _campo_o_faltante("lote", extraccion.lote)
    adversidad = _campo_o_faltante("adversidad", extraccion.adversidad)
    superficie_ha = _campo_o_faltante("superficie_ha", extraccion.superficie_ha)
    tipo_aplicacion_raw = _campo_o_faltante("tipo_aplicacion", extraccion.tipo_aplicacion)

    items = [
        RecetaItem(producto_nombre=p.producto_nombre, dosis_declarada=p.dosis_declarada)
        for p in extraccion.productos
        if p.confianza >= umbral
    ]
    if not items:
        confianza_por_campo["productos"] = 0.0
        faltantes.append(
            CampoFaltante(
                campo="productos",
                motivo="no se pudo leer ningún producto con confianza suficiente",
                pregunta_sugerida=_PREGUNTA_POR_CAMPO["productos"],
                tipo_entrada=_TIPO_ENTRADA_POR_CAMPO["productos"],
            )
        )
    else:
        confianza_por_campo["productos"] = min(p.confianza for p in extraccion.productos)

    receta = Receta(
        numero=extraccion.numero,
        cultivo=cultivo,
        lote=lote,
        adversidad=adversidad,
        items=items,
        superficie_ha=superficie_ha,
        tipo_aplicacion=tipo_aplicacion_raw,
        confianza_por_campo=confianza_por_campo,
    )
    return receta, faltantes
