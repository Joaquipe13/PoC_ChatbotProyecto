"""Tool `responder_consulta_normativa`: responde preguntas sobre normativa
de aplicación citando artículos verificados (ver skill, tabla de tools RAG)."""

from langchain_core.tools import tool
from pydantic import BaseModel

from fitosanitarios.datos.retrievers.territorio import (
    articulos_por_similitud,
    listar_jurisdicciones_cargadas,
    obtener_localidad_por_jurisdiccion_id,
)
from fitosanitarios.dominio.modelos import CampoFaltante, ResultadoTool
from fitosanitarios.dominio.motivos import MotivoNoResuelto
from fitosanitarios.servicios.rag_normativa import (
    FragmentoNormativa,
    filtrar_por_umbral,
    responder_con_fragmentos,
)


class ResponderConsultaNormativaArgs(BaseModel):
    pregunta: str
    jurisdiccion_id: str | None = None
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
                    campo="jurisdiccion_id",
                    motivo="no se indicó de qué localidad es la consulta",
                    pregunta_sugerida="¿De qué localidad es la consulta?",
                    tipo_entrada="lista",
                    opciones=jurisdicciones,
                )
            ],
        )

    localidad = obtener_localidad_por_jurisdiccion_id(conn, args.jurisdiccion_id)
    if localidad is None:
        return ResultadoTool(estado="no_resuelto", motivo=MotivoNoResuelto.JURISDICCION_NO_CUBIERTA)

    embedding_pregunta = modelo_embeddings.encode(args.pregunta).tolist()
    filas = articulos_por_similitud(
        conn, embedding_pregunta, localidad.id, localidad.provincia_id, top_k=8
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
        return ResultadoTool(estado="no_resuelto", motivo=MotivoNoResuelto.NORMATIVA_SIN_RESPALDO)

    respuesta = responder_con_fragmentos(args.pregunta, relevantes, cliente_llm)
    if not respuesta.citas:
        # El LLM no pudo anclar ninguna cita verificable a los fragmentos
        # recuperados: no se muestra un veredicto sin fuente citable.
        return ResultadoTool(
            estado="no_resuelto", motivo=MotivoNoResuelto.NORMATIVA_SIN_RESPALDO,
            advertencias=respuesta.advertencias,
        )

    return ResultadoTool(
        estado="ok",
        datos={"veredicto": respuesta.veredicto, "regla": respuesta.regla},
        citas=respuesta.citas,
        advertencias=respuesta.advertencias,
    )


@tool(
    "responder_consulta_normativa",
    args_schema=ResponderConsultaNormativaArgs,
    response_format="content_and_artifact",
)
def responder_consulta_normativa(
    pregunta: str,
    jurisdiccion_id: str | None = None,
    tipo_aplicacion: str | None = None,
    tipo_zona: str | None = None,
) -> tuple[str, ResultadoTool]:
    """Responde una pregunta puntual sobre normativa de aplicación de
    fitosanitarios en una localidad cargada, citando artículo y norma. Usar
    para preguntas de texto ("¿a cuántos metros de una escuela puedo
    aplicar?"), no para el dictamen de una receta (`evaluar_viabilidad_legal`).

    Args:
        pregunta: la pregunta tal como la escribió el operario.
        jurisdiccion_id: localidad de la consulta (explícita o de la receta
            en curso), si se conoce.
        tipo_aplicacion: "terrestre" o "aerea", si se mencionó.
        tipo_zona: tipo de zona protegida en cuestión, si se mencionó.
    """
    from fitosanitarios.config import get_settings
    from fitosanitarios.llm.client import crear_cliente_llm
    from fitosanitarios.tools._recursos import con_conexion_y_modelo

    args = ResponderConsultaNormativaArgs(
        pregunta=pregunta, jurisdiccion_id=jurisdiccion_id,
        tipo_aplicacion=tipo_aplicacion, tipo_zona=tipo_zona,
    )
    settings = get_settings()
    cliente_llm = crear_cliente_llm(settings)
    resultado = con_conexion_y_modelo(
        lambda conn, modelo: responder_consulta_normativa_logica(
            args, conn, modelo, cliente_llm, settings.rag_umbral_similitud
        )
    )
    return f"responder_consulta_normativa: estado={resultado.estado}", resultado
