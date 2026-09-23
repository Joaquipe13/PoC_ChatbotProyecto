"""Lo que el orquestador (el LLM) lee de esta tool: su descripción y la de sus
argumentos."""

DESCRIPCION = """\
Completa o corrige la receta leída de la foto con los datos que da el operario, y le
muestra la receta entera para confirmar. Usar cuando responde los datos que faltaban
("soja, en Sastre") o corrige uno ("la dosis es 200 cc"). Pasar solo lo que dijo.

Args:
    cultivo, lote, localidad, tipo_aplicacion ("terrestre" o "aerea"), adversidad:
        tal como los dijo.
    superficie_ha: hectáreas, si las dio.
    dosis: la dosis de cada producto que dio, con el nombre del producto si lo nombró."""
