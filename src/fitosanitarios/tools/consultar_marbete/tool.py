"""Tool `consultar_marbete`: RAG sobre el marbete de SENASA de un producto (ver
DECISIONES.md, "RAG de marbetes"). Resuelve el producto con el matching de siempre
(trigram + embedding), le pide al LLM que reformule la pregunta con los términos que
usaría el marbete, recupera los fragmentos de su marbete con búsqueda híbrida
(similitud + palabras, `servicios/busqueda_hibrida.py`) y el LLM
responde solo con esos fragmentos. Cada página que cita se verifica en código contra lo
recuperado: si no está, se descarta; sin ninguna cita verificada no hay respuesta."""

from langchain_core.tools import tool
from pydantic import BaseModel

from fitosanitarios.datos.retrievers.catalogo import buscar_productos_por_nombre
from fitosanitarios.dominio.modelos import CampoFaltante, Cita, ResultadoTool
from fitosanitarios.dominio.motivos import MotivoNoResuelto
from fitosanitarios.servicios.demo_reformulacion import comparar_con_y_sin_reformular
from fitosanitarios.servicios.marbete import responder_con_el_marbete
from fitosanitarios.servicios.matching import Candidato, hay_empate_ambiguo, rankear_candidatos
from fitosanitarios.servicios.reformulacion import consulta_de_busqueda
from fitosanitarios.tools.consultar_marbete import mensajes
from fitosanitarios.tools.consultar_marbete.prompts import (
    DESCRIPCION,
    PROMPT_REFORMULACION,
)


class ConsultarMarbeteArgs(BaseModel):
    producto: str
    pregunta: str


def consultar_marbete_logica(
    args: ConsultarMarbeteArgs, conn, modelo_embeddings, cliente_llm, umbral_similitud: float,
    modo_demo_reformulacion: bool = False,
) -> ResultadoTool:
    candidatos = buscar_productos_por_nombre(conn, args.producto, modelo_embeddings)
    if not candidatos:
        return ResultadoTool(estado="no_resuelto", motivo=MotivoNoResuelto.PRODUCTO_NO_ENCONTRADO)
    ranking = rankear_candidatos(
        args.producto, [Candidato(id=c.id, nombre=c.marca) for c in candidatos], top_k=5
    )
    if hay_empate_ambiguo(ranking):
        return ResultadoTool(
            estado="faltan_datos",
            faltantes=[CampoFaltante(
                campo="producto", motivo=mensajes.motivo_producto_ambiguo(args.producto),
                pregunta_sugerida=mensajes.pregunta_producto_ambiguo(args.producto),
                tipo_entrada="lista", opciones=[r.candidato.nombre for r in ranking],
            )],
        )
    producto = candidatos[0]

    def responder(consulta: str | None) -> ResultadoTool:
        return _responder_con_el_marbete(
            args.pregunta, consulta, producto, conn, modelo_embeddings, cliente_llm,
            umbral_similitud,
        )

    if modo_demo_reformulacion:
        return comparar_con_y_sin_reformular(
            args.pregunta, cliente_llm, PROMPT_REFORMULACION, responder, "consultar_marbete"
        )
    # Reformulación: la pregunta más los términos que usaría el marbete.
    return responder(consulta_de_busqueda(args.pregunta, cliente_llm, PROMPT_REFORMULACION))


def _responder_con_el_marbete(
    pregunta: str, consulta: str | None, producto, conn, modelo_embeddings, cliente_llm,
    umbral_similitud: float,
) -> ResultadoTool:
    """Busca en el marbete con `consulta` y responde `pregunta`. `consulta` es `None` si la
    pregunta quedó fuera de tema al reformularla."""
    sin_respaldo = ResultadoTool(
        estado="no_resuelto", motivo=MotivoNoResuelto.MARBETE_SIN_RESPALDO
    )
    if consulta is None:
        return sin_respaldo
    respuesta = responder_con_el_marbete(
        pregunta, consulta, producto.id, producto.marca, conn, modelo_embeddings, cliente_llm,
        umbral_similitud,
    )
    if respuesta.sin_json:
        return ResultadoTool(
            estado="no_resuelto", motivo=MotivoNoResuelto.MARBETE_SIN_RESPALDO,
            advertencias=[mensajes.ADVERTENCIA_SIN_JSON],
        )
    if not respuesta.paginas:
        return sin_respaldo
    return ResultadoTool(
        estado="ok",
        datos={
            "marca": producto.marca, "numero_inscripcion": producto.numero_inscripcion,
            "respuesta": respuesta.respuesta,
        },
        citas=[
            Cita(
                fuente="senasa", registro_senasa=producto.numero_inscripcion,
                documento=f"marbete, pág. {p}",
            )
            for p in respuesta.paginas
        ],
        advertencias=[
            mensajes.advertencia_pagina_descartada(p) for p in respuesta.paginas_descartadas
        ],
    )


@tool(
    "consultar_marbete",
    args_schema=ConsultarMarbeteArgs,
    description=DESCRIPCION,
    response_format="content_and_artifact",
    return_direct=True,  # ver `orquestador/respuesta_directa.py`
)
def consultar_marbete(producto: str, pregunta: str) -> tuple[str, ResultadoTool]:
    from fitosanitarios.config import get_settings
    from fitosanitarios.llm.client import crear_cliente_llm
    from fitosanitarios.servicios.recursos import con_conexion_y_modelo

    args = ConsultarMarbeteArgs(producto=producto, pregunta=pregunta)
    settings = get_settings()
    cliente_llm = crear_cliente_llm(settings)
    resultado = con_conexion_y_modelo(
        lambda conn, modelo: consultar_marbete_logica(
            args, conn, modelo, cliente_llm, settings.rag_umbral_similitud,
            settings.modo_demo_reformulacion,
        )
    )
    return mensajes.resumen_para_llm(resultado), resultado
