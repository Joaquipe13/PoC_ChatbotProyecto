"""Lo que el orquestador (el LLM) lee de esta tool: su descripción y la de sus
argumentos."""

DESCRIPCION = """\
Lista productos registrados en SENASA para un cultivo, plaga o
principio activo. Usar cuando el operario pide un listado ("¿qué hay
para yuyo colorado en soja?"), no para preguntar por un producto puntual
(eso es `validar_producto_registro`). Informa lo registrado; no
recomienda qué aplicar.

Args:
    cultivo: cultivo a buscar, si se mencionó.
    adversidad: plaga, maleza o enfermedad a buscar, si se mencionó.
    principio_activo: principio activo a buscar, si se mencionó.
    aptitud: herbicida/insecticida/fungicida/etc., si se mencionó.
    banda_maxima: banda toxicológica más peligrosa a incluir (ej. "III"
        incluye III y IV, no Ia/Ib/II), si se mencionó."""
