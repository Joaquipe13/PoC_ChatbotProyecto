"""Cliente HTTP tipado para el vademécum de SENASA.

Endpoints verificados en vivo el 12/09/2026 contra
https://aps2.senasa.gov.ar/adt_api/api (ver DECISIONES.md y DIFICULTADES.md
para el detalle de la verificación y en qué difiere de lo que asumía la skill).
No hay documentación pública ni endpoint de discovery (`/search` devuelve 403);
si SENASA cambia el contrato, este cliente puede romper sin aviso -- por eso
el resto del sistema nunca consulta la API en vivo, solo el snapshot versionado
(ver loader.py).

Los modelos pydantic de acá deliberadamente NO mapean la respuesta completa del
detalle (~50-90 KB por producto, con el objeto `producto` reincrustado muchas
veces por las relaciones embebidas de Spring Data REST): solo declaran los
campos que el resto del pipeline necesita. `extra="ignore"` (default de
pydantic) descarta el resto sin fallar.
"""

from pydantic import BaseModel, ConfigDict, Field, field_validator

USER_AGENT = "TP2-IA-UTN-FRRo/0.1 (proyecto academico fitosanitarios; +https://github.com/)"


class ProductoListado(BaseModel):
    """Un ítem de la respuesta de listado (endpoint publicSearchProductosFormuladosDTO)."""

    model_config = ConfigDict(populate_by_name=True)

    id: int
    numero_inscripcion: str = Field(alias="numeroInscripcion")
    marca: str = Field(default="")
    nombre_firma: str = Field(default="", alias="nombreFirma")
    clase_toxicologica: str | None = Field(default=None, alias="claseToxicologica")
    sustancias_activas: str = Field(default="", alias="sustanciasActivas")

    @field_validator("marca", "nombre_firma", "sustancias_activas", mode="before")
    @classmethod
    def _none_a_vacio(cls, v: str | None) -> str:
        """SENASA manda `null` (no solo ausencia de la clave) en algunos
        productos, p. ej. sustanciasActivas en formulados sin principio
        activo declarado (coadyuvantes). Se normaliza a "" en vez de fallar
        el parseo de todo el listado por un producto con datos incompletos."""
        return v or ""


class PaginaListado(BaseModel):
    productos: list[ProductoListado]
    total_elementos: int
    total_paginas: int
    pagina_actual: int


class ClaseToxicologica(BaseModel):
    """Forma real: objeto {id, claseTox, precaucion, advertencia, color}, no un
    string concatenado como asumía la skill originalmente (ver DECISIONES.md)."""

    model_config = ConfigDict(populate_by_name=True)

    clase_tox: str | None = Field(default=None, alias="claseTox")
    color: str | None = None
    advertencia: str | None = None


class NomencladorNombre(BaseModel):
    descripcion: str


class UnidadMedida(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    sigla: str | None = Field(default=None, alias="siglaEstandarizada")
    descripcion: str | None = None


class PrincipioActivoDetalle(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    nomenclador: NomencladorNombre
    concentracion: float | None = None
    unidad_medida: UnidadMedida | None = Field(default=None, alias="unidadMedida")


class AptitudDetalle(BaseModel):
    nomenclador: NomencladorNombre


class CultivoRef(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    nombre_comun: str = Field(alias="nombreComun")
    nombre_cientifico: str | None = Field(default=None, alias="nombreCientifico")


class AdversidadRef(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    nombre_comun: str = Field(alias="nombreComun")
    nombre_cientifico: str | None = Field(default=None, alias="nombreCientifico")


class AplicacionProducto(BaseModel):
    """Uso registrado estructurado. Poco frecuente: la mayoría de los productos
    no tiene ninguna entrada acá (ver DECISIONES.md, hallazgo de la Fase 2)."""

    model_config = ConfigDict(populate_by_name=True)

    cultivo: CultivoRef | None = None
    adversidad: AdversidadRef | None = None
    dosis: str | None = None
    momento_aplicacion: str | None = Field(default=None, alias="momentoAplicacion")
    volumen_por_aplicacion: str | None = Field(default=None, alias="volumenPorAplicacion")
    periodo_carencia: str | None = Field(default=None, alias="periodoCarencia")


class TipoDocumento(BaseModel):
    extension: str | None = None


class DocumentoProducto(BaseModel):
    """`nombre` distingue el tipo real de documento: 'Marbete' es la etiqueta que
    interesa para dosis; 'HDS' es la hoja de seguridad (no tiene dosis por cultivo).
    Este campo NO estaba en la descripción original de la skill: se descubrió
    verificando productos reales (ver DECISIONES.md)."""

    model_config = ConfigDict(populate_by_name=True)

    nombre: str | None = None
    observaciones: str | None = None
    tipo_documento: TipoDocumento | None = Field(default=None, alias="tipoDocumento")
    contenido: str | None = None  # base64; se separa a disco antes de persistir crudo_api

    @property
    def es_marbete(self) -> bool:
        return (self.nombre or "").strip().lower() == "marbete"


class TipoPresentacion(BaseModel):
    abreviatura: str | None = None
    descripcion: str | None = None


class EstadoProducto(BaseModel):
    descripcion: str | None = None


class DetalleProducto(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    id: int
    numero_inscripcion: str = Field(alias="numeroInscripcion")
    clase_toxicologica: ClaseToxicologica | None = Field(default=None, alias="claseToxicologica")
    toxicidad_abejas: ClaseToxicologica | None = Field(default=None, alias="toxicidadAbejas")
    toxicidad_peces: ClaseToxicologica | None = Field(default=None, alias="toxicidadPeces")
    toxicidad_aves: ClaseToxicologica | None = Field(default=None, alias="toxicidadAves")
    tipo_presentacion: TipoPresentacion | None = Field(default=None, alias="tipoPresentacion")
    estado_producto: EstadoProducto | None = Field(default=None, alias="estadoProducto")
    principios_activos: list[PrincipioActivoDetalle] = Field(
        default_factory=list, alias="principiosActivos"
    )
    productos_aptitudes: list[AptitudDetalle] = Field(
        default_factory=list, alias="productosAptitudes"
    )
    aplicaciones_por_producto: list[AplicacionProducto] = Field(
        default_factory=list, alias="aplicacionesPorProducto"
    )
    producto_documentos: list[DocumentoProducto] = Field(
        default_factory=list, alias="productoDocumentos"
    )


def parsear_pagina_listado(data: dict) -> PaginaListado:
    items_raw = data.get("_embedded", {}).get("productosAgroquimicosFormulados", [])
    productos = [ProductoListado.model_validate(item) for item in items_raw]
    pagina = data["page"]
    return PaginaListado(
        productos=productos,
        total_elementos=pagina["totalElements"],
        total_paginas=pagina["totalPages"],
        pagina_actual=pagina["number"],
    )


class ClienteSenasa:
    """Cliente HTTP delgado. No reintenta ni throttlea: eso es responsabilidad
    del crawler (crawler.py), que es quien conoce la política de reintentos."""

    def __init__(self, base_url: str, user_agent: str = USER_AGENT, timeout: float = 30.0) -> None:
        import httpx

        self._base_url = base_url.rstrip("/")
        self._client = httpx.Client(timeout=timeout, headers={"User-Agent": user_agent})

    def listar_pagina(self, page: int, size: int = 15) -> PaginaListado:
        url = (
            f"{self._base_url}/productosAgroquimicosFormulados/search/"
            "publicSearchProductosFormuladosDTO"
        )
        resp = self._client.get(
            url, params={"page": page, "size": size, "sort": "numeroInscripcion,desc"}
        )
        resp.raise_for_status()
        return parsear_pagina_listado(resp.json())

    def obtener_detalle(self, producto_id: int) -> DetalleProducto:
        producto_url = f"{self._base_url}/productosAgroquimicosFormulados/{producto_id}"
        url = f"{self._base_url}/productosAgroquimicosFormulados/search/publicSearchProducto"
        resp = self._client.get(
            url,
            params={"producto": producto_url, "projection": "productoFormuladoPublicoProjection"},
        )
        resp.raise_for_status()
        return DetalleProducto.model_validate(resp.json())

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "ClienteSenasa":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()
