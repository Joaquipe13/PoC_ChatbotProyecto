"""Lo que el orquestador (el LLM) lee de esta tool: su descripción y la de sus
argumentos."""

DESCRIPCION = """\
Devuelve las tareas del operario para un día (recetas con fecha
prevista para ese día, con su estado). Usar cuando pide su agenda o plan
del día ("¿qué tengo para hoy?", "¿qué me toca aplicar mañana?").

Args:
    fecha: el día tal como lo dijo el operario ("martes", "mañana",
        "25/09"), sin convertirlo, solo si pidió uno distinto de hoy; si
        no lo dijo, no completar este argumento (se usa hoy por defecto)."""
