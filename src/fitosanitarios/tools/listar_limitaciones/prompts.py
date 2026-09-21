"""Lo que el orquestador (el LLM) lee de esta tool: su descripción y la de sus
argumentos."""

DESCRIPCION = """\
Lista las limitaciones que impone la normativa de una localidad: a qué
distancia de cada zona (zona urbana, escuelas, cursos de agua) se puede o no
aplicar, según tipo de aplicación y banda, con norma y artículo. Usar para: "¿qué
limitaciones hay en El Trébol?", "que restricciones tiene san carlos", "¿qué
artículo dispone el límite?", "¿a cuánto de la zona urbana puedo fumigar con
avión?", y también "¿puedo aplicar a 1000 metros bajo alguna condición?" (pasar
`distancia_m`: responde qué está prohibido a esa distancia y qué excepciones
permitirían aplicar). Para ver el texto de un artículo usar `consultar_articulo`.

Args:
    localidad: localidad o municipio de la consulta, si la dijo o si hay una
        receta en curso.
    provincia: solo si la tool la pidió porque la localidad no está cargada.
    tipo_aplicacion: "terrestre" o "aerea", solo si lo mencionó.
    banda: banda toxicológica (Ia, Ib, II, III, IV) o su color (roja, amarilla,
        azul, verde), solo si la mencionó.
    tipo_zona: zona en cuestión ("zona urbana", "escuela", "curso de agua"), solo si
        la mencionó.
    distancia_m: distancia en metros a la que quiere aplicar, solo si la dio."""
