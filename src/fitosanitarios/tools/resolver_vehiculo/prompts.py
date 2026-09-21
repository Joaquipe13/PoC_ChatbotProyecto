"""Lo que el orquestador (el LLM) lee de esta tool: su descripción y la de sus
argumentos."""

DESCRIPCION = """\
Identifica qué vehículo/equipo de aplicación menciona el operario a
partir de una descripción informal ("la mosquito", "el dron", "la de
arrastre"). Usar cuando el operario nombra el equipo y hace falta saber
cuál es exactamente, por ejemplo antes de `registrar_evento`. No hace
falta llamarla por separado si el operario ya da un nombre exacto del
catálogo: `registrar_evento` la resuelve internamente.

Args:
    descripcion: cómo nombró el operario el vehículo, tal cual lo escribió."""
