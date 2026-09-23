"""Lo que el LLM lee en esta tool: la descripción para el orquestador y los prompts del
LLM que redacta la respuesta a partir de los fragmentos del marbete."""

DESCRIPCION = """\
Responde qué dice el marbete (la etiqueta aprobada por SENASA) de un producto: tiempo de
carencia, precauciones, compatibilidad o mezclas, reingreso al lote, primeros auxilios,
modo de aplicación ("¿qué carencia tiene Flyer en soja?", "¿se puede mezclar con
glifosato?"). No para si está registrado o autorizado para un cultivo
(`validar_producto_registro`), ni para listar productos (`consultar_productos`).

Args:
    producto: el nombre comercial tal como lo dijo.
    pregunta: tal como la escribió el operario."""

# Reformulación de la pregunta antes de buscar (el paso "contextualizar la pregunta" del
# notebook de RAG de la cursada): el operario pregunta "¿cuándo puedo volver a entrar al
# lote?" y el marbete dice "reingresar al área tratada".
RESPUESTA_FUERA_DE_TEMA = "FUERA"
PROMPT_REFORMULACION = (
    "Reescribís preguntas de operarios rurales para buscar la respuesta en el marbete "
    "(la etiqueta aprobada por SENASA) de un producto fitosanitario. Devolvé una sola línea "
    "con la pregunta en palabras simples seguida de los términos técnicos y sinónimos que "
    "usaría el marbete para ese tema (por ejemplo: 'volver a entrar al lote' -> reingreso, "
    "reingresar al área tratada, período de reingreso). No agregues datos, números ni "
    "respuestas: solo palabras para buscar. Sin comillas ni explicaciones. Si la pregunta "
    f"no es sobre el producto, su uso, sus riesgos o su manejo, respondé solo "
    f"{RESPUESTA_FUERA_DE_TEMA}."
)

PROMPT_SISTEMA_MARBETE = (
    "Sos un asistente que responde preguntas sobre el marbete (la etiqueta aprobada por "
    "SENASA) de un producto fitosanitario, usando ÚNICAMENTE los fragmentos del marbete "
    "que se te dan en el mensaje. Nunca respondas con información que no esté en esos "
    "fragmentos, aunque la sepas de otra fuente. No copies el texto del marbete: resumilo "
    "en una o dos oraciones, con los números tal como aparecen.\n\n"
    "Respondé ÚNICAMENTE un JSON (sin texto alrededor, sin markdown) con esta forma "
    'exacta:\n{"respuesta": "una o dos oraciones en español", "paginas_citadas": '
    "[números de página de los fragmentos que usaste]}\n\n"
    "Si ningún fragmento responde la pregunta, poné en \"respuesta\" que el marbete no lo "
    "dice y dejá \"paginas_citadas\" vacío."
)

PLANTILLA_PROMPT_USUARIO = (
    "Producto: {producto}\nPregunta: {pregunta}\n\nFragmentos del marbete:\n{contexto}"
)
PLANTILLA_FRAGMENTO = "[página {pagina}]\n{texto}"
