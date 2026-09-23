"""Los mensajes de esta tool: lo que pregunta si el producto es ambiguo y cómo se le
muestra al operario lo que dice el marbete (la plantilla del tipo de respuesta
`consulta_marbete`)."""

from fitosanitarios.dominio.modelos import RespuestaAgente, ResultadoTool
from fitosanitarios.servicios.formato import primer_dato, seccion_fuentes, todas_las_citas

ADVERTENCIA_SIN_JSON = "El modelo no devolvió una respuesta interpretable"


def pregunta_producto_ambiguo(nombre: str) -> str:
    return f"Hay varios productos parecidos a '{nombre}'. ¿Cuál es?"


def motivo_producto_ambiguo(nombre: str) -> str:
    return f"'{nombre}' coincide con varios productos"


def advertencia_pagina_descartada(pagina) -> str:
    return f"Se descartó una cita a la página {pagina}, que no estaba entre lo recuperado"


def resumen_para_llm(resultado: ResultadoTool) -> str:
    texto = f"consultar_marbete: estado={resultado.estado}"
    if resultado.faltantes:
        campos = ", ".join(f.campo for f in resultado.faltantes)
        texto += (
            f". Falta: {campos}. Preguntáselo al operario y no vuelvas a llamar la tool "
            "hasta que responda"
        )
    return texto


def plantilla_consulta_marbete(
    respuesta: RespuestaAgente, resultados: list[ResultadoTool]
) -> str:
    datos = primer_dato(resultados) or {}
    titulo = f"*{datos.get('marca', '')}* · Reg. SENASA {datos.get('numero_inscripcion', '')}"
    fuentes = seccion_fuentes(todas_las_citas(resultados))
    return "\n\n".join(p for p in (f"{titulo}\n{datos.get('respuesta', '')}", fuentes) if p)
