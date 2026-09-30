"""Catálogo de motivos por los que el sistema no pudo resolver una consulta.

Fuente: skill agente-fitosanitarios, sección "Catálogo MotivoNoResuelto".
Fuera de dominio NO es un motivo de esta lista: lo decide el orquestador antes
de llamar a cualquier tool (Fase 7), no una tool con `ResultadoTool`.
"""

from enum import StrEnum


class MotivoNoResuelto(StrEnum):
    JURISDICCION_NO_CUBIERTA = "jurisdiccion_no_cubierta"
    SIN_REGLA_APLICABLE = "sin_regla_aplicable"
    PRODUCTO_NO_ENCONTRADO = "producto_no_encontrado"
    SIN_USOS_REGISTRADOS = "sin_usos_registrados"
    NORMATIVA_SIN_RESPALDO = "normativa_sin_respaldo"
    IMAGEN_ILEGIBLE = "imagen_ilegible"
    LIMITE_REPREGUNTAS = "limite_repreguntas"
    # Fase 9 (extensiones RF6/RF7): la skill no cubre estos RF, así que no
    # están en su "Catálogo MotivoNoResuelto" -- se agregan acá siguiendo el
    # mismo patrón, ver DECISIONES.md.
    VEHICULO_NO_ENCONTRADO = "vehiculo_no_encontrado"
    SIN_EVENTO_EN_CURSO = "sin_evento_en_curso"
    # Consulta de un artículo por número (`consultar_articulo`).
    ARTICULO_NO_ENCONTRADO = "articulo_no_encontrado"
    # RAG de marbetes (`consultar_marbete`).
    MARBETE_SIN_RESPALDO = "marbete_sin_respaldo"


DESCRIPCION_MOTIVO: dict[MotivoNoResuelto, str] = {
    MotivoNoResuelto.JURISDICCION_NO_CUBIERTA: (
        "La localidad indicada no está entre las cargadas en el sistema."
    ),
    MotivoNoResuelto.SIN_REGLA_APLICABLE: (
        "La localidad no tiene ninguna regla de distancia para "
        "ese tipo de zona o de aplicación."
    ),
    MotivoNoResuelto.PRODUCTO_NO_ENCONTRADO: (
        "Ningún candidato de producto superó el umbral de matching (trigram + embedding)."
    ),
    MotivoNoResuelto.SIN_USOS_REGISTRADOS: (
        "SENASA no publica para qué cultivos ni en qué dosis está registrado el producto, "
        "así que no se pueden verificar."
    ),
    MotivoNoResuelto.NORMATIVA_SIN_RESPALDO: (
        "La normativa cargada no dice nada que responda la pregunta (o lo que se "
        "encontró no alcanza para citar una norma)."
    ),
    MotivoNoResuelto.IMAGEN_ILEGIBLE: (
        "La extracción de la receta desde la imagen no alcanzó la confianza "
        "mínima en campos clave."
    ),
    MotivoNoResuelto.LIMITE_REPREGUNTAS: (
        "Se alcanzaron 2 intentos fallidos repreguntando el mismo dato."
    ),
    MotivoNoResuelto.VEHICULO_NO_ENCONTRADO: (
        "No hay ningún vehículo cargado en el catálogo para ofrecer como opción."
    ),
    MotivoNoResuelto.SIN_EVENTO_EN_CURSO: (
        "Se pidió finalizar una aplicación pero no hay ninguna en curso para este operario."
    ),
    MotivoNoResuelto.ARTICULO_NO_ENCONTRADO: (
        "No hay un artículo con ese número en la normativa cargada para esa consulta."
    ),
    MotivoNoResuelto.MARBETE_SIN_RESPALDO: (
        "El marbete de ese producto no está disponible con texto, o no dice nada sobre "
        "lo que preguntaste."
    ),
}
