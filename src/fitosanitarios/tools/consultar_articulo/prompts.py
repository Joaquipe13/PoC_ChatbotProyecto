"""Lo que el orquestador (el LLM) lee de esta tool: su descripción y la de sus
argumentos."""

DESCRIPCION = """\
Muestra el texto literal de un artículo de la normativa, buscándolo por su
número. Usar cuando piden ver o leer un artículo puntual: "¿qué dice el
artículo 33?", "q dice el art 6 de la ordenanza 841", "leeme el 51 de la ley
11273", "mostrame el articulo 34". No usar para preguntas de contenido sin número
("¿a cuántos metros de una escuela puedo aplicar?": `responder_consulta_normativa`)
ni para listar las limitaciones (`listar_limitaciones`).

Args:
    numero_articulo: el número que pidió, solo el número o con "bis" ("33", "5 bis").
    norma: la norma a la que se refiere, tal como la nombró ("ley 11273",
        "ordenanza 841/2010"), si la nombró. Si el número está en varias normas y
        no la nombró, la tool pregunta cuál.
    localidad: localidad de la consulta, si la dijo o si hay una receta en curso.
        Sin localidad se busca en la normativa provincial y nacional.
    provincia: solo si la tool la pidió porque la localidad no está cargada."""
