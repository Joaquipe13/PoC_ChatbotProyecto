"""Crawler del vademécum de SENASA: listado completo + detalle por producto.

Throttling (~SENASA_REQ_POR_SEG), checkpoint reanudable (un id por línea en un
archivo de progreso) y reintentos con backoff ante error transitorio. El
crudo se guarda como JSON Lines (un producto por línea) en vez de PDFs/base64
sueltos: loader.py es quien separa los PDFs a disco al normalizar (ver skill,
"Estrategia a planificar", paso 1).
"""

import base64
import json
import logging
import re
import time
from pathlib import Path

from tenacity import retry, stop_after_attempt, wait_exponential

from fitosanitarios.senasa.cliente import ClienteSenasa, DetalleProducto, ProductoListado

logger = logging.getLogger(__name__)


def crawl_listado_completo(
    cliente: ClienteSenasa, size: int = 100, segundos_entre_requests: float = 1.0
) -> list[ProductoListado]:
    """Trae el listado completo (liviano: sin PDFs, ~7000 items en pocas decenas
    de requests con size=100)."""
    productos: list[ProductoListado] = []
    pagina = cliente.listar_pagina(0, size=size)
    productos.extend(pagina.productos)
    total_paginas = pagina.total_paginas
    logger.info("Listado: %d productos en %d páginas", pagina.total_elementos, total_paginas)
    for numero_pagina in range(1, total_paginas):
        time.sleep(segundos_entre_requests)
        pagina = cliente.listar_pagina(numero_pagina, size=size)
        productos.extend(pagina.productos)
    return productos


class ProgresoCrawler:
    """Checkpoint reanudable: un id de producto completado por línea."""

    def __init__(self, ruta: Path) -> None:
        self._ruta = ruta
        self.ids_completados: set[int] = set()
        if ruta.exists():
            lineas = ruta.read_text(encoding="utf-8").splitlines()
            self.ids_completados = {int(linea) for linea in lineas if linea.strip()}

    def marcar_completado(self, id_producto: int) -> None:
        self.ids_completados.add(id_producto)
        self._ruta.parent.mkdir(parents=True, exist_ok=True)
        with self._ruta.open("a", encoding="utf-8") as f:
            f.write(f"{id_producto}\n")


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
def _obtener_detalle_con_reintentos(cliente: ClienteSenasa, id_producto: int) -> DetalleProducto:
    return cliente.obtener_detalle(id_producto)


_NOMBRE_ARCHIVO_INVALIDO = re.compile(r"[^A-Za-z0-9_-]+")


def _separar_documentos_a_disco(detalle: DetalleProducto, carpeta_documentos: Path) -> None:
    """Saca el base64 de cada productoDocumento a un .pdf en disco y lo
    reemplaza por None en el objeto en memoria, para que el JSON Lines del
    crudo (y el snapshot que se arma después) nunca cargue los PDFs (ver
    skill, "Estrategia a planificar" paso 1, y plandefases.md Fase 2 tarea 5)."""
    if not detalle.producto_documentos:
        return
    carpeta_documentos.mkdir(parents=True, exist_ok=True)
    for indice, doc in enumerate(detalle.producto_documentos):
        if not doc.contenido:
            continue
        nombre = _NOMBRE_ARCHIVO_INVALIDO.sub("-", doc.nombre or "documento")
        extension = (doc.tipo_documento.extension if doc.tipo_documento else "pdf") or "pdf"
        nombre_archivo = f"{detalle.numero_inscripcion}_{indice}_{nombre}.{extension.lower()}"
        ruta = carpeta_documentos / nombre_archivo
        ruta.write_bytes(base64.b64decode(doc.contenido))
        doc.contenido = None


def crawl_detalle(
    cliente: ClienteSenasa,
    ids: list[int],
    ruta_salida: Path,
    ruta_checkpoint: Path,
    carpeta_documentos: Path | None = None,
    segundos_entre_requests: float = 1.0,
) -> list[int]:
    """Descarga el detalle de cada id y lo appendea como JSON Lines crudo,
    separando primero los PDFs de `productoDocumentos` a disco (nunca quedan
    en el JSON). Reanudable: salta los ids ya presentes en el checkpoint.
    Devuelve los ids que fallaron después de los reintentos."""
    progreso = ProgresoCrawler(ruta_checkpoint)
    fallidos: list[int] = []
    ruta_salida.parent.mkdir(parents=True, exist_ok=True)
    carpeta_documentos = carpeta_documentos or ruta_salida.parent / "documentos"

    pendientes = [i for i in ids if i not in progreso.ids_completados]
    logger.info(
        "Detalle: %d ids pedidos, %d ya completados, %d pendientes",
        len(ids), len(ids) - len(pendientes), len(pendientes),
    )

    for id_producto in pendientes:
        try:
            detalle = _obtener_detalle_con_reintentos(cliente, id_producto)
        except Exception:
            logger.warning("Producto %d falló tras reintentos", id_producto, exc_info=True)
            fallidos.append(id_producto)
            continue
        _separar_documentos_a_disco(detalle, carpeta_documentos)
        with ruta_salida.open("a", encoding="utf-8") as f:
            f.write(detalle.model_dump_json() + "\n")
        progreso.marcar_completado(id_producto)
        time.sleep(segundos_entre_requests)

    return fallidos


def guardar_listado_jsonl(productos: list[ProductoListado], ruta: Path) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("w", encoding="utf-8") as f:
        for producto in productos:
            f.write(producto.model_dump_json() + "\n")


def leer_listado_jsonl(ruta: Path) -> list[ProductoListado]:
    productos = []
    with ruta.open(encoding="utf-8") as f:
        for linea in f:
            if linea.strip():
                productos.append(ProductoListado.model_validate(json.loads(linea)))
    return productos


def leer_detalle_jsonl(ruta: Path) -> list[DetalleProducto]:
    detalles = []
    with ruta.open(encoding="utf-8") as f:
        for linea in f:
            if linea.strip():
                detalles.append(DetalleProducto.model_validate(json.loads(linea)))
    return detalles
