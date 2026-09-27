"""Lo que el orquestador (el LLM) lee de esta tool: su descripción y la de sus
argumentos."""

DESCRIPCION = """\
Valida si UN producto está registrado en SENASA y autorizado para un cultivo ("¿el
glifo full está habilitado para soja?"), su dosis registrada para ese cultivo ("¿cuál
es la dosis de Flyer para soja?", o "¿cuál es la dosis correcta?" después de un aviso de
dosis: con el producto y el cultivo de la conversación), o su banda toxicológica (color)
y su registro ("¿qué banda tiene el Tordon D 30?"). Para un listado:
`consultar_productos`.

Args:
    producto_nombre: nombre comercial tal como lo escribió.
    cultivo: cultivo declarado, si lo mencionó (para la banda no hace falta).
    adversidad: plaga, maleza o enfermedad, si la mencionó.
    dosis_valor: valor numérico de la dosis, si lo mencionó.
    dosis_unidad: unidad de la dosis ("L/ha", "kg/ha"), si la mencionó."""
