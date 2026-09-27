"""Tool `listar_limitaciones`: las limitaciones que impone la normativa de una
localidad ("¿qué limitaciones hay en El Trébol?", "¿qué artículo fija el límite?")
y, si se da una distancia, qué opciones hay a esa distancia ("¿puedo aplicar a
1.000 m bajo alguna condición?").

Sale de las reglas cargadas (`reglas.csv`), no de una búsqueda por similitud: la
lista es completa y cada línea cita norma y artículo. Las prohibiciones (`N`) son
las que bloquean el dictamen; las condicionales (`S`) solo se muestran acá.

Si el operario nombra un producto ("tengo Roundup, ¿a cuánto del pueblo lo puedo
tirar?"), la banda sale del registro de SENASA y se filtra con ella, aunque venga también
una banda.
"""

from langchain_core.tools import tool
from pydantic import BaseModel

from fitosanitarios.datos.retrievers.catalogo import buscar_productos_por_nombre
from fitosanitarios.datos.retrievers.territorio import reglas_candidatas
from fitosanitarios.dominio.modelos import CampoFaltante, Cita, ResultadoTool
from fitosanitarios.dominio.motivos import MotivoNoResuelto
from fitosanitarios.servicios.matching import Candidato, hay_empate_ambiguo, rankear_candidatos
from fitosanitarios.servicios.reglas import ReglaCandidata
from fitosanitarios.servicios.ubicacion import resolver_ubicacion_o_cortar
from fitosanitarios.tools.listar_limitaciones import mensajes
from fitosanitarios.tools.listar_limitaciones.prompts import DESCRIPCION
from fitosanitarios.tools.listar_limitaciones.utils import (
    distancias_que_rigen,
    equipo_sin_norma,
    filtrar_reglas,
    nombra_los_dos_tipos,
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
    producto: str | None = None  # su banda del registro manda sobre `banda`


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


def _producto_con_banda(
    conn, modelo_embeddings, nombre: str
) -> tuple[dict | None, ResultadoTool | None]:
    """El producto del registro y su banda: (producto, None); (None, None) si no está; y
    (None, repregunta) si el nombre coincide con varios de distinta banda. Si todas las
    variantes tienen la misma banda ("Roundup": Fg, Wg, Max...) no hace falta preguntar."""
    candidatos = buscar_productos_por_nombre(conn, nombre, modelo_embeddings)
    if not candidatos:
        return None, None
    ranking = rankear_candidatos(
        nombre, [Candidato(id=c.id, nombre=c.marca) for c in candidatos], top_k=5
    )
    if hay_empate_ambiguo(ranking):
        empatados = {r.candidato.id for r in ranking}
        bandas = {c.banda_toxicologica for c in candidatos if c.id in empatados}
        if len(bandas) == 1 and None not in bandas:
            variantes = [r.candidato.nombre for r in ranking]
            return {
                "marca": nombre, "numero_inscripcion": None, "banda": bandas.pop(),
                "variantes": variantes,
            }, None
        return None, ResultadoTool(
            estado="faltan_datos",
            faltantes=[CampoFaltante(
                campo="producto", motivo=mensajes.motivo_producto_ambiguo(nombre),
                pregunta_sugerida=mensajes.pregunta_producto_ambiguo(nombre),
                tipo_entrada="lista", opciones=[r.candidato.nombre for r in ranking],
            )],
        )
    elegido = candidatos[0]
    return {
        "marca": elegido.marca, "numero_inscripcion": elegido.numero_inscripcion,
        "banda": elegido.banda_toxicologica, "variantes": [],
    }, None


def listar_limitaciones_logica(
    args: ListarLimitacionesArgs, conn, modelo_embeddings=None
) -> ResultadoTool:
    ubicacion, corte = resolver_ubicacion_o_cortar(conn, args.localidad, args.provincia)
    if corte is not None:
        return corte

    advertencias: list[str] = []
    if not ubicacion.con_normativa_municipal:
        advertencias.append(mensajes.aviso_sin_normativa_municipal(ubicacion.nombre))

    compara = nombra_los_dos_tipos(args.tipo_aplicacion)
    tipo_aplicacion = None if compara else normalizar_tipo_aplicacion(args.tipo_aplicacion)
    if (
        args.tipo_aplicacion and args.tipo_aplicacion.strip() and tipo_aplicacion is None
        and not compara
    ):
        advertencias.append(mensajes.aviso_tipo_aplicacion_no_entendido(args.tipo_aplicacion.strip()))
    equipo = equipo_sin_norma(args.tipo_aplicacion)
    if equipo is not None and tipo_aplicacion is not None:
        advertencias.append(mensajes.aviso_equipo_sin_norma(equipo))
    bandas = normalizar_bandas(args.banda)
    if bandas == []:
        advertencias.append(mensajes.aviso_banda_no_entendida(args.banda.strip()))
        bandas = None
    tipo_zona = normalizar_tipo_zona(args.tipo_zona)

    # Si nombró un producto, manda la banda del registro: una banda dicha (o supuesta por el
    # modelo) que no coincide cambiaría la distancia. La dicha solo se usa si el producto no
    # está, no tiene banda o es ambiguo.
    producto = None
    citas_producto: list[Cita] = []
    if args.producto and args.producto.strip():
        producto, corte = _producto_con_banda(conn, modelo_embeddings, args.producto.strip())
        if corte is not None:
            if bandas is None:
                return corte
        elif producto is None:
            if bandas is None:
                advertencias.append(mensajes.aviso_producto_no_encontrado(args.producto.strip()))
        elif producto["banda"] is None:
            if bandas is None:
                advertencias.append(mensajes.aviso_producto_sin_banda(producto["marca"]))
            producto = None
        else:
            if bandas is not None and bandas != [producto["banda"]]:
                advertencias.append(
                    mensajes.aviso_banda_distinta_del_registro(producto["marca"], producto["banda"])
                )
            bandas = [producto["banda"]]
            if producto["numero_inscripcion"]:
                citas_producto = [Cita(
                    fuente="senasa", registro_senasa=producto["numero_inscripcion"],
                    documento="detalle API",
                )]

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
        "producto": producto,
        "que_rige": [
            {
                "tipo_zona": d.tipo_zona, "tipo_aplicacion": d.tipo_aplicacion,
                "tramos": [
                    {
                        "bandas": t.bandas,
                        "regla": regla_a_dict(t.regla) if t.regla else None,
                        "con_excepciones": t.con_excepciones,
                    }
                    for t in d.tramos
                ],
            }
            for d in distancias_que_rigen(prohibiciones, condicionales, tipo_aplicacion, bandas)
        ],
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
        estado="ok", datos=datos, citas=citas_producto + [_cita(r) for r in reglas_citadas],
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
    producto: str | None = None,
) -> tuple[str, ResultadoTool]:
    from fitosanitarios.servicios.recursos import con_conexion, con_conexion_y_modelo

    args = ListarLimitacionesArgs(
        localidad=localidad, provincia=provincia, tipo_aplicacion=tipo_aplicacion,
        banda=banda, tipo_zona=tipo_zona, distancia_m=distancia_m, producto=producto,
    )
    if producto:  # el matching del producto usa embeddings
        resultado = con_conexion_y_modelo(
            lambda conn, modelo: listar_limitaciones_logica(args, conn, modelo)
        )
    else:
        resultado = con_conexion(lambda conn: listar_limitaciones_logica(args, conn))
    return mensajes.resumen_para_llm(resultado), resultado
