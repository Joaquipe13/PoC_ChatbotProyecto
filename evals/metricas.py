"""Métricas por corrida, para comparar entre corridas (`evals/runs/<run_id>/metricas.json`).

- objetivos logrados por escenario, con la variabilidad entre repeticiones;
- invariantes violados por tipo, citas inválidas y dictámenes fuera de plantilla;
- cobertura de las tools esperadas (aproxima el ruteo en una conversación libre; la
  exactitud de ruteo con respuesta correcta conocida se mide con `evals/run_evals.py`);
- latencia y tokens promedio, reintentos de tools.

Las conversaciones con turnos que fallaron por infraestructura se cuentan aparte: no son
errores del bot.
"""

import statistics

from evals import escenarios as cat
from evals import registro


def _percentil(valores: list[float], p: float) -> float:
    if not valores:
        return 0.0
    ordenados = sorted(valores)
    return ordenados[min(len(ordenados) - 1, int(round(p * (len(ordenados) - 1))))]


def calcular(run: str, invariantes: dict) -> dict:
    directorio = registro.dir_run(run)
    por_escenario: dict[str, list[dict]] = {}
    latencias: list[float] = []
    tokens_entrada: list[int] = []
    tokens_salida: list[int] = []
    turnos_total = turnos_infra = reintentos = dictamenes = 0
    for ruta in sorted(directorio.glob("*.jsonl")):
        registros = registro.leer_registros(ruta)
        turnos = [r for r in registros if r["tipo_registro"] == "turno"]
        cierre = next((r for r in registros if r["tipo_registro"] == "cierre"), None)
        propios = [t for t in turnos if not t.get("infra")]
        turnos_total += len(propios)
        turnos_infra += len(turnos) - len(propios)
        for t in propios:
            latencias.append(t["latencia_s"])
            tokens_entrada.append(t["tokens"]["entrada"])
            tokens_salida.append(t["tokens"]["salida"])
            reintentos += t["reintentos_tool"]
            dictamenes += t["respuesta"]["tipo"] == "dictamen"
        escenario_id = ruta.stem.split("__")[0]
        esperadas = set(cat.cargar(escenario_id, requerido=False).get("tools_esperadas") or [])
        usadas = {c["nombre"] for t in propios for c in t["tool_calls"]}
        por_escenario.setdefault(escenario_id, []).append({
            "conversacion": ruta.stem,
            "logrado": bool(cierre and cierre.get("logrado")),
            "cierre": cierre["resultado"] if cierre else None,
            "turnos": len(propios), "turnos_infra": len(turnos) - len(propios),
            "cobertura_tools": (len(esperadas & usadas) / len(esperadas)) if esperadas else None,
            "secuencia_tipos": [t["respuesta"]["tipo"] for t in propios],
            "tools": sorted(usadas),
        })

    escenarios = {}
    for escenario_id, conversaciones in por_escenario.items():
        logradas = sum(c["logrado"] for c in conversaciones)
        secuencias = {tuple(c["secuencia_tipos"]) for c in conversaciones}
        conjuntos_de_tools = {tuple(c["tools"]) for c in conversaciones}
        coberturas = [
            c["cobertura_tools"] for c in conversaciones if c["cobertura_tools"] is not None
        ]
        escenarios[escenario_id] = {
            "conversaciones": len(conversaciones), "logradas": logradas,
            "tasa_de_objetivos": round(logradas / len(conversaciones), 2),
            "cobertura_de_tools_esperadas": (
                round(statistics.mean(coberturas), 2) if coberturas else None
            ),
            # 1 = todas las repeticiones hicieron exactamente lo mismo; más = variaron
            "variantes_de_recorrido": len(secuencias),
            "variantes_de_tools": len(conjuntos_de_tools),
            "detalle": conversaciones,
        }

    por_invariante = invariantes.get("por_invariante", {})
    total_convs = sum(len(v) for v in por_escenario.values())
    logradas_total = sum(e["logradas"] for e in escenarios.values())
    return {
        "run": run,
        "conversaciones": total_convs, "turnos": turnos_total,
        "turnos_de_infraestructura": turnos_infra,
        "objetivos_logrados": f"{logradas_total}/{total_convs}",
        "escenarios": escenarios,
        "invariantes_violados": por_invariante,
        "invariantes_violados_total": sum(por_invariante.values()),
        "citas_invalidas": por_invariante.get("cita_no_verificada", 0),
        "dictamenes": dictamenes,
        "dictamenes_fuera_de_plantilla": por_invariante.get("dictamen_fuera_de_plantilla", 0),
        "latencia_media_s": round(statistics.mean(latencias), 2) if latencias else 0,
        "latencia_p95_s": round(_percentil(latencias, 0.95), 2),
        "tokens_medios_por_turno": {
            "entrada": round(statistics.mean(tokens_entrada)) if tokens_entrada else 0,
            "salida": round(statistics.mean(tokens_salida)) if tokens_salida else 0,
        },
        "reintentos_de_tools": reintentos,
    }
