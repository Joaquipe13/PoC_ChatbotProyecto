"""Lo que el LLM lee en esta tool: la descripción para el orquestador y los prompts
del LLM que redacta la respuesta a partir de los fragmentos recuperados."""

DESCRIPCION = """\
Responde una pregunta de contenido sobre la normativa de aplicación en una localidad
cargada, citando norma y artículo: leyes, ordenanzas y fallos judiciales ("¿hay que
avisar antes de aplicar?", "¿se puede aplicar de noche?", "¿qué dice el fallo de
Sastre?"). No para la lista de distancias o límites (`listar_limitaciones`), ni para el
texto de un artículo por su número (`consultar_articulo`), ni para el dictamen de una
receta (`evaluar_viabilidad_legal`).

Args:
    pregunta: tal como la escribió el operario.
    jurisdiccion_id: localidad de la consulta o de la receta en curso, si se conoce.
    provincia: solo si la tool la pidió.
    tipo_aplicacion: "terrestre" o "aerea", si lo mencionó.
    tipo_zona: zona protegida en cuestión, si la mencionó."""

PROMPT_SISTEMA_CONSULTA_NORMATIVA = (
    "Sos un asistente que responde preguntas sobre normativa de aplicación de "
    "fitosanitarios en Argentina, usando ÚNICAMENTE los fragmentos de normativa "
    "(artículos de leyes y ordenanzas, fallos judiciales y reglas de distancia ya "
    "cargadas) que se te dan en el mensaje. Nunca respondas con información que no esté "
    "en esos fragmentos, aunque la sepas de otra fuente. Si ningún fragmento "
    "responde la pregunta, decilo explícitamente.\n\n"
    "Respondé ÚNICAMENTE un JSON (sin texto alrededor, sin markdown) con esta "
    "forma exacta:\n"
    '{"veredicto": "Si" | "No" | "Depende", "regla": "una oración en español '
    'con la regla aplicable", "articulos_citados": [{"norma": string, '
    '"articulo": string}, ...]}\n\n'
    "\"articulos_citados\" tiene que listar exactamente los fragmentos (norma + "
    "número de artículo, tal como aparecen en los fragmentos; \"\" si el fragmento "
    "no tiene artículo) que usaste para responder. La \"regla\" es una oración "
    "propia, sin copiar el texto de la norma. "
    "Si no hay fragmentos suficientes, poné \"veredicto\": \"Depende\", "
    "explicá en \"regla\" que no hay información suficiente, y dejá "
    "\"articulos_citados\" vacío."
)

# Cómo se le presenta al LLM la pregunta y cada fragmento de artículo recuperado.
PLANTILLA_PROMPT_USUARIO = "Pregunta: {pregunta}\n\nFragmentos disponibles:\n{contexto}"
PLANTILLA_FRAGMENTO = "[{norma}, {referencia}, jurisdicción: {jurisdiccion_id}]\n{texto}"
