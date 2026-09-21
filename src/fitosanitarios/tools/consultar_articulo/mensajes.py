"""Los mensajes de esta tool: lo que pregunta, lo que avisa y cómo se le muestra el
artículo al operario (la plantilla del tipo de respuesta `consulta_articulo`)."""

from fitosanitarios.dominio.modelos import RespuestaAgente, ResultadoTool
from fitosanitarios.servicios.formato import norma_legible, primer_dato, unir_secciones

# --- preguntas y avisos de la tool ---

MOTIVO_SIN_NUMERO = "no se indicó qué número de artículo consultar"
PREGUNTA_NUMERO = "¿Qué número de artículo querés ver?"
ADVERTENCIA_SIN_LOCALIDAD = (
    "Busqué en la normativa provincial y nacional. Si es de una ordenanza, decime la localidad"
)
ADVERTENCIA_OCR = "El texto viene de un documento escaneado y puede tener errores de lectura"


def etiqueta_norma(archivo: str, jurisdiccion_id: str) -> str:
    """Cómo se le ofrece una norma al operario: "Ley 11273/1995 (santa-fe)"."""
    return f"{norma_legible(archivo)} ({jurisdiccion_id})"


def advertencia_sin_normativa_municipal(localidad: str) -> str:
    return (
        f"No se cuenta con la normativa municipal de {localidad}: se busca en la "
        "normativa provincial y nacional"
    )


def advertencia_norma_no_encontrada(pedida: str, cargadas: str) -> str:
    return f"No encontré la norma '{pedida}'. Las cargadas son: {cargadas}"


def advertencia_articulo_no_encontrado(numero: str) -> str:
    return f"No hay un artículo {numero} en la normativa consultada"


def motivo_numero_en_varias_normas(numero: str) -> str:
    return f"el artículo {numero} figura en más de una norma"


def pregunta_cual_norma(numero: str) -> str:
    return f"El artículo {numero} está en varias normas. ¿De cuál?"


def resumen_para_llm(resultado: ResultadoTool) -> str:
    """Lo que ve el LLM de la tool. Si la tool pidió un dato, se lo dice para que se lo
    pregunte al operario en vez de volver a llamarla con argumentos inventados."""
    texto = f"consultar_articulo: estado={resultado.estado}"
    if resultado.faltantes:
        campos = ", ".join(f.campo for f in resultado.faltantes)
        texto += (
            f". Falta: {campos}. Preguntáselo al operario y no vuelvas a llamar la tool "
            "hasta que responda"
        )
    return texto


# --- plantilla del resultado (tipo de respuesta `consulta_articulo`) ---


def plantilla_consulta_articulo(
    respuesta: RespuestaAgente, resultados: list[ResultadoTool]
) -> str:
    """El texto del artículo va literal (sin pasar por el LLM), con su norma y
    jurisdicción en el encabezado."""
    datos = primer_dato(resultados) or {}
    partes = datos.get("partes", [])
    encabezado = f"{datos.get('norma_legible', 'Norma')}, art. {datos.get('numero', '')}"
    if datos.get("jurisdiccion_id"):
        encabezado += f" ({datos['jurisdiccion_id']})"
    bloques = []
    for i, parte in enumerate(partes, start=1):
        titulo = encabezado + (f" — texto {i} de {len(partes)}" if len(partes) > 1 else "")
        bloques.append(f"*{titulo}*\n{parte['texto']}")
    avisos = "\n".join(f"⚠️ {a}" for r in resultados for a in r.advertencias)
    return unir_secciones(*bloques, avisos)
