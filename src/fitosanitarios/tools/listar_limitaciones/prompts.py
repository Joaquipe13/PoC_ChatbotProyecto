"""Lo que el orquestador (el LLM) lee de esta tool: su descripción y la de sus
argumentos."""

DESCRIPCION = """\
Limitaciones de la normativa de una localidad: a qué distancia de la zona
urbana, escuelas o cursos de agua se puede o no aplicar, según tipo de
aplicación y banda, con norma y artículo. Para "¿qué limitaciones hay en X?",
"¿qué artículo dispone el límite?", "¿a cuánto de la zona urbana puedo fumigar con
avión?", "¿puedo aplicar a 1000 metros bajo alguna condición?" (pasar
`distancia_m`) y "tengo Roundup, ¿a cuánto del pueblo lo puedo tirar?" (pasar
`producto`: la banda sale del registro). También para comparar, en UNA sola
llamada: "¿es lo mismo por avión que por tierra?", "¿qué diferencia hay entre la
mosquito y el avión?" (si nombra dos equipos o dos tipos, sin `tipo_aplicacion`: la
respuesta separa aérea y terrestre) y "¿qué diferencia hay entre banda amarilla y verde?"
(`banda` con las dos: "amarilla y verde"). El texto de un artículo por su número:
`consultar_articulo`. Para evaluar una receta con dosis y cultivo: `evaluar_riesgo`.

Args:
    localidad: la de la consulta o la de la receta en curso.
    provincia: solo si la tool la pidió.
    tipo_aplicacion: el tipo o el equipo tal como lo dijo ("aérea", "terrestre", "avión",
        "mosquito", "drone", "mochila"), si lo dijo. No lo traduzcas: la tool lo interpreta.
    banda: Ia, Ib, II, III, IV o su color (roja, amarilla, azul, verde), solo si el
        operario la dijo; una o varias ("amarilla y verde"). Nunca la supongas por el
        producto: para eso está `producto`.
    tipo_zona: "zona urbana", "escuela" o "curso de agua", si la dijo.
    distancia_m: metros entre el lote y la zona a la que quiere aplicar, si los dio.
        Nunca la dosis ni la superficie.
    producto: nombre comercial del producto, si lo nombró. Su banda sale del registro."""
