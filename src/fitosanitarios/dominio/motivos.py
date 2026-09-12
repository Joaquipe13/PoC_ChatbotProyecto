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
    DOSIS_NO_COMPARABLE = "dosis_no_comparable"
    NORMATIVA_SIN_RESPALDO = "normativa_sin_respaldo"
    IMAGEN_ILEGIBLE = "imagen_ilegible"
    LIMITE_REPREGUNTAS = "limite_repreguntas"
    SERVICIO_NO_DISPONIBLE = "servicio_no_disponible"
    # Fase 9 (extensiones RF6/RF7): la skill no cubre estos RF, así que no
    # están en su "Catálogo MotivoNoResuelto" -- se agregan acá siguiendo el
    # mismo patrón, ver DECISIONES.md.
    VEHICULO_NO_ENCONTRADO = "vehiculo_no_encontrado"
    SIN_EVENTO_EN_CURSO = "sin_evento_en_curso"


DESCRIPCION_MOTIVO: dict[MotivoNoResuelto, str] = {
    MotivoNoResuelto.JURISDICCION_NO_CUBIERTA: (
        "El punto del lote no cae en ningún polígono de localidad cargado."
    ),
    MotivoNoResuelto.SIN_REGLA_APLICABLE: (
        "La jurisdicción del lote no tiene ninguna regla de distancia para "
        "ese tipo de zona o de aplicación."
    ),
    MotivoNoResuelto.PRODUCTO_NO_ENCONTRADO: (
        "Ningún candidato de producto superó el umbral de matching (trigram + embedding)."
    ),
    MotivoNoResuelto.SIN_USOS_REGISTRADOS: (
        "El producto no tiene cultivos ni dosis registrados, ni estructurados "
        "ni extraídos del marbete."
    ),
    MotivoNoResuelto.DOSIS_NO_COMPARABLE: (
        "No se pudieron normalizar las unidades de la dosis de la receta "
        "contra las del registro."
    ),
    MotivoNoResuelto.NORMATIVA_SIN_RESPALDO: (
        "Ningún fragmento de normativa recuperado superó RAG_UMBRAL_SIMILITUD."
    ),
    MotivoNoResuelto.IMAGEN_ILEGIBLE: (
        "La extracción de la receta desde la imagen no alcanzó la confianza "
        "mínima en campos clave."
    ),
    MotivoNoResuelto.LIMITE_REPREGUNTAS: (
        "Se alcanzaron 2 intentos fallidos repreguntando el mismo dato."
    ),
    MotivoNoResuelto.SERVICIO_NO_DISPONIBLE: (
        "Se agotó la cuota del LLM configurada o un servicio externo "
        "(base de datos, etc.) no respondió."
    ),
    MotivoNoResuelto.VEHICULO_NO_ENCONTRADO: (
        "No hay ningún vehículo cargado en el catálogo para ofrecer como opción."
    ),
    MotivoNoResuelto.SIN_EVENTO_EN_CURSO: (
        "Se pidió finalizar una aplicación pero no hay ninguna en curso para este operario."
    ),
}
