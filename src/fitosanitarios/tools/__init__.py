"""Las tools del agente, una carpeta por tool:

    tools/<tool>/
        __init__.py   exporta la tool, sus argumentos y su lógica
        tool.py       el script base: argumentos, lógica y la tool de LangChain
        prompts.py    lo que lee un LLM: la descripción de la tool y, si los hay, sus prompts
        mensajes.py   lo que lee el operario: preguntas, avisos y la plantilla de la respuesta
        utils.py      los auxiliares que solo usa esta tool (si los tiene)

Lo que usan varias tools no está acá sino en `servicios/` (por ejemplo `recursos.py`,
`ubicacion.py`, `conversacion.py`, `formato.py`): una tool no importa de otra. La
convención se verifica en `tests/tools/test_estructura.py`.
"""
