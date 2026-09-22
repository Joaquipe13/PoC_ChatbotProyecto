"""Lo que el orquestador (el LLM) lee de esta tool: su descripción y la de sus
argumentos."""

DESCRIPCION = """\
Banda toxicológica de la aplicación (la más peligrosa de sus productos), distancia
mínima que fija la normativa de la localidad y dosis contra el rango registrado. Para
consultas sueltas, incluso "quiero aplicar Flyer 10 EC a 170 cm3/ha en El Trébol, ¿a
qué distancia de la zona urbana?". El dictamen de una receta confirmada:
`evaluar_viabilidad_legal`. Limitaciones sin producto: `listar_limitaciones`.

Args:
    localidad: donde se va a aplicar.
    provincia: solo si la tool la pidió.
    tipo_aplicacion: "terrestre" o "aerea".
    productos: nombres de los productos.
    cultivo: cultivo declarado.
    dosis_valor: valor numérico de la dosis.
    dosis_unidad: unidad de la dosis ("L/ha", "kg/ha").
    adversidad: plaga, maleza o enfermedad, si la mencionó."""
