"""Paso común de las tools de evaluación y de consulta normativa: resolver
dónde se aplica (texto del usuario o de la receta) y qué normativa le
corresponde. Devuelve la `Ubicacion` o el `ResultadoTool` con el que la tool
debe cortar.

Si la localidad no tiene normativa municipal cargada pero es un municipio o
comuna conocido (`territorio.municipio`), se usa la provincial, y
`Ubicacion.con_normativa_municipal` queda en False para que la respuesta lo
aclare. Una localidad desconocida se vuelve a pedir: nunca se adivina.
"""

from fitosanitarios.datos.retrievers.territorio import (
    listar_localidades,
    listar_municipios,
    listar_provincias,
    localidad_tiene_normativa_municipal,
)
from fitosanitarios.dominio.modelos import CampoFaltante, ResultadoTool
from fitosanitarios.dominio.motivos import MotivoNoResuelto
from fitosanitarios.servicios.localidad import Jurisdiccion, Ubicacion, resolver_localidad


def resolver_ubicacion_o_cortar(
    conn, texto: str | None, provincia: str | None = None
) -> tuple[Ubicacion | None, ResultadoTool | None]:
    cargadas = listar_localidades(conn)

    if not texto or not texto.strip():
        return None, _pedir_localidad(
            "no se indicó la localidad donde se va a aplicar", cargadas
        )

    resolucion = resolver_localidad(texto, cargadas)
    if resolucion.localidad is not None:
        loc = resolucion.localidad
        return Ubicacion(
            nombre=loc.nombre, provincia_id=loc.provincia_id, localidad_id=loc.id,
            jurisdiccion_id=loc.jurisdiccion_id,
            con_normativa_municipal=localidad_tiene_normativa_municipal(conn, loc.id),
        ), None
    if resolucion.ambiguas:
        return None, _pedir_localidad(
            f"'{texto}' coincide con más de una localidad", resolucion.ambiguas,
            "Hay varias con ese nombre. ¿Cuál es?",
        )

    # Sin normativa propia cargada: si es un municipio o comuna conocido de una
    # provincia con normativa, se usa la provincial. El servicio opera solo en
    # esas provincias, así que no se pregunta cuál es: un nombre que no figura
    # se vuelve a pedir.
    if provincia and resolver_localidad(provincia, listar_provincias(conn)).localidad is None:
        return None, _no_cubierta()
    municipios = resolver_localidad(texto, listar_municipios(conn))
    if municipios.localidad is not None:
        m = municipios.localidad
        return Ubicacion(nombre=m.nombre, provincia_id=m.provincia_id), None
    if municipios.ambiguas:
        return None, _pedir_localidad(
            f"'{texto}' coincide con más de una localidad", municipios.ambiguas,
            "Hay varias con ese nombre. ¿Cuál es?",
        )
    return None, ResultadoTool(
        estado="faltan_datos",
        faltantes=[
            CampoFaltante(
                campo="localidad",
                motivo=f"'{texto.strip()}' no figura entre los municipios y comunas cargados",
                pregunta_sugerida=(
                    f"No encontré '{texto.strip()}' entre las localidades de Santa Fe "
                    "(solo opero ahí). ¿En qué localidad se aplica?"
                ),
                tipo_entrada="texto",
            )
        ],
    )


def _no_cubierta() -> ResultadoTool:
    return ResultadoTool(estado="no_resuelto", motivo=MotivoNoResuelto.JURISDICCION_NO_CUBIERTA)


def _pedir_localidad(
    motivo: str, opciones: list[Jurisdiccion], pregunta: str = "¿En qué localidad se aplica?"
) -> ResultadoTool:
    return ResultadoTool(
        estado="faltan_datos",
        faltantes=[
            CampoFaltante(
                campo="localidad", motivo=motivo,
                pregunta_sugerida=pregunta,
                tipo_entrada="lista", opciones=[o.nombre for o in opciones],
            )
        ],
    )
