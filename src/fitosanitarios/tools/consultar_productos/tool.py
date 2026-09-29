"""Tool `consultar_productos`: lista productos registrados filtrando por cualquiera de sus
atributos, solos o combinados (cultivo, adversidad, principio activo, aptitud, banda,
firma, marca). Informa lo registrado; no recomienda qué aplicar (ver skill, tool
`consultar_productos`).

Una localidad y una distancia a la zona urbana equivalen a filtrar por banda: las que se
pueden aplicar a esa distancia según las reglas cargadas ("¿qué fungicidas para trigo
puedo aplicar con avión a 1500 m de El Trébol?"). Sin tipo de aplicación, se responde
para aérea y terrestre. Así una pregunta compuesta es una sola llamada: antes Gemini la
partía entre `listar_limitaciones` y esta tool, y el listado no se cruzaba con las bandas
permitidas (hallazgo del 28/09/2026, ver DIFICULTADES.md).

Un filtro que no se encuentra en el registro (una firma, una aptitud o un cultivo que no
existen) se omite en la búsqueda y se avisa.
"""

import logging

from langchain.tools import ToolRuntime
from langchain_core.tools import tool
from pydantic import BaseModel, model_validator

from fitosanitarios.datos.retrievers.catalogo import (
    aptitudes_registradas,
    listar_productos_por_filtro,
    resolver_entidad_por_nombre,
    resolver_firmas,
)
from fitosanitarios.datos.retrievers.territorio import listar_localidades, reglas_candidatas
from fitosanitarios.dominio.modelos import Cita, ResultadoTool
from fitosanitarios.servicios.conversacion import lo_dicho_en_la_conversacion, se_menciona
from fitosanitarios.servicios.limitaciones import (
    bandas_a_distancia,
    equipo_sin_norma,
    filtrar_reglas,
    nombra_los_dos_tipos,
    normalizar_bandas,
    normalizar_tipo_aplicacion,
)
from fitosanitarios.servicios.reglas import ReglaCandidata, texto_plano
from fitosanitarios.servicios.ubicacion import resolver_ubicacion_o_cortar
from fitosanitarios.tools.consultar_productos import mensajes
from fitosanitarios.tools.consultar_productos.prompts import DESCRIPCION
from fitosanitarios.tools.consultar_productos.utils import (
    bandas_hasta,
    intersectar_bandas,
    resolver_aptitudes,
)

logger = logging.getLogger(__name__)

# La distancia que se consulta con una localidad es siempre a la zona urbana.
_ZONA = "zona_urbana"


class ConsultarProductosArgs(BaseModel):
    cultivo: str | None = None
    adversidad: str | None = None
    principio_activo: str | None = None
    aptitud: str | None = None
    banda: str | None = None
    banda_maxima: str | None = None
    firma: str | None = None
    marca: str | None = None
    localidad: str | None = None
    provincia: str | None = None  # solo si la localidad no está cargada
    tipo_aplicacion: str | None = None
    distancia_m: float | None = None

    @model_validator(mode="after")
    def _al_menos_un_filtro(self) -> "ConsultarProductosArgs":
        filtros = (
            self.cultivo, self.adversidad, self.principio_activo, self.aptitud, self.banda,
            self.banda_maxima, self.firma, self.marca, self.distancia_m,
        )
        if not any(f not in (None, "") for f in filtros):
            raise ValueError(mensajes.motivo_sin_filtros())
        return self


def _texto(valor: str | None) -> str | None:
    return valor.strip() if valor and valor.strip() else None


def _cita(r: ReglaCandidata) -> Cita:
    return Cita(
        fuente="normativa", jurisdiccion_id=r.jurisdiccion_id, norma=r.norma, articulo=r.articulo
    )


def _tipos_de_aplicacion(texto: str | None, advertencias: list[str]) -> list[str]:
    """Los tipos para los que se responde: el que dijo (o el de su equipo), o los dos si
    no dijo ninguno o los comparó."""
    texto = _texto(texto)
    if texto is None or nombra_los_dos_tipos(texto):
        return ["aerea", "terrestre"]
    tipo = normalizar_tipo_aplicacion(texto)
    if tipo is None:
        advertencias.append(mensajes.aviso_tipo_aplicacion_no_entendido(texto))
        return ["aerea", "terrestre"]
    equipo = equipo_sin_norma(texto)
    if equipo is not None:
        advertencias.append(mensajes.aviso_equipo_sin_norma(equipo))
    return [tipo]


def _bandas_por_distancia(
    args: ConsultarProductosArgs, conn, advertencias: list[str], citas: list[Cita]
) -> tuple[dict | None, ResultadoTool | None]:
    """Qué bandas se pueden a esa distancia de la zona urbana, por tipo de aplicación:
    ({"localidad", "por_aplicacion": [BandasADistancia]}, None), o (None, corte) si falta la
    localidad o es ambigua."""
    ubicacion, corte = resolver_ubicacion_o_cortar(conn, args.localidad, args.provincia)
    if corte is not None:
        return None, corte
    if not ubicacion.con_normativa_municipal:
        advertencias.append(mensajes.aviso_sin_normativa_municipal(ubicacion.nombre))
    prohibiciones = filtrar_reglas(
        reglas_candidatas(conn, ubicacion.localidad_id, ubicacion.provincia_id), _ZONA
    )
    condicionales = filtrar_reglas(
        reglas_candidatas(conn, ubicacion.localidad_id, ubicacion.provincia_id, permitido=True),
        _ZONA,
    )
    por_aplicacion = [
        bandas_a_distancia(prohibiciones, condicionales, args.distancia_m, tipo)
        for tipo in _tipos_de_aplicacion(args.tipo_aplicacion, advertencias)
    ]
    for b in por_aplicacion:
        for r in b.reglas:
            if _cita(r) not in citas:
                citas.append(_cita(r))
    return {"localidad": ubicacion.nombre, "por_aplicacion": por_aplicacion}, None


def _cultivo_supuesto(cultivo: str | None, dicho: str | None, conn) -> bool:
    """El LLM pasó un cultivo que nadie dijo, o tomó una localidad por un cultivo. Con
    "¿puedo aplicar metsulfuron en el trébol?", Gemini pasó `cultivo="trigo"` en 4 de 5
    corridas y `"Trébol"` en la otra, aunque la descripción se lo prohíbe (28/09/2026).
    `dicho`: `None` si no se sabe qué se dijo (llamadas directas, tests)."""
    if not _texto(cultivo) or dicho is None:
        return False
    if not se_menciona(cultivo, dicho):
        return True
    localidades = {texto_plano(j.nombre) for j in listar_localidades(conn)}
    plano = texto_plano(cultivo)
    return any(plano in (loc, loc.removeprefix("el ")) for loc in localidades) and (
        f"el {plano}" in dicho
    )


def consultar_productos_logica(
    args: ConsultarProductosArgs, conn, modelo_embeddings, dicho: str | None = None
) -> ResultadoTool:
    """`dicho`: lo dicho en la conversación (`lo_dicho_en_la_conversacion`), para descartar
    un cultivo que el LLM supuso."""
    advertencias: list[str] = []
    citas: list[Cita] = []
    if _cultivo_supuesto(args.cultivo, dicho, conn):
        logger.info("consultar_productos: cultivo '%s' supuesto por el LLM, se omite", args.cultivo)
        args = args.model_copy(update={"cultivo": None})

    def resolver(tabla: str, columna: str, valor: str | None, que: str) -> int | None:
        valor = _texto(valor)
        if valor is None:
            return None
        id_ = resolver_entidad_por_nombre(conn, tabla, columna, valor, modelo_embeddings)
        if id_ is None:
            advertencias.append(mensajes.aviso_filtro_no_encontrado(que, valor))
        return id_

    cultivo_id = resolver("cultivo", "nombre", args.cultivo, "el cultivo")
    adversidad_id = resolver("adversidad", "nombre_comun", args.adversidad, "la plaga")
    principio_id = resolver(
        "principio_activo", "nombre", args.principio_activo, "el principio activo"
    )

    aptitudes = None
    if _texto(args.aptitud):
        aptitudes, sin_resolver = resolver_aptitudes(args.aptitud, aptitudes_registradas(conn))
        for parte in sin_resolver:
            advertencias.append(mensajes.aviso_filtro_no_encontrado("la aptitud", parte))

    firma_ids = None
    if _texto(args.firma):
        firma_ids = resolver_firmas(conn, _texto(args.firma))
        if not firma_ids:
            advertencias.append(mensajes.aviso_filtro_no_encontrado("la firma", args.firma))

    bandas_dichas = normalizar_bandas(args.banda)
    if bandas_dichas == []:
        advertencias.append(mensajes.aviso_banda_no_entendida(args.banda.strip()))
        bandas_dichas = None
    maxima = normalizar_bandas(args.banda_maxima)
    bandas_maximas = bandas_hasta(maxima[0]) if maxima else None
    bandas_filtro = intersectar_bandas(bandas_dichas, bandas_maximas)

    distancia = None
    if args.distancia_m is not None:
        distancia, corte = _bandas_por_distancia(args, conn, advertencias, citas)
        if corte is not None:
            return corte

    filtros = {
        "cultivo_id": cultivo_id, "adversidad_id": adversidad_id,
        "principio_activo_id": principio_id, "aptitudes": aptitudes or None,
        "firma_ids": firma_ids or None, "marca": _texto(args.marca),
    }
    # Una lista por tipo de aplicación; si aérea y terrestre dan lo mismo, es una sola lista
    # que vale para las dos.
    grupos: list[dict] = []
    if distancia is None:
        grupos.append({"aplicaciones": [], "bandas": bandas_filtro})
    else:
        for b in distancia["por_aplicacion"]:
            grupo = {
                "aplicaciones": [b.tipo_aplicacion],
                "bandas": intersectar_bandas(bandas_filtro, b.permitidas),
                "permitidas": b.permitidas, "con_excepcion": b.con_excepcion,
                "prohibidas": b.prohibidas,
            }
            igual = next(
                (g for g in grupos
                 if {k: v for k, v in g.items() if k != "aplicaciones"}
                 == {k: v for k, v in grupo.items() if k != "aplicaciones"}),
                None,
            )
            if igual is not None:
                igual["aplicaciones"].append(b.tipo_aplicacion)
            else:
                grupos.append(grupo)

    # Gemini pasó un principio activo como marca ("¿puedo aplicar metsulfuron?", 28/09/2026):
    # si ningún producto tiene ese texto en el nombre, se prueba como principio activo.
    if filtros["marca"] and principio_id is None and not listar_productos_por_filtro(
        conn, marca=filtros["marca"], limite=1
    ).productos:
        principio_id = resolver_entidad_por_nombre(
            conn, "principio_activo", "nombre", filtros["marca"], modelo_embeddings
        )
        if principio_id is not None:
            filtros["principio_activo_id"] = principio_id
            filtros["marca"] = None
            args = args.model_copy(
                update={"principio_activo": args.marca, "marca": None}
            )

    hay_filtro = any(filtros.values()) or bandas_filtro is not None
    for grupo in grupos:
        bandas = grupo["bandas"]
        if bandas == [] or (not hay_filtro and bandas is None):
            grupo["productos"], grupo["total"] = [], 0  # ninguna banda o ningún filtro válido
        else:
            listado = listar_productos_por_filtro(
                conn, **filtros, bandas_permitidas=bandas, limite=mensajes.MAXIMO_LISTADO,
            )
            grupo["productos"], grupo["total"] = listado.productos, listado.total
    listados = grupos

    if cultivo_id is not None or adversidad_id is not None:
        advertencias.append(mensajes.AVISO_SOLO_CON_USOS)
    if any(lst["productos"] for lst in listados):
        citas.insert(0, Cita(fuente="senasa", documento="vademécum"))
    return ResultadoTool(
        estado="ok",
        datos={
            "filtros": {
                "cultivo": _texto(args.cultivo) if cultivo_id else None,
                "adversidad": _texto(args.adversidad) if adversidad_id else None,
                "principio_activo": _texto(args.principio_activo) if principio_id else None,
                "aptitudes": aptitudes or [],
                "firma": _texto(args.firma) if firma_ids else None,
                "marca": _texto(args.marca),
                "bandas": bandas_filtro,
            },
            "localidad": distancia["localidad"] if distancia else None,
            "distancia_m": args.distancia_m if distancia else None,
            "listados": listados,
        },
        citas=citas,
        advertencias=advertencias,
    )


@tool(
    "consultar_productos",
    args_schema=ConsultarProductosArgs,
    description=DESCRIPCION,
    response_format="content_and_artifact",
    return_direct=True,  # ver `orquestador/respuesta_directa.py`
)
def consultar_productos(
    runtime: ToolRuntime,
    cultivo: str | None = None,
    adversidad: str | None = None,
    principio_activo: str | None = None,
    aptitud: str | None = None,
    banda: str | None = None,
    banda_maxima: str | None = None,
    firma: str | None = None,
    marca: str | None = None,
    localidad: str | None = None,
    provincia: str | None = None,
    tipo_aplicacion: str | None = None,
    distancia_m: float | None = None,
) -> tuple[str, ResultadoTool]:
    from fitosanitarios.servicios.recursos import con_conexion_y_modelo

    args = ConsultarProductosArgs(
        cultivo=cultivo, adversidad=adversidad, principio_activo=principio_activo,
        aptitud=aptitud, banda=banda, banda_maxima=banda_maxima, firma=firma, marca=marca,
        localidad=localidad, provincia=provincia, tipo_aplicacion=tipo_aplicacion,
        distancia_m=distancia_m,
    )
    dicho = lo_dicho_en_la_conversacion(runtime.state.get("messages", []))
    resultado = con_conexion_y_modelo(
        lambda conn, modelo: consultar_productos_logica(args, conn, modelo, dicho)
    )
    return mensajes.resumen_para_llm(resultado), resultado

