"""Contratos y modelos de dominio del agente de recetas fitosanitarios.

Fuente de verdad de los contratos `Cita`, `CampoFaltante`, `ResultadoTool` y
`RespuestaAgente`: skill agente-fitosanitarios, sección "Contratos" (reproducidos
acá tal cual). Los modelos de dominio (`Receta`, `RecetaItem`, `Dictamen`,
`Observacion`) no vienen especificados campo a campo en la skill -- solo se
describe el dominio y las tablas `operacion.*` -- así que su forma exacta es
una decisión de la Fase 1 (ver DECISIONES.md) y puede ajustarse en la Fase 5
al integrar datos reales de SENASA y territorio.
"""

from datetime import date
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field

from fitosanitarios.dominio.motivos import MotivoNoResuelto


class TipoAplicacion(StrEnum):
    TERRESTRE = "terrestre"
    AEREA = "aerea"


class EstadoReceta(StrEnum):
    BORRADOR = "borrador"
    CONFIRMADA = "confirmada"
    EVALUADA = "evaluada"
    CANCELADA = "cancelada"


class RecetaItem(BaseModel):
    """Un producto dentro de una receta, antes o después de resolverlo contra el catálogo."""

    producto_nombre: str
    producto_id: int | None = None
    dosis_declarada: str | None = None  # texto libre tal como lo dice la receta, ej. "2 L/ha"
    dosis_valor: float | None = None
    dosis_unidad: str | None = None
    adversidad: str | None = None


class Receta(BaseModel):
    """Estado de una receta agronómica en curso o evaluada. Corresponde a `operacion.receta`."""

    id: int | None = None
    numero: str | None = None
    cultivo: str | None = None
    lote: str | None = None
    items: list[RecetaItem] = Field(default_factory=list)
    superficie_ha: float | None = None
    tipo_aplicacion: TipoAplicacion | None = None
    ubicacion_lat: float | None = None
    ubicacion_lon: float | None = None
    jurisdiccion_id: str | None = None
    fecha_prevista: date | None = None
    estado: EstadoReceta = EstadoReceta.BORRADOR
    confianza_por_campo: dict[str, float] = Field(default_factory=dict)


class Cita(BaseModel):
    fuente: Literal["normativa", "senasa"]
    jurisdiccion_id: str | None = None
    norma: str | None = None  # "Ordenanza 914/2018"
    articulo: str | None = None  # "8"
    registro_senasa: str | None = None
    documento: str | None = None  # "marbete", "detalle API", nombre del PDF


class Observacion(BaseModel):
    """Un chequeo del dictamen que no cumple."""

    descripcion: str
    citas: list[Cita] = Field(default_factory=list)


class Dictamen(BaseModel):
    resultado: Literal["APTA", "OBSERVADA", "NO_EVALUABLE"]
    observaciones: list[Observacion] = Field(default_factory=list)
    chequeos_no_realizados: list[str] = Field(default_factory=list)
    citas: list[Cita] = Field(default_factory=list)


class CampoFaltante(BaseModel):
    campo: str  # "ubicacion_lote"
    motivo: str
    pregunta_sugerida: str
    tipo_entrada: Literal["texto", "ubicacion", "botones", "lista", "imagen"]
    opciones: list[str] | None = None


class ResultadoTool(BaseModel):
    estado: Literal["ok", "observado", "faltan_datos", "no_resuelto", "error"]
    datos: dict[str, Any] | None = None  # payload tipado por tool (modelo propio serializado)
    faltantes: list[CampoFaltante] = Field(default_factory=list)
    motivo: MotivoNoResuelto | None = None
    citas: list[Cita] = Field(default_factory=list)
    advertencias: list[str] = Field(default_factory=list)
    chequeos_no_realizados: list[str] = Field(default_factory=list)


class RespuestaAgente(BaseModel):  # response_format del agente
    tipo: Literal[
        "confirmacion_receta",
        "dictamen",
        "consulta_producto",
        "consulta_normativa",
        "repregunta",
        "fuera_de_dominio",
        "no_resuelto",
        "ayuda",
        "error",
    ]
    intro: str | None = None  # máximo una línea
    faltantes: list[CampoFaltante] = Field(default_factory=list)  # solo si repregunta sin tools
