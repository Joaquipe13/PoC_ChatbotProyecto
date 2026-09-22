"""Lo que el orquestador (el LLM) lee de esta tool: su descripción y la de sus
argumentos. Es el "cuándo usar" y el cómo completar cada dato (ver
`orquestador/prompt_sistema.py`: el detalle de cada tool va acá, no en el prompt)."""

DESCRIPCION = """\
Agenda la aplicación de la receta cuando el operario lo pide ("agendala", "agendala
para el martes"). La tool pregunta lo que falta: no inventes ni calcules fechas.

Args:
    fecha: el día tal como lo dijo ("martes", "25/09"), sin convertirlo; si no dijo
        ninguno, no completar. Si una respuesta anterior de la tool informó
        `fecha=AAAA-MM-DD`, pasar esa.
    hora: el horario tal como lo dijo ("8", "3 de la tarde"); si no lo dijo, no completar.
    numero: número de la receta, si se conoce.
    cultivo: cultivo de la receta, si se conoce.
    lote: lote de la receta, si se conoce.
    superficie_ha: superficie en hectáreas, si se conoce.
    tipo_aplicacion: "terrestre" o "aerea", si se conoce."""
