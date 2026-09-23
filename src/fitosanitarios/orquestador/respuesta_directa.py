"""Turnos que terminan en la tool, sin una segunda llamada al modelo.

Con una tool, un turno hacía dos llamadas a Gemini: una para invocarla y otra solo para
elegir el `tipo` de la respuesta (el texto lo arma el formateador con los datos de la tool).
Cada llamada reenvía los esquemas de las tools y el prompt, unos 4k tokens: la segunda era
casi la mitad del costo del turno y una petición más contra el límite de la API gratuita.

Las tools que tienen un único tipo de respuesta se declaran `return_direct=True`: el agente
termina apenas se ejecutan y el `tipo` sale de este módulo. `evaluar_riesgo` (dictamen o
detalle de bandas según lo que se venga hablando) y `resolver_vehiculo` (alimenta a otra
tool) siguen pasando por el modelo.
"""

from fitosanitarios.dominio.modelos import RespuestaAgente, ResultadoTool

TIPO_POR_TOOL = {
    "leer_receta": "confirmacion_receta",
    "completar_receta": "confirmacion_receta",
    "validar_producto_registro": "consulta_producto",
    "consultar_productos": "consulta_producto",
    "consultar_marbete": "consulta_marbete",
    "evaluar_viabilidad_legal": "dictamen",
    "responder_consulta_normativa": "consulta_normativa",
    "consultar_articulo": "consulta_articulo",
    "listar_limitaciones": "limitaciones",
    "registrar_evento": "evento_registrado",
    "consultar_agenda": "agenda",
    "agendar_aplicacion": "agendar_aplicacion",
}

# Su plantilla ya sabe mostrar qué falta (además de la pregunta muestra, p. ej., la agenda del día).
_MUESTRAN_SUS_FALTANTES = ("agendar_aplicacion",)


def respuesta_de_las_tools(
    nombres: list[str], resultados: list[ResultadoTool]
) -> RespuestaAgente | None:
    """La `RespuestaAgente` de un turno que terminó en sus tools. `nombres`: las tools que
    dieron un resultado, en orden; `resultados`: esos resultados. `None` si no hay ninguno
    (la tool falló antes de devolver algo, por argumentos inválidos): ahí tiene que volver a
    decidir el modelo."""
    if not resultados or any(n not in TIPO_POR_TOOL for n in nombres):
        return None

    sin_datos = [r for r in resultados if not r.datos]
    if any(r.estado == "no_resuelto" for r in sin_datos):
        return RespuestaAgente(tipo="no_resuelto")
    if any(r.estado == "faltan_datos" and r.faltantes for r in sin_datos):
        if not all(n in _MUESTRAN_SUS_FALTANTES for n in nombres):
            return RespuestaAgente(tipo="repregunta")
    return RespuestaAgente(tipo=TIPO_POR_TOOL[nombres[0]])
