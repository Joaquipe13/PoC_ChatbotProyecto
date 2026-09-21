"""Evalúa con Gemini REAL y la base real las consultas de normativa (limitaciones,
artículo por número, duda de contenido) con frases informales y con errores de
ortografía, y unos casos de control de otras tools.

Cada caso de `consultas_normativa.jsonl` es una lista de turnos; cada turno puede
esperar la tool que se llama (`tool`), el tipo de respuesta (`tipo`), textos que
tiene que contener el mensaje final (`contiene`) y textos que no (`no_contiene`).
Solo lee de la base: no corre casos que escriban (agendar, registrar eventos).

    USE_FIXTURES=false uv run python evals/run_consultas_normativa.py [--casos id1,id2]
                                                                      [--pausa 4]

Sale a la red a propósito (no es un test de `pytest`). Requiere `USE_FIXTURES=false`,
una `GEMINI_API_KEY_*` y Postgres con la normativa cargada. El detalle de cada corrida
queda en `evals/ultima_corrida_normativa.json`.
"""

import argparse
import json
import sys
import time
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver

from fitosanitarios.config import get_settings
from fitosanitarios.orquestador.agente import crear_agente, crear_modelo_chat_gemini
from fitosanitarios.orquestador.estado import ContadorRepreguntas
from fitosanitarios.orquestador.turno import ejecutar_turno

RUTA_DATASET = Path(__file__).parent / "consultas_normativa.jsonl"
RUTA_SALIDA = Path(__file__).parent / "ultima_corrida_normativa.json"


def cargar_casos() -> list[dict]:
    with RUTA_DATASET.open(encoding="utf-8") as f:
        return [json.loads(linea) for linea in f if linea.strip()]


def tools_del_ultimo_turno(mensajes: list) -> list[dict]:
    """Las tools que se llamaron desde el último mensaje del usuario, con sus argumentos."""
    llamadas: list[dict] = []
    for m in reversed(mensajes):
        if isinstance(m, HumanMessage):
            break
        if isinstance(m, AIMessage) and m.tool_calls:
            llamadas.extend(
                {"tool": tc["name"], "args": tc["args"]}
                for tc in m.tool_calls if tc["name"] != "RespuestaAgente"
            )
    return list(reversed(llamadas))


def evaluar_turno(turno: dict, tipo: str, tools: list[dict], texto: str) -> list[str]:
    """Las expectativas que no se cumplieron, en texto."""
    fallas = []
    if "tool" in turno and turno["tool"] not in [t["tool"] for t in tools]:
        fallas.append(
            f"esperaba la tool {turno['tool']!r}, llamó {[t['tool'] for t in tools] or 'ninguna'}"
        )
    if "tipo" in turno and turno["tipo"] != tipo:
        fallas.append(f"esperaba el tipo {turno['tipo']!r}, obtuvo {tipo!r}")
    minusculas = texto.lower()
    fallas.extend(
        f"el mensaje no contiene {frag!r}"
        for frag in turno.get("contiene", []) if frag.lower() not in minusculas
    )
    fallas.extend(
        f"el mensaje contiene {frag!r} y no debería"
        for frag in turno.get("no_contiene", []) if frag.lower() in minusculas
    )
    return fallas


def correr_caso(agente, contador: ContadorRepreguntas, caso: dict, pausa: float) -> dict:
    thread_id = f"eval-normativa-{caso['id']}"
    turnos_resultado = []
    for turno in caso["turnos"]:
        try:
            respuesta, mensajes = ejecutar_turno(agente, thread_id, turno["mensaje"], contador)
        except Exception as exc:  # un caso que rompe no frena la corrida
            error = f"{type(exc).__name__}: {exc}"
            turnos_resultado.append({"mensaje": turno["mensaje"], "error": error})
            break
        estado = agente.get_state({"configurable": {"thread_id": thread_id}})
        tools = tools_del_ultimo_turno(estado.values.get("messages", []))
        texto = "\n\n".join(mensajes)
        turnos_resultado.append({
            "mensaje": turno["mensaje"], "tipo": respuesta.tipo, "tools": tools,
            "respuesta": texto, "fallas": evaluar_turno(turno, respuesta.tipo, tools, texto),
        })
        time.sleep(pausa)
    return {"id": caso["id"], "descripcion": caso["descripcion"], "turnos": turnos_resultado}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--casos", default=None, help="ids separados por coma")
    parser.add_argument("--pausa", type=float, default=4.0, help="segundos entre llamadas")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    settings = get_settings()
    if settings.use_fixtures:
        print("USE_FIXTURES=true: hace falta el LLM real (USE_FIXTURES=false).", file=sys.stderr)
        raise SystemExit(1)

    casos = cargar_casos()
    if args.casos:
        pedidos = set(args.casos.split(","))
        casos = [c for c in casos if c["id"] in pedidos]

    agente = crear_agente(crear_modelo_chat_gemini(settings), checkpointer=InMemorySaver())
    contador = ContadorRepreguntas()
    resultados = [correr_caso(agente, contador, c, args.pausa) for c in casos]

    fallidos = 0
    for r in resultados:
        fallas = [f for t in r["turnos"] for f in t.get("fallas", [])]
        errores = [t["error"] for t in r["turnos"] if "error" in t]
        ok = not fallas and not errores
        fallidos += 0 if ok else 1
        print(f"[{'OK' if ok else 'FALLA'}] {r['id']}: {r['descripcion']}")
        for f in fallas + errores:
            print(f"      - {f}")
    print(f"\n{len(resultados) - fallidos}/{len(resultados)} casos bien")
    RUTA_SALIDA.write_text(json.dumps(resultados, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Detalle en {RUTA_SALIDA}")


if __name__ == "__main__":
    main()
