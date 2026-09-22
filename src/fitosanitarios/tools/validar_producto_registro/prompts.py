"""Lo que el orquestador (el LLM) lee de esta tool: su descripción y la de sus
argumentos."""

DESCRIPCION = """\
Valida si UN producto está registrado en SENASA y autorizado para un cultivo ("¿el
glifo full está habilitado para soja?"). Para un listado: `consultar_productos`.

Args:
    producto_nombre: nombre comercial tal como lo escribió.
    cultivo: cultivo declarado.
    adversidad: plaga, maleza o enfermedad, si la mencionó.
    dosis_valor: valor numérico de la dosis, si lo mencionó.
    dosis_unidad: unidad de la dosis ("L/ha", "kg/ha"), si la mencionó."""
