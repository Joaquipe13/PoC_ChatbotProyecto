"""Los mensajes de esta tool: lo que pregunta y cómo se le muestra el listado al
operario (una de las dos formas del tipo de respuesta `consulta_producto`; la otra
es la de `validar_producto_registro`)."""

from fitosanitarios.dominio.modelos import RespuestaAgente, ResultadoTool
from fitosanitarios.servicios.formato import primer_dato

PREGUNTA_CULTIVO = "¿Cómo se llama el cultivo?"
SIN_PRODUCTOS = "No encontré productos registrados con esos filtros."
_AVISO_REGISTRO = (
    "Es lo que figura en el registro; qué aplicar lo define la receta del ingeniero agrónomo."
)
_MAXIMO_LISTADO = 10


def motivo_cultivo_no_encontrado(cultivo: str) -> str:
    return f"no se encontró un cultivo parecido a '{cultivo}'"


def motivo_sin_filtros() -> str:
    return "consultar_productos requiere cultivo, adversidad o principio_activo"


def resumen_para_llm(total: int) -> str:
    return f"consultar_productos: {total} productos encontrados"


def plantilla_listado(respuesta: RespuestaAgente, resultados: list[ResultadoTool]) -> str:
    """Sin intro del LLM ni sección *Fuentes* aparte (ver `formatear_respuesta`
    y DECISIONES.md): la única Cita que arma la tool es un marcador genérico
    ("SENASA, (vademécum)") que no agrega nada sobre lo que ya va en la línea
    del producto (el propio n.° de registro). La Cita real sigue viajando en
    `ResultadoTool.citas` y quedando logueada por turno."""
    datos = primer_dato(resultados) or {}
    productos = datos.get("productos", [])
    total = datos.get("total", len(productos))
    if not productos:
        return SIN_PRODUCTOS
    lineas = [f"*Productos registrados* ({len(productos)} de {total})"]
    for i, p in enumerate(productos[:_MAXIMO_LISTADO], start=1):
        dosis = p.get("dosis") or {}
        dosis_txt = dosis.get("texto_original", "sin dosis registrada")
        marca = p.get("marca", "(sin marca)")
        registro = p.get("numero_inscripcion", "-")
        banda = p.get("banda_toxicologica") or "S/D"
        lineas.append(f"{i}. *{marca}* · Reg. SENASA {registro} · Banda {banda} · {dosis_txt}")
    lineas.append(_AVISO_REGISTRO)
    return "\n".join(lineas)
