"""Lo que el orquestador (el LLM) lee de esta tool: su descripción y la de sus
argumentos."""

DESCRIPCION = """\
Valida si UN producto está registrado en SENASA y autorizado para un cultivo ("¿el
glifo full está habilitado para soja?"), o dice su banda toxicológica (color) y su
registro ("¿qué banda tiene el Tordon D 30?", "¿el Roundup es banda verde?"). Para un
listado: `consultar_productos`.

Args:
    producto_nombre: nombre comercial tal como lo escribió.
    cultivo: cultivo declarado, si lo mencionó (para la banda no hace falta).
    adversidad: plaga, maleza o enfermedad, si la mencionó.
    dosis_valor: valor numérico de la dosis, si lo mencionó.
    dosis_unidad: unidad de la dosis ("L/ha", "kg/ha"), si la mencionó."""
