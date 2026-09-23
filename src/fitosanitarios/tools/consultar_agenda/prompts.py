"""Lo que el orquestador (el LLM) lee de esta tool: su descripción y la de sus
argumentos."""

DESCRIPCION = """\
Tareas del operario para uno o varios días, con su estado ("¿qué tengo para hoy?",
"¿qué me toca mañana?", "la agenda semanal", "¿y el jueves y el viernes?").

Args:
    fecha: el día o los días tal como los dijo ("martes", "jueves y viernes",
        "semanal", "del 24/09 al 26/09"), sin convertirlos ni partirlos en varias
        llamadas; si no pidió uno distinto de hoy, no completar."""
