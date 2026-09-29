"""Los mensajes de esta tool. La receta completada se le muestra al operario con la
misma plantilla que la leída de la foto (`confirmacion_receta`, en
`tools/leer_receta/mensajes.py`)."""

from fitosanitarios.dominio.modelos import CampoFaltante, ResultadoTool
from fitosanitarios.servicios.receta import datos_para_llm

PREGUNTA_FOTO = "No tengo una receta en curso. ¿Me mandás la foto de la receta?"
MOTIVO_SIN_RECETA = "no hay una receta leída en esta conversación"


def faltante_foto() -> CampoFaltante:
    return CampoFaltante(
        campo="receta", motivo=MOTIVO_SIN_RECETA, pregunta_sugerida=PREGUNTA_FOTO,
        tipo_entrada="imagen",
    )


PREGUNTA_CORRECCION = (
    "¿Qué dato querés corregir? Escribilo con el valor correcto, por ejemplo: "
    "\"la dosis es 200 cc/ha\" o \"es en Sastre\"."
)


def faltante_correccion() -> CampoFaltante:
    return CampoFaltante(
        campo="correccion", motivo="el operario quiere corregir la receta sin decir qué",
        pregunta_sugerida=PREGUNTA_CORRECCION, tipo_entrada="texto",
    )


def aviso_producto_no_encontrado(nombre: str) -> str:
    return f"No encontré '{nombre}' entre los productos de la receta"


def resumen_para_llm(resultado: ResultadoTool) -> str:
    if resultado.faltantes and resultado.faltantes[0].campo == "correccion":
        return (
            "completar_receta: se le preguntó al operario qué dato quiere corregir; "
            "esperá su respuesta."
        )
    if not resultado.datos:
        return "completar_receta: no hay una receta leída; se le pidió la foto al operario."
    texto = f"Receta actualizada. Datos de la receta: {datos_para_llm(resultado.datos)}."
    if resultado.faltantes:
        campos = ", ".join(f.campo for f in resultado.faltantes)
        return texto + f" Todavía faltan: {campos}; ya se le preguntaron al operario."
    return texto + " Se le mostró para confirmar; no la evalúes hasta que confirme."
