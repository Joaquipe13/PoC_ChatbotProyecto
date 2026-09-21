"""Lo que el orquestador (el LLM) lee de esta tool: su descripción y la de sus
argumentos."""

DESCRIPCION = """\
Informa la banda toxicológica de la aplicación (la más peligrosa entre
sus productos) y la distancia mínima que fija la normativa de la
localidad, más la dosis contra el rango registrado. No usa la ubicación
exacta del lote. Usar para consultas sueltas; para el dictamen completo de
una receta confirmada usar `evaluar_viabilidad_legal`.

Args:
    localidad: localidad o municipio donde se va a aplicar.
    provincia: provincia de la localidad, solo si la tool la pidió porque la
        localidad no tiene normativa municipal cargada (se usa la provincial).
    tipo_aplicacion: "terrestre" o "aerea".
    productos: nombres de los productos a aplicar.
    cultivo: cultivo declarado.
    dosis_valor: valor numérico de la dosis.
    dosis_unidad: unidad de la dosis ("L/ha", "kg/ha", etc.).
    adversidad: plaga/maleza/enfermedad, si se mencionó."""
