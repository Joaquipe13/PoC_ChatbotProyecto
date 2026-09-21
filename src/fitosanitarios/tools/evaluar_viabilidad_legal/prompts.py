"""Lo que el orquestador (el LLM) lee de esta tool: su descripción y la de sus
argumentos."""

DESCRIPCION = """\
Emite el dictamen completo (APTA/OBSERVADA/NO EVALUABLE) de una
receta ya confirmada por el operario e informa la banda de la aplicación
y la distancia mínima a zona urbana y otras zonas que fija la normativa
de la localidad (no usa la ubicación exacta del lote). Requiere los
mismos datos que `validar_producto_registro` y `evaluar_riesgo` juntos.

Args:
    localidad: localidad o municipio donde se va a aplicar.
    provincia: provincia de la localidad, solo si la tool la pidió porque la
        localidad no tiene normativa municipal cargada (se usa la provincial).
    tipo_aplicacion: "terrestre" o "aerea".
    productos: lista de productos con su dosis declarada.
    cultivo: cultivo declarado.
    adversidad: plaga/maleza/enfermedad, si se mencionó.
    superficie_ha: superficie del lote en hectáreas, si se mencionó."""
