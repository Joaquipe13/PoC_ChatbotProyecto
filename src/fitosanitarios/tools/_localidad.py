"""Paso común de las tools de evaluación y de consulta normativa: resolver
dónde se aplica (texto del usuario o de la receta) y qué normativa le
corresponde. Devuelve la `Ubicacion` o el `ResultadoTool` con el que la tool
debe cortar.

Si la localidad no tiene normativa municipal cargada (o no está cargada), se
usa la provincial, y `Ubicacion.con_normativa_municipal` queda en False para
que la respuesta lo aclare. Nunca se supone la provincia: si no se sabe, se
pregunta.
"""

from fitosanitarios.datos.retrievers.territorio import (
    listar_localidades,
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
            f"'{texto}' coincide con más de una localidad", resolucion.ambiguas
        )

    # Localidad sin normativa propia cargada: se recurre a la provincial.
    provincias = listar_provincias(conn)
    if not provincias:
        return None, _no_cubierta()
    buscada = resolver_localidad(provincia or texto, provincias)
    if buscada.localidad is not None:
        return Ubicacion(nombre=texto.strip(), provincia_id=buscada.localidad.id), None
    if provincia:
        return None, _no_cubierta()
    return None, ResultadoTool(
        estado="faltan_datos",
        faltantes=[
            CampoFaltante(
                campo="provincia",
                motivo=(
                    f"no se cuenta con la normativa municipal de '{texto.strip()}'; "
                    "se puede usar la provincial"
                ),
                pregunta_sugerida=(
                    f"No tengo la normativa municipal de {texto.strip()}. ¿En qué provincia "
                    "queda? Con eso me baso en la normativa provincial."
                ),
                tipo_entrada="lista", opciones=[p.nombre for p in provincias],
            )
        ],
    )


def _no_cubierta() -> ResultadoTool:
    return ResultadoTool(estado="no_resuelto", motivo=MotivoNoResuelto.JURISDICCION_NO_CUBIERTA)


def _pedir_localidad(motivo: str, opciones: list[Jurisdiccion]) -> ResultadoTool:
    return ResultadoTool(
        estado="faltan_datos",
        faltantes=[
            CampoFaltante(
                campo="localidad", motivo=motivo,
                pregunta_sugerida="¿En qué localidad o municipio se va a realizar la aplicación?",
                tipo_entrada="lista", opciones=[o.nombre for o in opciones],
            )
        ],
    )
