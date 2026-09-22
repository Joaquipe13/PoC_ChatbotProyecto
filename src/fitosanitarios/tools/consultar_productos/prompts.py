"""Lo que el orquestador (el LLM) lee de esta tool: su descripción y la de sus
argumentos."""

DESCRIPCION = """\
Lista productos registrados en SENASA para un cultivo, plaga o principio activo
("¿qué hay para yuyo colorado en soja?"). Para UN producto puntual:
`validar_producto_registro`. Informa lo registrado, no recomienda.

Args:
    cultivo: cultivo a buscar, si lo mencionó.
    adversidad: plaga, maleza o enfermedad, si la mencionó.
    principio_activo: principio activo, si lo mencionó.
    aptitud: herbicida, insecticida, fungicida, etc., si la mencionó.
    banda_maxima: banda más peligrosa a incluir ("III" incluye III y IV), si la mencionó."""
