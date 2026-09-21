"""Corre las conversaciones etiquetadas de `evals/conversaciones.jsonl`
contra el agente REAL (Gemini + Postgres) y reporta exactitud de ruteo (ver
skill, "Tests y evaluación").

A diferencia del resto del proyecto, esto sí sale a la red a propósito: es
una evaluación, no un test de `pytest` (`pytest` nunca toca la red, ver
skill). Requiere `USE_FIXTURES=false` con al menos una `GEMINI_API_KEY_*`
real y Postgres levantado.

Uso: uv run python evals/run_evals.py [--limite N]

Sobre las otras dos metas de la Fase 7 ("0 citas inventadas", "100% de
dictámenes por plantilla"): no se miden acá porque están garantizadas por
construcción, no por comportamiento del LLM en cada corrida:
- Las citas nunca vienen del texto libre del LLM: `tools/responder_consulta_normativa/utils.py`
  descarta en código cualquier cita que no esté entre los fragmentos
  recuperados (ver tests/tools/responder_consulta_normativa/test_utils.py, Fase 6).
- Todo `RespuestaAgente.tipo == "dictamen"` pasa siempre por
  `_plantilla_dictamen` (`formateador.py`): no hay otro camino para
  mostrar un dictamen. Ver tests/orquestador/test_formateador.py.
"""

import argparse
import json
import sys
from pathlib import Path

from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver

from fitosanitarios.config import get_settings
from fitosanitarios.orquestador.agente import crear_agente, crear_modelo_chat_gemini
from fitosanitarios.orquestador.estado import ContadorRepreguntas
from fitosanitarios.orquestador.turno import ejecutar_turno

RUTA_DATASET = Path(__file__).parent / "conversaciones.jsonl"
CATEGORIAS_CON_TOOL_ESPERADA = {"ruteo", "repregunta", "ambiguedad", "no_resuelto"}


def cargar_dataset() -> list[dict]:
    with RUTA_DATASET.open(encoding="utf-8") as f:
        return [json.loads(linea) for linea in f if linea.strip()]


def _tool_llamada(mensajes: list) -> str | None:
    for m in mensajes:
        if isinstance(m, AIMessage) and m.tool_calls:
            for tc in m.tool_calls:
                if tc["name"] != "RespuestaAgente":
                    return tc["name"]
    return None


def correr_caso(agente, contador: ContadorRepreguntas, caso: dict) -> dict:
    thread_id = f"eval-{caso['id']}"
    try:
        respuesta, mensajes_wa = ejecutar_turno(agente, thread_id, caso["mensaje"], contador)
    except Exception as exc:  # no se detiene la corrida por un caso que rompe
        return {**caso, "error": f"{type(exc).__name__}: {exc}"}

    estado = agente.get_state({"configurable": {"thread_id": thread_id}})
    tool_obtenida = _tool_llamada(estado.values.get("messages", []))

    resultado = {
        **caso,
        "tool_obtenida": tool_obtenida,
        "tipo_obtenido": respuesta.tipo,
        "mensaje_final": mensajes_wa[0][:200] if mensajes_wa else "",
    }
    if caso["categoria"] in CATEGORIAS_CON_TOOL_ESPERADA:
        resultado["ruteo_correcto"] = tool_obtenida == caso.get("tool_esperada")
    return resultado


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limite", type=int, default=None)
    args = parser.parse_args()

    settings = get_settings()
    if settings.use_fixtures:
        print(
            "USE_FIXTURES=true: los evals necesitan el LLM real. "
            "Corré con USE_FIXTURES=false y una GEMINI_API_KEY_* configurada.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    modelo = crear_modelo_chat_gemini(settings)
    # Checkpointer en memoria (no Postgres): cada caso corre en su propio
    # thread_id efímero, no hace falta persistencia real entre corridas de
    # evals; alcanza con que `agente.get_state()` tenga de dónde leer.
    agente = crear_agente(modelo, checkpointer=InMemorySaver())
    contador = ContadorRepreguntas()

    casos = cargar_dataset()
    if args.limite:
        casos = casos[: args.limite]

    resultados = [correr_caso(agente, contador, caso) for caso in casos]

    con_ruteo = [r for r in resultados if "ruteo_correcto" in r]
    aciertos = sum(1 for r in con_ruteo if r["ruteo_correcto"])
    errores = [r for r in resultados if "error" in r]

    print(f"\nCasos corridos: {len(resultados)} ({len(errores)} con error)")
    if con_ruteo:
        exactitud = aciertos / len(con_ruteo)
        print(f"Exactitud de ruteo: {exactitud:.0%} ({aciertos}/{len(con_ruteo)})")
    for r in resultados:
        if r.get("ruteo_correcto") is False:
            print(
                f"  [RUTEO INCORRECTO] {r['id']}: esperaba "
                f"{r.get('tool_esperada')!r}, obtuvo {r.get('tool_obtenida')!r}"
            )
        if "error" in r:
            print(f"  [ERROR] {r['id']}: {r['error']}")

    ruta_salida = Path(__file__).parent / "ultima_corrida.json"
    ruta_salida.write_text(json.dumps(resultados, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nDetalle completo en {ruta_salida}")


if __name__ == "__main__":
    main()
