"""Lo que el orquestador (el LLM) lee de esta tool: su descripción y la de sus
argumentos."""

DESCRIPCION = """\
Valida si un producto puntual está registrado en SENASA y autorizado
para un cultivo. Usar cuando el operario pregunta por UN producto
concreto ("¿el glifo full está habilitado para soja?"). Para pedir un
listado de productos, usar `consultar_productos`.

Args:
    producto_nombre: nombre comercial tal como lo escribió el operario.
    cultivo: cultivo declarado.
    adversidad: plaga/maleza/enfermedad, si se mencionó.
    dosis_valor: valor numérico de la dosis, si se mencionó.
    dosis_unidad: unidad de la dosis ("L/ha", "kg/ha", etc.), si se mencionó."""
