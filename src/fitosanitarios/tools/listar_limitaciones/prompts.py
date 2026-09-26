"""Lo que el orquestador (el LLM) lee de esta tool: su descripción y la de sus
argumentos."""

DESCRIPCION = """\
Limitaciones de la normativa de una localidad: a qué distancia de la zona
urbana, escuelas o cursos de agua se puede o no aplicar, según tipo de
aplicación y banda, con norma y artículo. Para "¿qué limitaciones hay en X?",
"¿qué artículo dispone el límite?", "¿a cuánto de la zona urbana puedo fumigar con
avión?", "¿puedo aplicar a 1000 metros bajo alguna condición?" (pasar
`distancia_m`) y "tengo Roundup, ¿a cuánto del pueblo lo puedo tirar?" (pasar
`producto`: la banda sale del registro). El texto de un artículo por su número:
`consultar_articulo`. Para evaluar una receta con dosis y cultivo: `evaluar_riesgo`.

Args:
    localidad: la de la consulta o la de la receta en curso.
    provincia: solo si la tool la pidió.
    tipo_aplicacion: "terrestre" o "aerea", si lo dijo.
    banda: Ia, Ib, II, III, IV o su color (roja, amarilla, azul, verde), si la dijo.
    tipo_zona: "zona urbana", "escuela" o "curso de agua", si la dijo.
    distancia_m: metros entre el lote y la zona a la que quiere aplicar, si los dio.
        Nunca la dosis ni la superficie.
    producto: nombre comercial del producto, si lo nombró y no dijo la banda."""
