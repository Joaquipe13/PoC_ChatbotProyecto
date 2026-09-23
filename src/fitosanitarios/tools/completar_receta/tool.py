"""Tool `completar_receta`: los datos que da el operario sobre la receta leída de la
foto (los que faltaban, o una corrección). Toma la última receta de la conversación
(`servicios/receta.py::ultima_receta`), le aplica lo que dijo el operario y vuelve a
mostrarla: con lo que todavía falte preguntado, o completa para confirmar.

La receta sale del artifact de la tool anterior, no de lo que el LLM recuerde: así no
puede cambiar en el camino un dato que el operario no tocó."""

import unicodedata

from langchain.tools import ToolRuntime
from langchain_core.tools import tool
from pydantic import BaseModel

from fitosanitarios.dominio.modelos import Receta, ResultadoTool
from fitosanitarios.servicios.receta import (
    es_sin_dato,
    faltantes_de_receta,
    normalizar_tipo_aplicacion,
    ultima_receta,
)
from fitosanitarios.tools.completar_receta import mensajes
from fitosanitarios.tools.completar_receta.prompts import DESCRIPCION


class DosisDeProducto(BaseModel):
    producto: str | None = None  # el nombre, si lo dijo; sin él, el producto sin dosis
    dosis: str


class CompletarRecetaArgs(BaseModel):
    cultivo: str | None = None
    lote: str | None = None
    localidad: str | None = None
    tipo_aplicacion: str | None = None
    adversidad: str | None = None
    superficie_ha: float | None = None
    dosis: list[DosisDeProducto] = []


def _clave(texto: str) -> str:
    sin_tildes = "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )
    return " ".join(sin_tildes.lower().split())


def _item_de(items: list[dict], producto: str | None) -> dict | None:
    """El producto al que va una dosis: el que nombró (por nombre contenido uno en el
    otro); si no nombró ninguno, el único sin dosis, o el único de la receta."""
    if producto:
        buscado = _clave(producto)
        coinciden = [
            i for i in items
            if buscado in _clave(i["producto_nombre"]) or _clave(i["producto_nombre"]) in buscado
        ]
        return coinciden[0] if len(coinciden) == 1 else None
    sin_dosis = [i for i in items if es_sin_dato(i.get("dosis_declarada"))]
    if len(sin_dosis) == 1:
        return sin_dosis[0]
    return items[0] if len(items) == 1 else None


def completar_receta_logica(args: CompletarRecetaArgs, receta_previa: dict | None) -> ResultadoTool:
    if receta_previa is None:
        return ResultadoTool(estado="faltan_datos", faltantes=[mensajes.faltante_foto()])

    datos = {**receta_previa, "items": [dict(i) for i in receta_previa.get("items", [])]}
    for campo in ("cultivo", "lote", "localidad", "adversidad"):
        valor = getattr(args, campo)
        if not es_sin_dato(valor):
            datos[campo] = valor.strip()
    tipo = normalizar_tipo_aplicacion(args.tipo_aplicacion)
    if tipo:
        datos["tipo_aplicacion"] = tipo
    if args.superficie_ha is not None:
        datos["superficie_ha"] = args.superficie_ha

    advertencias = []
    for d in args.dosis:
        item = _item_de(datos["items"], d.producto)
        if item is None:
            advertencias.append(mensajes.aviso_producto_no_encontrado(d.producto or d.dosis))
        elif not es_sin_dato(d.dosis):
            item["dosis_declarada"] = d.dosis.strip()

    receta = Receta.model_validate(datos).model_dump(mode="json")
    faltantes = faltantes_de_receta(receta)
    return ResultadoTool(
        estado="faltan_datos" if faltantes else "ok",
        datos=receta, faltantes=faltantes, advertencias=advertencias,
    )


@tool(
    "completar_receta",
    args_schema=CompletarRecetaArgs,
    description=DESCRIPCION,
    response_format="content_and_artifact",
    return_direct=True,  # ver `orquestador/respuesta_directa.py`
)
def completar_receta(
    runtime: ToolRuntime,
    cultivo: str | None = None,
    lote: str | None = None,
    localidad: str | None = None,
    tipo_aplicacion: str | None = None,
    adversidad: str | None = None,
    superficie_ha: float | None = None,
    dosis: list[DosisDeProducto] | None = None,
) -> tuple[str, ResultadoTool]:
    args = CompletarRecetaArgs(
        cultivo=cultivo, lote=lote, localidad=localidad, tipo_aplicacion=tipo_aplicacion,
        adversidad=adversidad, superficie_ha=superficie_ha, dosis=dosis or [],
    )
    resultado = completar_receta_logica(
        args, ultima_receta(runtime.state.get("messages", []))
    )
    return mensajes.resumen_para_llm(resultado), resultado
