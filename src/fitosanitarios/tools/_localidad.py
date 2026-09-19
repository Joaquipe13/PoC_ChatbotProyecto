"""Paso común de `evaluar_riesgo` y `evaluar_viabilidad_legal`: resolver la
localidad (texto del usuario o de la receta) contra las cargadas. Devuelve la
localidad o el `ResultadoTool` con el que la tool debe cortar."""

from fitosanitarios.datos.retrievers.territorio import listar_localidades
from fitosanitarios.dominio.modelos import CampoFaltante, ResultadoTool
from fitosanitarios.dominio.motivos import MotivoNoResuelto
from fitosanitarios.servicios.localidad import Jurisdiccion, resolver_localidad


def resolver_localidad_o_cortar(
    conn, texto: str | None
) -> tuple[Jurisdiccion | None, ResultadoTool | None]:
    cargadas = listar_localidades(conn)

    if not texto or not texto.strip():
        return None, _pedir_localidad(
            "no se indicó la localidad donde se va a aplicar", cargadas
        )

    resolucion = resolver_localidad(texto, cargadas)
    if resolucion.localidad is not None:
        return resolucion.localidad, None
    if resolucion.ambiguas:
        return None, _pedir_localidad(
            f"'{texto}' coincide con más de una localidad", resolucion.ambiguas
        )
    return None, ResultadoTool(
        estado="no_resuelto", motivo=MotivoNoResuelto.JURISDICCION_NO_CUBIERTA
    )


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
