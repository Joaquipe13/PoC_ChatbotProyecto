"""Lo que el orquestador (el LLM) lee de esta tool: su descripción y la de sus
argumentos."""

DESCRIPCION = """\
Muestra el texto literal de un artículo de la normativa, por su número ("¿qué dice el
art 33?", "leeme el 51 de la ley 11273"). Preguntas de contenido sin número:
`responder_consulta_normativa`. Limitaciones: `listar_limitaciones`.

Args:
    numero_articulo: solo el número, o con "bis" ("33", "5 bis").
    norma: la norma tal como la nombró ("ley 11273", "ordenanza 841/2010"), si la
        nombró; si el número está en varias normas y no la nombró, la tool pregunta.
    localidad: la de la consulta o la de la receta en curso; sin localidad se busca
        en la normativa provincial y nacional.
    provincia: solo si la tool la pidió."""
