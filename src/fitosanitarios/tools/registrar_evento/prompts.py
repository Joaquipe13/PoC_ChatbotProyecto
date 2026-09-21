"""Lo que el orquestador (el LLM) lee de esta tool: su descripción y la de sus
argumentos."""

DESCRIPCION = """\
Registra el inicio o el fin de una aplicación real en el campo. Usar
"iniciar" cuando el operario avisa que va a empezar o está empezando a
aplicar (con qué vehículo y en qué lote); usar "finalizar" cuando avisa
que terminó. No confundir con el dictamen (`evaluar_viabilidad_legal`):
esto registra que se aplicó, no evalúa si es viable aplicar.

Args:
    accion: "iniciar" o "finalizar".
    vehiculo: con qué vehículo/equipo aplica, tal cual lo describió
        (requerido solo para "iniciar").
    lote: el lote donde aplica (requerido solo para "iniciar").
    receta_id: si esta aplicación corresponde a una receta ya evaluada,
        su id (opcional)."""
