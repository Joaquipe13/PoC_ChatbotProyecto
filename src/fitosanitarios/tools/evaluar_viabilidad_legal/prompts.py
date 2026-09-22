"""Lo que el orquestador (el LLM) lee de esta tool: su descripción y la de sus
argumentos."""

DESCRIPCION = """\
Dictamen completo (APTA/OBSERVADA/NO EVALUABLE) de una receta ya confirmada por el
operario, con la banda de la aplicación y la distancia mínima a cada zona según la
normativa de la localidad.

Args:
    localidad: donde se va a aplicar.
    provincia: solo si la tool la pidió.
    tipo_aplicacion: "terrestre" o "aerea".
    productos: productos con su dosis declarada.
    cultivo: cultivo declarado.
    adversidad: plaga, maleza o enfermedad, si la mencionó.
    superficie_ha: superficie en hectáreas, si la mencionó."""
