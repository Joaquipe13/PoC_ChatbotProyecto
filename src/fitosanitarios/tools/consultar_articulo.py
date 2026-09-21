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
from fitosanitarios.servicios.localidad import Ubicacion
from fitosanitarios.servicios.normas import (
    filtrar_normas,
    limpiar_texto_articulo,
    norma_legible,
    numero_de_articulo,
)
from fitosanitarios.tools._localidad import resolver_ubicacion_o_cortar


class ConsultarArticuloArgs(BaseModel):
    numero_articulo: str
    norma: str | None = None
    localidad: str | None = None
    provincia: str | None = None  # solo si la localidad no está cargada


def _etiqueta(archivo: str, jurisdiccion_id: str) -> str:
    return f"{norma_legible(archivo)} ({jurisdiccion_id})"


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
                    campo="numero_articulo",
                    motivo="no se indicó qué número de artículo consultar",
                    pregunta_sugerida="¿Qué número de artículo querés ver?",
                    tipo_entrada="texto",
                )
            ],
        )

    ubicacion, corte = _ubicacion(conn, args)
    if corte is not None:
        return corte
    con_localidad = bool(args.localidad and args.localidad.strip())
    advertencias: list[str] = []
    if con_localidad and not ubicacion.con_normativa_municipal:
        advertencias.append(
            f"No se cuenta con la normativa municipal de {ubicacion.nombre}: se busca en la "
            "normativa provincial y nacional"
        )
    if not con_localidad:
        advertencias.append(
            "Busqué en la normativa provincial y nacional. Si es de una ordenanza, decime la "
            "localidad"
        )

    filas = articulos_por_numero(conn, numero, ubicacion.localidad_id, ubicacion.provincia_id)
    if args.norma and args.norma.strip():
        normas = normas_de_alcance(conn, ubicacion.localidad_id, ubicacion.provincia_id)
        elegidas = filtrar_normas([n["archivo"] for n in normas], args.norma)
        if not elegidas:
            cargadas = ", ".join(_etiqueta(n["archivo"], n["jurisdiccion_id"]) for n in normas)
            return ResultadoTool(
                estado="no_resuelto", motivo=MotivoNoResuelto.ARTICULO_NO_ENCONTRADO,
                advertencias=[
                    f"No encontré la norma '{args.norma.strip()}'. Las cargadas son: {cargadas}"
                ],
            )
        filas = [f for f in filas if f["archivo"] in elegidas]

    if not filas:
        return ResultadoTool(
            estado="no_resuelto", motivo=MotivoNoResuelto.ARTICULO_NO_ENCONTRADO,
            advertencias=[f"No hay un artículo {numero} en la normativa consultada"] + advertencias,
        )

    archivos = list(dict.fromkeys(f["archivo"] for f in filas))
    if len(archivos) > 1:
        etiquetas = [
            _etiqueta(a, next(f["jurisdiccion_id"] for f in filas if f["archivo"] == a))
            for a in archivos
        ]
        return ResultadoTool(
            estado="faltan_datos",
            faltantes=[
                CampoFaltante(
                    campo="norma",
                    motivo=f"el artículo {numero} figura en más de una norma",
                    pregunta_sugerida=f"El artículo {numero} está en varias normas. ¿De cuál?",
                    tipo_entrada="lista", opciones=etiquetas,
                )
            ],
        )

    archivo = archivos[0]
    jurisdiccion_id = filas[0]["jurisdiccion_id"]
    if any(f["requiere_revision"] for f in filas):
        advertencias.append(
            "El texto viene de un documento escaneado y puede tener errores de lectura"
        )
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
    response_format="content_and_artifact",
)
def consultar_articulo(
    numero_articulo: str,
    norma: str | None = None,
    localidad: str | None = None,
    provincia: str | None = None,
) -> tuple[str, ResultadoTool]:
    """Muestra el texto literal de un artículo de la normativa, buscándolo por su
    número. Usar cuando piden ver o leer un artículo puntual: "¿qué dice el
    artículo 33?", "q dice el art 6 de la ordenanza 841", "leeme el 51 de la ley
    11273", "mostrame el articulo 34". No usar para preguntas de contenido sin número
    ("¿a cuántos metros de una escuela puedo aplicar?": `responder_consulta_normativa`)
    ni para listar las limitaciones (`listar_limitaciones`).

    Args:
        numero_articulo: el número que pidió, solo el número o con "bis" ("33", "5 bis").
        norma: la norma a la que se refiere, tal como la nombró ("ley 11273",
            "ordenanza 841/2010"), si la nombró. Si el número está en varias normas y
            no la nombró, la tool pregunta cuál.
        localidad: localidad de la consulta, si la dijo o si hay una receta en curso.
            Sin localidad se busca en la normativa provincial y nacional.
        provincia: solo si la tool la pidió porque la localidad no está cargada.
    """
    from fitosanitarios.tools._recursos import con_conexion

    args = ConsultarArticuloArgs(
        numero_articulo=numero_articulo, norma=norma, localidad=localidad, provincia=provincia
    )
    resultado = con_conexion(lambda conn: consultar_articulo_logica(args, conn))
    return f"consultar_articulo: estado={resultado.estado}", resultado
