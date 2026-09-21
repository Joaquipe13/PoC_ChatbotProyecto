"""Lo que el LLM lee en esta tool: la descripción para el orquestador y los prompts
del LLM que redacta la respuesta a partir de los fragmentos recuperados."""

DESCRIPCION = """\
Responde una pregunta puntual sobre normativa de aplicación de
fitosanitarios en una localidad cargada, citando artículo y norma. Usar
para dudas de contenido ("¿hay que avisar antes de aplicar?", "¿qué
obligaciones tiene el aplicador?", "¿se puede aplicar de noche?"). No usar para
preguntas de distancias o limitaciones ("¿a cuántos metros de una escuela puedo
aplicar?", "¿qué límites hay en X?": `listar_limitaciones`), ni para el texto de un
artículo por su número (`consultar_articulo`), ni para el dictamen de una receta
(`evaluar_viabilidad_legal`).

Args:
    pregunta: la pregunta tal como la escribió el operario.
    jurisdiccion_id: localidad de la consulta (explícita o de la receta
        en curso), si se conoce.
    provincia: provincia de la localidad, solo si la tool la pidió porque
        la localidad no tiene normativa municipal cargada (se usa la
        provincial y se aclara).
    tipo_aplicacion: "terrestre" o "aerea", si se mencionó.
    tipo_zona: tipo de zona protegida en cuestión, si se mencionó."""

PROMPT_SISTEMA_CONSULTA_NORMATIVA = (
    "Sos un asistente que responde preguntas sobre normativa de aplicación de "
    "fitosanitarios en Argentina, usando ÚNICAMENTE los fragmentos de artículo "
    "que se te dan en el mensaje. Nunca respondas con información que no esté "
    "en esos fragmentos, aunque la sepas de otra fuente. Si ningún fragmento "
    "responde la pregunta, decilo explícitamente.\n\n"
    "Respondé ÚNICAMENTE un JSON (sin texto alrededor, sin markdown) con esta "
    "forma exacta:\n"
    '{"veredicto": "Si" | "No" | "Depende", "regla": "una oración en español '
    'con la regla aplicable", "articulos_citados": [{"norma": string, '
    '"articulo": string}, ...]}\n\n'
    "\"articulos_citados\" tiene que listar exactamente los artículos (norma + "
    "número, tal como aparecen en los fragmentos) que usaste para responder. "
    "Si no hay fragmentos suficientes, poné \"veredicto\": \"Depende\", "
    "explicá en \"regla\" que no hay información suficiente, y dejá "
    "\"articulos_citados\" vacío."
)

# Cómo se le presenta al LLM la pregunta y cada fragmento de artículo recuperado.
PLANTILLA_PROMPT_USUARIO = "Pregunta: {pregunta}\n\nFragmentos disponibles:\n{contexto}"
PLANTILLA_FRAGMENTO = "[{norma}, art. {numero}, jurisdicción: {jurisdiccion_id}]\n{texto}"
