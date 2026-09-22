"""Lo que el orquestador (el LLM) lee de esta tool: su descripción y la de sus
argumentos."""

DESCRIPCION = """\
Registra el inicio o el fin de una aplicación real en el campo: "iniciar" cuando
avisa que empieza (con qué vehículo y en qué lote), "finalizar" cuando avisa que
terminó. No evalúa si es viable aplicar (`evaluar_viabilidad_legal`).

Args:
    accion: "iniciar" o "finalizar".
    vehiculo: equipo con el que aplica, tal cual lo describió (solo para "iniciar").
    lote: lote donde aplica (solo para "iniciar").
    receta_id: id de la receta ya evaluada a la que corresponde, si la hay."""
