"""Tool `listar_limitaciones`: las limitaciones que impone la normativa de una
localidad ("¿qué limitaciones hay en El Trébol?", "¿qué artículo fija el límite?")
y, si se da una distancia, qué opciones hay a esa distancia ("¿puedo aplicar a
1.000 m bajo alguna condición?").

Sale de las reglas cargadas (`reglas.csv`), no de una búsqueda por similitud: la
lista es completa y cada línea cita norma y artículo. Las prohibiciones (`N`) son
las que bloquean el dictamen; las condicionales (`S`) solo se muestran acá.
"""

from langchain_core.tools import tool
from pydantic import BaseModel

from fitosanitarios.datos.retrievers.territorio import reglas_candidatas
from fitosanitarios.dominio.modelos import Cita, ResultadoTool
from fitosanitarios.dominio.motivos import MotivoNoResuelto
from fitosanitarios.servicios.reglas import ReglaCandidata
from fitosanitarios.servicios.ubicacion import resolver_ubicacion_o_cortar
from fitosanitarios.tools.listar_limitaciones import mensajes
from fitosanitarios.tools.listar_limitaciones.prompts import DESCRIPCION
from fitosanitarios.tools.listar_limitaciones.utils import (
    filtrar_reglas,
    normalizar_bandas,
    normalizar_tipo_aplicacion,
    normalizar_tipo_zona,
    restricciones_a_distancia,
)


class ListarLimitacionesArgs(BaseModel):
    localidad: str | None = None
    provincia: str | None = None  # solo si la localidad no está cargada
    tipo_aplicacion: str | None = None
    banda: str | None = None
    tipo_zona: str | None = None
    distancia_m: float | None = None


def regla_a_dict(r: ReglaCandidata) -> dict:
    return {
        "tipo_zona": r.tipo_zona, "tipo_aplicacion": r.tipo_aplicacion, "bandas": r.bandas,
        "distancia_min_m": r.distancia_min_m, "norma": r.norma, "articulo": r.articulo,
        "jurisdiccion_id": r.jurisdiccion_id, "observaciones": r.observaciones,
        "condiciones": r.condiciones, "extraida_de_pdf": r.fuente == "pdf_extraido",
    }


def _cita(r: ReglaCandidata) -> Cita:
    return Cita(
        fuente="normativa", jurisdiccion_id=r.jurisdiccion_id, norma=r.norma, articulo=r.articulo
    )


def listar_limitaciones_logica(args: ListarLimitacionesArgs, conn) -> ResultadoTool:
    ubicacion, corte = resolver_ubicacion_o_cortar(conn, args.localidad, args.provincia)
    if corte is not None:
        return corte

    advertencias: list[str] = []
    if not ubicacion.con_normativa_municipal:
        advertencias.append(mensajes.aviso_sin_normativa_municipal(ubicacion.nombre))

    tipo_aplicacion = normalizar_tipo_aplicacion(args.tipo_aplicacion)
    if args.tipo_aplicacion and args.tipo_aplicacion.strip() and tipo_aplicacion is None:
        advertencias.append(mensajes.aviso_tipo_aplicacion_no_entendido(args.tipo_aplicacion.strip()))
    bandas = normalizar_bandas(args.banda)
    if bandas == []:
        advertencias.append(mensajes.aviso_banda_no_entendida(args.banda.strip()))
        bandas = None
    tipo_zona = normalizar_tipo_zona(args.tipo_zona)

    def filtrar(reglas):
        return filtrar_reglas(reglas, tipo_zona, tipo_aplicacion, bandas)

    prohibiciones = filtrar(reglas_candidatas(conn, ubicacion.localidad_id, ubicacion.provincia_id))
    condicionales = filtrar(
        reglas_candidatas(conn, ubicacion.localidad_id, ubicacion.provincia_id, permitido=True)
    )
    if not prohibiciones and not condicionales:
        return ResultadoTool(
            estado="no_resuelto", motivo=MotivoNoResuelto.SIN_REGLA_APLICABLE,
            advertencias=advertencias,
        )

    datos: dict = {
        "localidad": ubicacion.nombre,
        "filtros": {"tipo_aplicacion": tipo_aplicacion, "bandas": bandas, "tipo_zona": tipo_zona},
        "distancia_m": args.distancia_m,
        "prohibiciones": [regla_a_dict(r) for r in prohibiciones],
        "condicionales": [regla_a_dict(r) for r in condicionales],
    }
    reglas_citadas = prohibiciones + condicionales
    if args.distancia_m is not None:
        restricciones = restricciones_a_distancia(
            prohibiciones, condicionales, args.distancia_m, tipo_aplicacion, bandas
        )
        datos["restricciones"] = [
            {
                "prohibicion": regla_a_dict(x.prohibicion),
                "excepciones": [regla_a_dict(e) for e in x.excepciones],
            }
            for x in restricciones
        ]
        reglas_citadas = [x.prohibicion for x in restricciones] + [
            e for x in restricciones for e in x.excepciones
        ]

    return ResultadoTool(
        estado="ok", datos=datos, citas=[_cita(r) for r in reglas_citadas],
        advertencias=advertencias,
    )


@tool(
    "listar_limitaciones",
    args_schema=ListarLimitacionesArgs,
    description=DESCRIPCION,
    response_format="content_and_artifact",
    return_direct=True,  # ver `orquestador/respuesta_directa.py`
)
def listar_limitaciones(
    localidad: str | None = None,
    provincia: str | None = None,
    tipo_aplicacion: str | None = None,
    banda: str | None = None,
    tipo_zona: str | None = None,
    distancia_m: float | None = None,
) -> tuple[str, ResultadoTool]:
    from fitosanitarios.servicios.recursos import con_conexion

    args = ListarLimitacionesArgs(
        localidad=localidad, provincia=provincia, tipo_aplicacion=tipo_aplicacion,
        banda=banda, tipo_zona=tipo_zona, distancia_m=distancia_m,
    )
    resultado = con_conexion(lambda conn: listar_limitaciones_logica(args, conn))
    return mensajes.resumen_para_llm(resultado), resultado
