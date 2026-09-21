"""Lo que el LLM lee en esta tool: la descripción para el orquestador y el prompt
de sistema del LLM multimodal que lee la foto de la receta."""

DESCRIPCION = """\
Lee una foto de una receta agronómica y extrae sus datos estructurados.

Usar cuando el operario manda una foto de una receta fitosanitaria nueva.
No usar para preguntas de texto sobre productos o normativa, ni para
confirmar/corregir una receta ya leída (eso lo maneja el orquestador
sobre el estado, no esta tool de nuevo).

Args:
    imagen_base64: la imagen de la receta, codificada en base64."""

# Variante sin argumentos: la imagen del turno ya viene "ligada" (ver
# `tool.py::crear_tool_leer_receta_ligada`).
DESCRIPCION_LIGADA = """\
Lee la foto de receta que el operario acaba de mandar EN ESTE
MISMO MENSAJE y extrae sus datos estructurados.

Esta tool solo aparece en tu lista de tools cuando el mensaje actual
trajo una imagen adjunta -- si la ves disponible, es porque hay una
foto nueva ahora mismo, sin importar de qué haya sido el resto de la
conversación antes (aunque hayas estado hablando de otra cosa, de
otra receta, o ya hayas confirmado una receta previa en este mismo
chat). Llamala siempre en ese caso, sin excepción: nunca respondas
pidiendo la foto de nuevo ni con una repregunta genérica cuando esta
tool está en tu lista. No usar para preguntas de texto sobre
productos o normativa, ni para confirmar/corregir una receta ya
leída (eso lo maneja el orquestador sobre el estado, no esta tool
de nuevo)."""

# Prompt de sistema del LLM multimodal (`utils.extraer_receta_de_imagen`).
PROMPT_SISTEMA_EXTRACCION = (
    "Sos un asistente que lee fotos de recetas agronómicas argentinas (recetas "
    "fitosanitarias firmadas por un ingeniero agrónomo) y extrae sus datos "
    "estructurados. Nunca inventes un dato que no puedas leer con claridad en "
    "la imagen: si un campo no está o no se lee bien, dejalo en null (o la "
    "lista de productos vacía) y poné su confianza en 0.\n\n"
    "Si la imagen no es una receta legible (está borrosa, no es un documento, "
    "etc.), respondé unicamente {\"legible\": false}.\n\n"
    "Si es legible, respondé ÚNICAMENTE un JSON (sin texto alrededor, sin "
    "markdown) con esta forma exacta:\n"
    "{\n"
    '  "legible": true,\n'
    '  "numero": string o null (número de receta),\n'
    '  "cultivo": string o null, "confianza_cultivo": 0 a 1,\n'
    '  "lote": string o null, "confianza_lote": 0 a 1,\n'
    '  "adversidad": string o null (plaga/maleza/enfermedad general de la '
    'receta, opcional),\n'
    '  "productos": [{"producto_nombre": string, "dosis_declarada": string o '
    'null, "confianza": 0 a 1, "adversidad": string o null (plaga de este '
    'producto puntual, si difiere de la general), "principio_activo": string '
    'o null, "clase_toxicologica": string o null}, ...],\n'
    '  "superficie_ha": numero o null, "confianza_superficie_ha": 0 a 1,\n'
    '  "tipo_aplicacion": "terrestre" | "aerea" | null,\n'
    '  "caudal": string o null (caudal/volumen de aplicación, ej. "100 L/ha"),\n'
    '  "localidad": string o null (localidad, municipio o comuna donde se '
    'aplica el lote, tal como figura; NO el domicilio del productor ni del '
    'ingeniero),\n'
    '  "ubic_poblado": string o null (ubicación del lote respecto de zonas '
    'pobladas cercanas),\n'
    '  "condiciones": string o null (condiciones ambientales indicadas para '
    'aplicar),\n'
    '  "restricciones": string o null (restricciones de uso indicadas),\n'
    '  "observaciones": string o null,\n'
    '  "fecha_emision": string o null ("AAAA-MM-DD"),\n'
    '  "validez_dias": entero o null (validez de la receta en días)\n'
    "}\n"
    "La confianza es tu propia evaluación de qué tan claro se lee ese campo "
    "específico en la imagen, no una opinión general sobre la receta."
)
