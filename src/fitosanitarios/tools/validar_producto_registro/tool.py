"""Tool `validar_producto_registro`: valida un producto puntual contra el
registro de SENASA (ver skill, "Matriz de parámetros")."""

from langchain_core.tools import tool
from pydantic import BaseModel

from fitosanitarios.dominio.modelos import CampoFaltante, Cita, ResultadoTool
from fitosanitarios.dominio.motivos import MotivoNoResuelto
from fitosanitarios.servicios.formato import num
from fitosanitarios.servicios.marbete import responder_con_el_marbete
from fitosanitarios.servicios.validacion_producto import (
    ResolucionProducto,
    resolver_y_validar_producto,
)
from fitosanitarios.tools.validar_producto_registro import mensajes
from fitosanitarios.tools.validar_producto_registro.prompts import DESCRIPCION


class ValidarProductoRegistroArgs(BaseModel):
    producto_nombre: str
    cultivo: str | None = None  # sin cultivo: solo registro y banda
    adversidad: str | None = None
    dosis_valor: float | None = None
    dosis_unidad: str | None = None


def _sin_usos_registrados(
    args: ValidarProductoRegistroArgs, resolucion: ResolucionProducto, conn, modelo_embeddings,
    cliente_llm, umbral_similitud: float,
) -> ResultadoTool:
    """El producto está registrado pero SENASA no publica sus cultivos ni sus dosis (pasa
    con 6 de cada 7 productos). Antes era un "No pude completar la consulta" con el motivo
    en jerga interna, y se perdía que el producto sí está registrado y su banda (caso real:
    "¿es correcta la dosis para Manto?", 28/09/2026). Ahora se muestra lo que se sabe, se
    dice qué no se puede verificar y, si el producto tiene marbete con texto, se busca ahí
    la dosis para ese cultivo, citando la página."""
    cp = resolucion.chequeo_producto
    dosis = (
        f"{num(args.dosis_valor)} {args.dosis_unidad}"
        if args.dosis_valor is not None and args.dosis_unidad else None
    )
    citas = list(cp.citas) if cp else []
    marbete = None
    if cliente_llm is not None and resolucion.producto_id is not None:
        para = f" para {args.cultivo}" + (f" contra {args.adversidad}" if args.adversidad else "")
        pregunta = f"¿Cuál es la dosis de {resolucion.marca}{para}?"
        respuesta = responder_con_el_marbete(
            pregunta, f"{pregunta} Dosis por hectárea, cultivo, plaga.",
            resolucion.producto_id, resolucion.marca, conn, modelo_embeddings, cliente_llm,
            umbral_similitud,
        )
        if respuesta.paginas:
            marbete = respuesta.respuesta
            citas += [
                Cita(
                    fuente="senasa", registro_senasa=resolucion.numero_inscripcion,
                    documento=f"marbete, pág. {p}",
                )
                for p in respuesta.paginas
            ]
    return ResultadoTool(
        estado="ok",
        datos={
            "producto": resolucion.marca,
            "numero_inscripcion": resolucion.numero_inscripcion,
            "banda_toxicologica": resolucion.banda_toxicologica,
            "cultivo": args.cultivo,
            "cultivo_autorizado": None,
            "usos_del_cultivo": [],
            "sin_usos_registrados": True,
            "dosis_declarada": dosis,
            "marbete": marbete,
        },
        citas=citas,
        chequeos_no_realizados=[mensajes.no_verificado_sin_usos(args.cultivo, dosis)],
    )


def validar_producto_registro_logica(
    args: ValidarProductoRegistroArgs, conn, modelo_embeddings, tolerancia_pct: float,
    cliente_llm=None, umbral_similitud: float = 0.0,
) -> ResultadoTool:
    """`cliente_llm`: para buscar la dosis en el marbete de un producto sin usos
    registrados; sin él (tests) no se busca."""
    resolucion = resolver_y_validar_producto(
        conn, modelo_embeddings, args.producto_nombre, args.cultivo,
        args.adversidad, args.dosis_valor, args.dosis_unidad, tolerancia_pct,
    )

    if resolucion.opciones_ambiguas:
        return ResultadoTool(
            estado="faltan_datos",
            faltantes=[
                CampoFaltante(
                    campo="producto_nombre", motivo=mensajes.MOTIVO_PRODUCTO_AMBIGUO,
                    pregunta_sugerida=mensajes.pregunta_producto_ambiguo(args.producto_nombre),
                    tipo_entrada="lista",
                    opciones=resolucion.opciones_ambiguas,
                )
            ],
        )

    if resolucion.motivo_no_resuelto == MotivoNoResuelto.SIN_USOS_REGISTRADOS:
        return _sin_usos_registrados(
            args, resolucion, conn, modelo_embeddings, cliente_llm, umbral_similitud
        )
    if resolucion.motivo_no_resuelto is not None:
        return ResultadoTool(estado="no_resuelto", motivo=resolucion.motivo_no_resuelto)

    cp = resolucion.chequeo_producto
    datos = {
        "producto": resolucion.marca,
        "numero_inscripcion": resolucion.numero_inscripcion,
        "banda_toxicologica": resolucion.banda_toxicologica,
        "cultivo": args.cultivo,
        "cultivo_autorizado": cp.cultivo_autorizado,
        "usos_del_cultivo": resolucion.usos_del_cultivo or [],
    }
    advertencias = []
    if cp.cultivo_autorizado is False:
        advertencias.append(mensajes.advertencia_sin_uso_registrado(resolucion.marca, args.cultivo))

    estado = "ok" if cp.cultivo_autorizado or args.cultivo is None else "observado"
    return ResultadoTool(estado=estado, datos=datos, citas=cp.citas, advertencias=advertencias)


@tool(
    "validar_producto_registro",
    args_schema=ValidarProductoRegistroArgs,
    description=DESCRIPCION,
    response_format="content_and_artifact",
    return_direct=True,  # ver `orquestador/respuesta_directa.py`
)
def validar_producto_registro(
    producto_nombre: str,
    cultivo: str | None = None,
    adversidad: str | None = None,
    dosis_valor: float | None = None,
    dosis_unidad: str | None = None,
) -> tuple[str, ResultadoTool]:
    from fitosanitarios.config import get_settings
    from fitosanitarios.llm.client import crear_cliente_llm
    from fitosanitarios.servicios.recursos import con_conexion_y_modelo

    args = ValidarProductoRegistroArgs(
        producto_nombre=producto_nombre, cultivo=cultivo, adversidad=adversidad,
        dosis_valor=dosis_valor, dosis_unidad=dosis_unidad,
    )
    settings = get_settings()
    resultado = con_conexion_y_modelo(
        lambda conn, modelo: validar_producto_registro_logica(
            args, conn, modelo, settings.dosis_tolerancia_pct, crear_cliente_llm(settings),
            settings.rag_umbral_similitud,
        )
    )
    return mensajes.resumen_para_llm(resultado.estado), resultado
