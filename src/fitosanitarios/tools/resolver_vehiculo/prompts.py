"""Lo que el orquestador (el LLM) lee de esta tool: su descripción y la de sus
argumentos."""

DESCRIPCION = """\
Identifica qué vehículo o equipo menciona el operario ("la mosquito", "el dron"). No
hace falta llamarla antes de `registrar_evento`: la resuelve internamente.

Args:
    descripcion: cómo nombró el vehículo, tal cual."""
