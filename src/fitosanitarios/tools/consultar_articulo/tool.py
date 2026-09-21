"""Tool `consultar_articulo`: el texto de un artículo, buscado por número, sin
que ningún LLM lo reescriba ("¿qué dice el artículo 33?"). A diferencia de
`responder_consulta_normativa` (búsqueda por similitud + respuesta redactada),
acá la búsqueda es exacta y el texto se muestra literal.
"""

from langchain_core.tools import tool
from pydantic import BaseModel

from fitosanitarios.datos.retrievers.territorio import (
    articulos_por_numero,
    listar_provincias,
    normas_de_alcance,
)
from fitosanitarios.dominio.modelos import CampoFaltante, Cita, ResultadoTool
from fitosanitarios.dominio.motivos import MotivoNoResuelto
from fitosanitarios.servicios.formato import norma_legible
from fitosanitarios.servicios.localidad import Ubicacion
from fitosanitarios.servicios.ubicacion import resolver_ubicacion_o_cortar
from fitosanitarios.tools.consultar_articulo import mensajes
from fitosanitarios.tools.consultar_articulo.prompts import DESCRIPCION
from fitosanitarios.tools.consultar_articulo.utils import (
    filtrar_normas,
    limpiar_texto_articulo,
    numero_de_articulo,
)


class ConsultarArticuloArgs(BaseModel):
    numero_articulo: str
    norma: str | None = None
    localidad: str | None = None
    provincia: str | None = None  # solo si la localidad no está cargada


def _ubicacion(conn, args: ConsultarArticuloArgs) -> tuple[Ubicacion | None, ResultadoTool | None]:
    """Sin localidad se busca en la normativa provincial y nacional (el servicio
    opera en una sola provincia); si hubiera varias, se pregunta la localidad."""
    if not args.localidad or not args.localidad.strip():
        provincias = listar_provincias(conn)
        if len(provincias) == 1:
            p = provincias[0]
            return Ubicacion(nombre=p.nombre, provincia_id=p.provincia_id), None
    return resolver_ubicacion_o_cortar(conn, args.localidad, args.provincia)


def consultar_articulo_logica(args: ConsultarArticuloArgs, conn) -> ResultadoTool:
    numero = numero_de_articulo(args.numero_articulo)
    if numero is None:
        return ResultadoTool(
            estado="faltan_datos",
            faltantes=[
                CampoFaltante(
                    campo="numero_articulo", motivo=mensajes.MOTIVO_SIN_NUMERO,
                    pregunta_sugerida=mensajes.PREGUNTA_NUMERO, tipo_entrada="texto",
                )
            ],
        )

    ubicacion, corte = _ubicacion(conn, args)
    if corte is not None:
        return corte
    con_localidad = bool(args.localidad and args.localidad.strip())
    advertencias: list[str] = []
    if con_localidad and not ubicacion.con_normativa_municipal:
        advertencias.append(mensajes.advertencia_sin_normativa_municipal(ubicacion.nombre))
    if not con_localidad:
        advertencias.append(mensajes.ADVERTENCIA_SIN_LOCALIDAD)

    filas = articulos_por_numero(conn, numero, ubicacion.localidad_id, ubicacion.provincia_id)
    if args.norma and args.norma.strip():
        normas = normas_de_alcance(conn, ubicacion.localidad_id, ubicacion.provincia_id)
        elegidas = filtrar_normas([n["archivo"] for n in normas], args.norma)
        if not elegidas:
            cargadas = ", ".join(
                mensajes.etiqueta_norma(n["archivo"], n["jurisdiccion_id"]) for n in normas
            )
            return ResultadoTool(
                estado="no_resuelto", motivo=MotivoNoResuelto.ARTICULO_NO_ENCONTRADO,
                advertencias=[
                    mensajes.advertencia_norma_no_encontrada(args.norma.strip(), cargadas)
                ],
            )
        filas = [f for f in filas if f["archivo"] in elegidas]

    if not filas:
        return ResultadoTool(
            estado="no_resuelto", motivo=MotivoNoResuelto.ARTICULO_NO_ENCONTRADO,
            advertencias=[mensajes.advertencia_articulo_no_encontrado(numero)] + advertencias,
        )

    archivos = list(dict.fromkeys(f["archivo"] for f in filas))
    if len(archivos) > 1:
        jurisdiccion_de = {f["archivo"]: f["jurisdiccion_id"] for f in filas}
        etiquetas = [mensajes.etiqueta_norma(a, jurisdiccion_de[a]) for a in archivos]
        return ResultadoTool(
            estado="faltan_datos",
            faltantes=[
                CampoFaltante(
                    campo="norma", motivo=mensajes.motivo_numero_en_varias_normas(numero),
                    pregunta_sugerida=mensajes.pregunta_cual_norma(numero),
                    tipo_entrada="lista", opciones=etiquetas,
                )
            ],
        )

    archivo = archivos[0]
    jurisdiccion_id = filas[0]["jurisdiccion_id"]
    if any(f["requiere_revision"] for f in filas):
        advertencias.append(mensajes.ADVERTENCIA_OCR)
    return ResultadoTool(
        estado="ok",
        datos={
            "numero": numero, "norma": archivo, "norma_legible": norma_legible(archivo),
            "jurisdiccion_id": jurisdiccion_id,
            # Más de una parte si el PDF trae varios textos con el mismo número.
            "partes": [
                {"texto": limpiar_texto_articulo(f["texto"]), "pagina": f["pagina"]}
                for f in filas
            ],
        },
        citas=[Cita(fuente="normativa", jurisdiccion_id=jurisdiccion_id, norma=archivo,
                    articulo=numero)],
        advertencias=advertencias,
    )


@tool(
    "consultar_articulo",
    args_schema=ConsultarArticuloArgs,
    description=DESCRIPCION,
    response_format="content_and_artifact",
)
def consultar_articulo(
    numero_articulo: str,
    norma: str | None = None,
    localidad: str | None = None,
    provincia: str | None = None,
) -> tuple[str, ResultadoTool]:
    from fitosanitarios.servicios.recursos import con_conexion

    args = ConsultarArticuloArgs(
        numero_articulo=numero_articulo, norma=norma, localidad=localidad, provincia=provincia
    )
    resultado = con_conexion(lambda conn: consultar_articulo_logica(args, conn))
    return mensajes.resumen_para_llm(resultado.estado), resultado
