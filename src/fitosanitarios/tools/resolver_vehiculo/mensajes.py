"""Los mensajes de esta tool: cómo se le muestra el vehículo identificado al
operario (la plantilla del tipo de respuesta `consulta_vehiculo`). La pregunta
cuando no se lo identifica es común con `registrar_evento`: vive en
`servicios/resolucion_vehiculo.py`."""

from fitosanitarios.dominio.modelos import RespuestaAgente, ResultadoTool
from fitosanitarios.servicios.formato import primer_dato


def resumen_para_llm(estado: str) -> str:
    return f"resolver_vehiculo: estado={estado}"


def plantilla_consulta_vehiculo(
    respuesta: RespuestaAgente, resultados: list[ResultadoTool]
) -> str:
    datos = primer_dato(resultados) or {}
    vehiculo = datos.get("vehiculo", "(sin identificar)")
    tipo_aplic = datos.get("tipo_aplicacion", "")
    return f"*Vehículo:* {vehiculo}" + (f" ({tipo_aplic})" if tipo_aplic else "")
