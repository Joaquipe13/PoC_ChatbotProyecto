"""Lo que el orquestador (el LLM) lee de esta tool: su descripción y la de sus
argumentos."""

DESCRIPCION = """\
Tareas del operario para un día, con su estado ("¿qué tengo para hoy?", "¿qué me toca
mañana?").

Args:
    fecha: el día tal como lo dijo ("martes", "25/09"), sin convertirlo; si no pidió
        uno distinto de hoy, no completar."""
