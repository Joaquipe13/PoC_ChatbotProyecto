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
    """Un producto dentro de una receta, antes o después de resolverlo contra el catálogo.

    `principio_activo` y `clase_toxicologica`: lo que dice la receta en papel
    (no lo que figura en SENASA -- eso lo trae la tool `validar_producto_registro`
    aparte, y ambos pueden compararse más adelante). `adversidad` es la plaga/
    maleza/enfermedad de ESTE producto puntual (campo opcional del formulario:
    ver `Receta.adversidad` para la de toda la receta)."""

    producto_nombre: str
    producto_id: int | None = None
    dosis_declarada: str | None = None  # texto libre tal como lo dice la receta, ej. "2 L/ha"
    dosis_valor: float | None = None
    dosis_unidad: str | None = None
    adversidad: str | None = None
    principio_activo: str | None = None
    clase_toxicologica: str | None = None


class Receta(BaseModel):
    """Estado de una receta agronómica en curso o evaluada. Corresponde a `operacion.receta`.

    Campos agregados (12/09/2026, ver DECISIONES.md) para reflejar la receta
    agronómica real, sin datos personales/sensibles (productor, ingeniero
    agrónomo, matrícula, receta de venta quedan fuera de este proyecto):
    `caudal`, `ubic_poblado`, `condiciones`, `restricciones`, `observaciones`,
    `fecha_emision`, `validez_dias`. Son descriptivos -- no alimentan ningún
    chequeo legal (eso lo siguen haciendo cultivo/lote/superficie/producto/
    dosis/tipo_aplicacion) -- así que `leer_receta` nunca repregunta por
    ellos: si no se leen, quedan en `None` y se muestran como "no figura" en
    la confirmación, sin bloquear."""

    id: int | None = None
    numero: str | None = None  # número de receta
    cultivo: str | None = None
    lote: str | None = None
    adversidad: str | None = None  # plaga/maleza/enfermedad general de la receta
    items: list[RecetaItem] = Field(default_factory=list)
    superficie_ha: float | None = None
    tipo_aplicacion: TipoAplicacion | None = None
    caudal: str | None = None  # texto libre, ej. "100 L/ha"
    localidad: str | None = None  # localidad/municipio/comuna donde se aplica
    ubic_poblado: str | None = None  # ubicación del lote respecto de zonas pobladas
    condiciones: str | None = None  # condiciones ambientales al momento de aplicar
    restricciones: str | None = None  # restricciones de uso indicadas en la receta
    observaciones: str | None = None
    fecha_emision: date | None = None
    validez_dias: int | None = None
    ubicacion_lat: float | None = None
    ubicacion_lon: float | None = None
    jurisdiccion_id: str | None = None
    fecha_prevista: date | None = None
    estado: EstadoReceta = EstadoReceta.BORRADOR
    confianza_por_campo: dict[str, float] = Field(default_factory=dict)


class Cita(BaseModel):
    fuente: Literal["normativa", "senasa"]
    jurisdiccion_id: str | None = None
    norma: str | None = None  # "Ordenanza 841/2010"
    articulo: str | None = None  # "8"
    registro_senasa: str | None = None
    documento: str | None = None  # "marbete", "detalle API", nombre del PDF


class Observacion(BaseModel):
    """Un chequeo del dictamen que no cumple."""

    descripcion: str
    citas: list[Cita] = Field(default_factory=list)


class DistanciaMinima(BaseModel):
    """Distancia mínima que fija la normativa de la localidad para un tipo de zona."""

    tipo_zona: str  # "zona_urbana", "escuela", "curso_agua", ...
    distancia_min_m: float
    norma_limitante: Cita | None = None  # la regla que fija ese mínimo (la más restrictiva)
    # Sin reglas.csv el mínimo se leyó del texto de la norma: hay que verificarlo.
    extraida_de_pdf: bool = False
    citas: list[Cita] = Field(default_factory=list)  # todas las reglas que aplican
    advertencias: list[str] = Field(default_factory=list)


class CondicionesAplicacion(BaseModel):
    """Qué exige la normativa para esta aplicación, sin comparar contra la
    ubicación del lote: solo informa banda y distancias mínimas según la
    localidad, el tipo de aplicación y las bandas de los productos."""

    localidad: str
    tipo_aplicacion: str
    banda: str | None = None  # la más peligrosa entre los productos de la aplicación
    banda_color: str | None = None
    productos_por_banda: dict[str, str | None] = Field(default_factory=dict)
    # Sin su banda, la de la aplicación podría ser más restrictiva de lo que se informa.
    productos_sin_banda: list[str] = Field(default_factory=list)
    # No hay ordenanzas de la localidad: rige la normativa provincial (y se aclara).
    sin_normativa_municipal: bool = False
    distancias_minimas: list[DistanciaMinima] = Field(default_factory=list)
    advertencias: list[str] = Field(default_factory=list)


class Dictamen(BaseModel):
    resultado: Literal["APTA", "OBSERVADA", "NO_EVALUABLE"]
    observaciones: list[Observacion] = Field(default_factory=list)
    chequeos_no_realizados: list[str] = Field(default_factory=list)
    citas: list[Cita] = Field(default_factory=list)
    condiciones: CondicionesAplicacion | None = None


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
        # Fase 9 (extensiones RF6/RF7/RF9, ver DECISIONES.md):
        "consulta_vehiculo",
        "evento_registrado",
        "agenda",
        # Seguimiento del dictamen: banda de cada producto y agendado.
        "detalle_bandas",
        "agendar_aplicacion",
        # Consultas de normativa sin LLM en el texto: artículo por número y
        # limitaciones de una localidad.
        "consulta_articulo",
        "limitaciones",
        # RAG de marbetes de SENASA (`consultar_marbete`).
        "consulta_marbete",
    ]
    faltantes: list[CampoFaltante] = Field(default_factory=list)  # solo si repregunta sin tools
