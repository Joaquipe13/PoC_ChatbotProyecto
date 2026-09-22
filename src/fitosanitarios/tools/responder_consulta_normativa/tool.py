"""Tool `responder_consulta_normativa`: responde preguntas sobre normativa
de aplicación citando artículos verificados (ver skill, tabla de tools RAG)."""

from langchain_core.tools import tool
from pydantic import BaseModel

from fitosanitarios.datos.retrievers.territorio import (
    articulos_por_similitud,
    listar_jurisdicciones_cargadas,
)
from fitosanitarios.dominio.modelos import CampoFaltante, ResultadoTool
from fitosanitarios.dominio.motivos import MotivoNoResuelto
from fitosanitarios.servicios.ubicacion import resolver_ubicacion_o_cortar
from fitosanitarios.tools.responder_consulta_normativa import mensajes
from fitosanitarios.tools.responder_consulta_normativa.prompts import DESCRIPCION
from fitosanitarios.tools.responder_consulta_normativa.utils import (
    FragmentoNormativa,
    filtrar_por_umbral,
    responder_con_fragmentos,
)


class ResponderConsultaNormativaArgs(BaseModel):
    pregunta: str
    jurisdiccion_id: str | None = None
    provincia: str | None = None  # solo si la localidad no está cargada
    tipo_aplicacion: str | None = None
    tipo_zona: str | None = None


def responder_consulta_normativa_logica(
    args: ResponderConsultaNormativaArgs,
    conn,
    modelo_embeddings,
    cliente_llm,
    umbral_similitud: float,
) -> ResultadoTool:
    if args.jurisdiccion_id is None:
        jurisdicciones = listar_jurisdicciones_cargadas(conn)
        return ResultadoTool(
            estado="faltan_datos",
            faltantes=[
                CampoFaltante(
                    campo="jurisdiccion_id", motivo=mensajes.MOTIVO_SIN_LOCALIDAD,
                    pregunta_sugerida=mensajes.PREGUNTA_LOCALIDAD,
                    tipo_entrada="lista",
                    opciones=jurisdicciones,
                )
            ],
        )

    ubicacion, corte = resolver_ubicacion_o_cortar(conn, args.jurisdiccion_id, args.provincia)
    if corte is not None:
        return corte
    # Sin normativa municipal (localidad sin ordenanzas cargadas, o no cargada) la
    # respuesta se basa en la provincial y nacional: hay que decirlo.
    aclaracion = (
        []
        if ubicacion.con_normativa_municipal
        else [mensajes.aclaracion_sin_normativa_municipal(ubicacion.nombre)]
    )

    embedding_pregunta = modelo_embeddings.encode(args.pregunta).tolist()
    filas = articulos_por_similitud(
        conn, embedding_pregunta, ubicacion.localidad_id, ubicacion.provincia_id, top_k=8
    )
    fragmentos = [
        FragmentoNormativa(
            articulo_id=f["id"], numero=f["numero"], texto=f["texto"],
            norma=f["archivo"], ambito=f["ambito"],
            jurisdiccion_id=f["jurisdiccion_id"], score=f["score"],
        )
        for f in filas
    ]
    relevantes = filtrar_por_umbral(fragmentos, umbral_similitud)
    if not relevantes:
        return ResultadoTool(
            estado="no_resuelto", motivo=MotivoNoResuelto.NORMATIVA_SIN_RESPALDO,
            advertencias=aclaracion,
        )

    respuesta = responder_con_fragmentos(args.pregunta, relevantes, cliente_llm)
    if not respuesta.citas:
        # El LLM no pudo anclar ninguna cita verificable a los fragmentos
        # recuperados: no se muestra un veredicto sin fuente citable.
        return ResultadoTool(
            estado="no_resuelto", motivo=MotivoNoResuelto.NORMATIVA_SIN_RESPALDO,
            advertencias=aclaracion + respuesta.advertencias,
        )

    return ResultadoTool(
        estado="ok",
        datos={
            "veredicto": respuesta.veredicto, "regla": respuesta.regla,
            "sin_normativa_municipal": not ubicacion.con_normativa_municipal,
        },
        citas=respuesta.citas,
        advertencias=aclaracion + respuesta.advertencias,
    )


@tool(
    "responder_consulta_normativa",
    args_schema=ResponderConsultaNormativaArgs,
    description=DESCRIPCION,
    response_format="content_and_artifact",
    return_direct=True,  # ver `orquestador/respuesta_directa.py`
)
def responder_consulta_normativa(
    pregunta: str,
    jurisdiccion_id: str | None = None,
    provincia: str | None = None,
    tipo_aplicacion: str | None = None,
    tipo_zona: str | None = None,
) -> tuple[str, ResultadoTool]:
    from fitosanitarios.config import get_settings
    from fitosanitarios.llm.client import crear_cliente_llm
    from fitosanitarios.servicios.recursos import con_conexion_y_modelo

    args = ResponderConsultaNormativaArgs(
        pregunta=pregunta, jurisdiccion_id=jurisdiccion_id, provincia=provincia,
        tipo_aplicacion=tipo_aplicacion, tipo_zona=tipo_zona,
    )
    settings = get_settings()
    cliente_llm = crear_cliente_llm(settings)
    resultado = con_conexion_y_modelo(
        lambda conn, modelo: responder_consulta_normativa_logica(
            args, conn, modelo, cliente_llm, settings.rag_umbral_similitud
        )
    )
    return mensajes.resumen_para_llm(resultado.estado), resultado
