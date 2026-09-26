"""Tool `consultar_marbete`: RAG sobre el marbete de SENASA de un producto (ver
DECISIONES.md, "RAG de marbetes"). Resuelve el producto con el matching de siempre
(trigram + embedding), le pide al LLM que reformule la pregunta con los términos que
usaría el marbete, recupera los fragmentos de su marbete con búsqueda híbrida
(similitud + palabras, `servicios/busqueda_hibrida.py`) y el LLM
responde solo con esos fragmentos. Cada página que cita se verifica en código contra lo
recuperado: si no está, se descarta; sin ninguna cita verificada no hay respuesta."""

import json
import logging

from langchain_core.tools import tool
from pydantic import BaseModel

from fitosanitarios.datos.retrievers.catalogo import (
    buscar_productos_por_nombre,
    fragmentos_de_marbete,
    palabras_de,
)
from fitosanitarios.dominio.modelos import CampoFaltante, Cita, ResultadoTool
from fitosanitarios.dominio.motivos import MotivoNoResuelto
from fitosanitarios.servicios.busqueda_hibrida import seleccionar
from fitosanitarios.servicios.matching import Candidato, hay_empate_ambiguo, rankear_candidatos
from fitosanitarios.servicios.reformulacion import consulta_de_busqueda
from fitosanitarios.tools.consultar_marbete import mensajes
from fitosanitarios.tools.consultar_marbete.prompts import (
    DESCRIPCION,
    PLANTILLA_FRAGMENTO,
    PLANTILLA_PROMPT_USUARIO,
    PROMPT_REFORMULACION,
    PROMPT_SISTEMA_MARBETE,
)

logger = logging.getLogger(__name__)

TOP_K_FRAGMENTOS = 5


class ConsultarMarbeteArgs(BaseModel):
    producto: str
    pregunta: str


def _parsear_json(respuesta: str) -> dict | None:
    texto = respuesta.strip().removeprefix("```json").removeprefix("```").removesuffix("```")
    try:
        datos = json.loads(texto.strip())
    except json.JSONDecodeError:
        logger.warning("El LLM no devolvió JSON válido para consultar_marbete")
        return None
    return datos if isinstance(datos, dict) else None


def consultar_marbete_logica(
    args: ConsultarMarbeteArgs, conn, modelo_embeddings, cliente_llm, umbral_similitud: float
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

    sin_respaldo = ResultadoTool(
        estado="no_resuelto", motivo=MotivoNoResuelto.MARBETE_SIN_RESPALDO
    )
    # Reformulación: la pregunta más los términos que usaría el marbete.
    consulta = consulta_de_busqueda(args.pregunta, cliente_llm, PROMPT_REFORMULACION)
    if consulta is None:
        return sin_respaldo

    # Retrieval híbrido: los fragmentos del marbete de ese producto, rankeados por
    # similitud de significado y por palabras (BM25), fusionados.
    del_marbete = fragmentos_de_marbete(
        conn, modelo_embeddings.encode(consulta).tolist(), producto.id
    )
    elegidos = seleccionar(
        [f["score"] for f in del_marbete], [f["palabras"] for f in del_marbete],
        palabras_de(conn, consulta), umbral_similitud, TOP_K_FRAGMENTOS,
    )
    fragmentos = [del_marbete[p.indice] for p in elegidos]
    if not fragmentos:
        return sin_respaldo

    # Generación: el LLM responde solo con esos fragmentos.
    contexto = "\n\n".join(
        PLANTILLA_FRAGMENTO.format(pagina=f["pagina"], texto=f["texto"]) for f in fragmentos
    )
    respuesta_llm = cliente_llm.generar(
        PLANTILLA_PROMPT_USUARIO.format(
            producto=producto.marca, pregunta=args.pregunta, contexto=contexto
        ),
        system=PROMPT_SISTEMA_MARBETE,
    )
    datos_llm = _parsear_json(respuesta_llm)
    if datos_llm is None:
        return ResultadoTool(
            estado="no_resuelto", motivo=MotivoNoResuelto.MARBETE_SIN_RESPALDO,
            advertencias=[mensajes.ADVERTENCIA_SIN_JSON],
        )

    # Verificación: cada página citada tiene que estar entre los fragmentos recuperados.
    recuperadas = {f["pagina"] for f in fragmentos}
    paginas: list[int] = []
    advertencias: list[str] = []
    for pagina in datos_llm.get("paginas_citadas") or []:
        try:
            numero = int(pagina)
        except (TypeError, ValueError):
            numero = None
        if numero in recuperadas and numero not in paginas:
            paginas.append(numero)
        elif numero not in paginas:
            advertencias.append(mensajes.advertencia_pagina_descartada(pagina))
    if not paginas:
        return sin_respaldo

    return ResultadoTool(
        estado="ok",
        datos={
            "marca": producto.marca, "numero_inscripcion": producto.numero_inscripcion,
            "respuesta": datos_llm.get("respuesta") or "",
        },
        citas=[
            Cita(
                fuente="senasa", registro_senasa=producto.numero_inscripcion,
                documento=f"marbete, pág. {p}",
            )
            for p in sorted(paginas)
        ],
        advertencias=advertencias,
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
            args, conn, modelo, cliente_llm, settings.rag_umbral_similitud
        )
    )
    return mensajes.resumen_para_llm(resultado), resultado
