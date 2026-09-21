"""Los mensajes de esta tool: lo que pregunta, lo que avisa y cómo se le muestra
el resultado al operario (la plantilla del tipo de respuesta `evento_registrado`)."""

from fitosanitarios.dominio.modelos import RespuestaAgente, ResultadoTool
from fitosanitarios.servicios.formato import primer_dato

# --- preguntas y motivos de la tool ---

MOTIVO_SIN_VEHICULO = "no se indicó qué vehículo se usa"
PREGUNTA_VEHICULO = "¿Con qué vehículo vas a aplicar?"
MOTIVO_SIN_LOTE = "no se indicó el lote"
PREGUNTA_LOTE = "¿En qué lote vas a aplicar?"


def advertencia_ya_en_curso(desde: str, lote: str | None) -> str:
    return (
        f"ya hay una aplicación en curso desde {desde} en el lote {lote}; "
        "registrá que la terminaste antes de iniciar otra"
    )


def resumen_para_llm(accion: str, estado: str) -> str:
    return f"registrar_evento: accion={accion} estado={estado}"


# --- plantilla del resultado (tipo de respuesta `evento_registrado`) ---


def plantilla_evento_registrado(
    respuesta: RespuestaAgente, resultados: list[ResultadoTool]
) -> str:
    datos = primer_dato(resultados) or {}
    resultado = resultados[0] if resultados else None

    if resultado is not None and resultado.estado == "observado":
        lineas = ["⚠️ *Ya hay una aplicación en curso*"]
        lineas.extend(f"- {a}" for a in resultado.advertencias)
        return "\n".join(lineas)

    if datos.get("fecha_fin"):
        lineas = ["✅ *Aplicación finalizada*"]
        if datos.get("lote"):
            lineas.append(f"- *Lote:* {datos['lote']}")
        lineas.append(f"- *Inicio:* {datos.get('fecha_inicio', 'no figura')}")
        lineas.append(f"- *Fin:* {datos['fecha_fin']}")
        return "\n".join(lineas)

    lineas = ["✅ *Aplicación iniciada*"]
    if datos.get("vehiculo"):
        lineas.append(f"- *Vehículo:* {datos['vehiculo']}")
    if datos.get("lote"):
        lineas.append(f"- *Lote:* {datos['lote']}")
    lineas.append(f"- *Inicio:* {datos.get('fecha_inicio', 'no figura')}")
    return "\n".join(lineas)
