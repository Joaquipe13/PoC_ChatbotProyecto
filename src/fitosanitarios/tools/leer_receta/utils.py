"""Auxiliares de `leer_receta`: extracción multimodal de datos de una receta
agronómica desde una foto, con confianza por campo (ver skill, RF1/RF2 y contrato
`Receta`). El prompt de extracción está en `prompts.py` y las preguntas de
repregunta en `mensajes.py`.

El LLM nunca decide solo: acá se convierte su salida en `Receta` + lista de
`CampoFaltante` para los campos con confianza baja o ausentes, que es lo que
el orquestador (Fase 7) va a usar para armar la repregunta o la confirmación
(ver skill, "Reglas de repregunta": "Receta leída de foto: siempre
confirmación (Confirmar / Corregir) antes de evaluar").
"""

import hashlib
import json
import logging
from datetime import date
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, Field, ValidationError

from fitosanitarios.dominio.modelos import CampoFaltante, Receta, RecetaItem
from fitosanitarios.tools.leer_receta import mensajes
from fitosanitarios.tools.leer_receta.prompts import PROMPT_SISTEMA_EXTRACCION

logger = logging.getLogger(__name__)

UMBRAL_CONFIANZA_CAMPO = 0.6

class ProductoExtraidoLLM(BaseModel):
    producto_nombre: str
    dosis_declarada: str | None = None
    confianza: float = 0.0
    adversidad: str | None = None  # plaga/maleza/enfermedad de este producto puntual
    principio_activo: str | None = None
    clase_toxicologica: str | None = None


class RecetaExtraidaLLM(BaseModel):
    """Salida cruda del LLM, antes de convertirla a `Receta` + faltantes.

    Solo los campos que alimentan un chequeo legal (`cultivo`, `lote`,
    `superficie_ha`, `productos`) llevan confianza propia y pueden terminar
    en `faltantes`. El resto son descriptivos de la receta real (ver
    `Receta`, DECISIONES.md): se toman tal cual los lea el LLM -- que ya
    tiene la instrucción de dejarlos en `null` si no los puede leer con
    claridad, ver `PROMPT_SISTEMA_EXTRACCION` -- sin gatillar una repregunta
    si faltan."""

    legible: bool = True
    numero: str | None = None
    cultivo: str | None = None
    confianza_cultivo: float = 0.0
    lote: str | None = None
    confianza_lote: float = 0.0
    adversidad: str | None = None  # plaga/maleza/enfermedad general, opcional
    productos: list[ProductoExtraidoLLM] = Field(default_factory=list)
    superficie_ha: float | None = None
    confianza_superficie_ha: float = 0.0
    tipo_aplicacion: str | None = None  # "terrestre" | "aerea" | None
    caudal: str | None = None
    localidad: str | None = None  # localidad/municipio/comuna donde se aplica el lote
    ubic_poblado: str | None = None
    condiciones: str | None = None
    restricciones: str | None = None
    observaciones: str | None = None
    fecha_emision: str | None = None  # "AAAA-MM-DD"; se parsea al convertir
    validez_dias: int | None = None


class ClienteLLMMultimodalProtocolo(Protocol):
    def generar_con_imagen(
        self, imagen: bytes, prompt: str, *, system: str | None = None
    ) -> str: ...


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


def _fecha_o_none(texto: str | None):
    if not texto:
        return None
    try:
        return date.fromisoformat(texto)
    except ValueError:
        logger.warning("fecha_emision no parseable, se descarta: %r", texto)
        return None


def convertir_a_receta_y_faltantes(
    extraccion: RecetaExtraidaLLM, umbral: float = UMBRAL_CONFIANZA_CAMPO
) -> tuple[Receta, list[CampoFaltante]]:
    """Separa lo que se leyó con confianza suficiente (va a la `Receta`) de lo
    que no. Solo `cultivo`, `lote`, `superficie_ha` y `productos` -- los que
    alimentan un chequeo legal más adelante -- generan `CampoFaltante` (para
    que el orquestador pueda repreguntar). El resto de los campos (ver
    `Receta`, DECISIONES.md) son descriptivos: si el LLM no los pudo leer
    quedan en `None` sin bloquear nada -- la receta se arma igual con lo que
    sí se pudo leer, y el hueco se ve en la confirmación ("no figura")."""
    faltantes: list[CampoFaltante] = []
    confianza_por_campo: dict[str, float] = {}

    def _campo_o_faltante(nombre: str, valor):
        confianza = getattr(extraccion, f"confianza_{nombre}", 0.0)
        confianza_por_campo[nombre] = confianza
        if valor is None or confianza < umbral:
            faltantes.append(
                CampoFaltante(
                    campo=nombre,
                    motivo=mensajes.MOTIVO_CAMPO_ILEGIBLE,
                    pregunta_sugerida=mensajes.PREGUNTA_POR_CAMPO[nombre],
                    tipo_entrada="texto",
                )
            )
            return None
        return valor

    cultivo = _campo_o_faltante("cultivo", extraccion.cultivo)
    lote = _campo_o_faltante("lote", extraccion.lote)
    superficie_ha = _campo_o_faltante("superficie_ha", extraccion.superficie_ha)

    items = [
        RecetaItem(
            producto_nombre=p.producto_nombre,
            dosis_declarada=p.dosis_declarada,
            adversidad=p.adversidad,
            principio_activo=p.principio_activo,
            clase_toxicologica=p.clase_toxicologica,
        )
        for p in extraccion.productos
        if p.confianza >= umbral
    ]
    if not items:
        confianza_por_campo["productos"] = 0.0
        faltantes.append(
            CampoFaltante(
                campo="productos",
                motivo=mensajes.MOTIVO_SIN_PRODUCTOS,
                pregunta_sugerida=mensajes.PREGUNTA_POR_CAMPO["productos"],
                tipo_entrada="texto",
            )
        )
    else:
        confianza_por_campo["productos"] = min(p.confianza for p in extraccion.productos)

    receta = Receta(
        numero=extraccion.numero,
        cultivo=cultivo,
        lote=lote,
        adversidad=extraccion.adversidad,
        items=items,
        superficie_ha=superficie_ha,
        tipo_aplicacion=extraccion.tipo_aplicacion,
        caudal=extraccion.caudal,
        localidad=extraccion.localidad,
        ubic_poblado=extraccion.ubic_poblado,
        condiciones=extraccion.condiciones,
        restricciones=extraccion.restricciones,
        observaciones=extraccion.observaciones,
        fecha_emision=_fecha_o_none(extraccion.fecha_emision),
        validez_dias=extraccion.validez_dias,
        confianza_por_campo=confianza_por_campo,
    )
    return receta, faltantes
