"""Control de una corrida de simulación: crearla, saber qué falta, marcar lo hecho y analizar.

La corrida es reanudable: `progreso.json` guarda el estado de cada conversación
(`escenario__repetición`), así que si se corta por cuota se retoma sin repetir lo ya hecho.

    uv run python -m evals.corrida iniciar --escenarios a,b,c --reps 2
    uv run python -m evals.corrida pendientes <run_id>
    uv run python -m evals.corrida marcar <run_id> <escenario__n> hecha|infra|error
    uv run python -m evals.corrida analizar <run_id>   # invariantes + métricas
"""

import argparse
import hashlib
import subprocess
import sys

from evals import base_eval, invariantes, metricas, registro
from evals import escenarios as cat


def _git(*args: str) -> str:
    try:
        return subprocess.run(
            ["git", *args], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "desconocido"


def configuracion(base: str) -> dict:
    from fitosanitarios.config import get_settings
    from fitosanitarios.orquestador.prompt_sistema import PROMPT_SISTEMA, contar_tokens_aproximado

    settings = get_settings()
    return {
        "commit": _git("rev-parse", "--short", "HEAD"),
        "arbol_sin_commitear": bool(_git("status", "--porcelain")),
        "hash_prompt_de_sistema": hashlib.sha256(PROMPT_SISTEMA.encode()).hexdigest()[:12],
        "tokens_prompt_aprox": contar_tokens_aproximado(PROMPT_SISTEMA),
        "orquestador": {"proveedor": settings.llm_provider, "modelo": settings.gemini_model},
        "temperatura_solicitada": registro.TEMPERATURA,
        "temperatura_efectiva": (
            "la que fija el modelo: el proveedor ignora el parámetro en modelos Gemini 3 "
            "(aviso de langchain-google-genai); verificar por modelo"
        ),
        "base_de_datos": base,
        "max_turnos_por_conversacion": registro.MAX_TURNOS,
        "keys_de_gemini": len(settings.gemini_api_keys),
    }


def iniciar(escenarios: list[str], reps: int) -> str:
    base = base_eval.nombre_base(base_eval.url_eval())
    run = registro.nuevo_run_id()
    directorio = registro.dir_run(run)
    for e in escenarios:
        cat.cargar(e)  # falla si no existe
    meta = {
        "run_id": run,
        **configuracion(base),
        "escenarios": escenarios,
        "conjuntos": {e: cat.cargar(e).get("conjunto") for e in escenarios},
        "repeticiones": reps,
        "simulador": "subagente de Claude Code (evals/../.claude/agents/simulador-operario.md)",
    }
    registro.escribir_json(directorio / "meta.json", meta)
    registro.escribir_json(directorio / "progreso.json", {
        "conversaciones": {f"{e}__{n}": "pendiente" for e in escenarios for n in range(1, reps + 1)}
    })
    registro.anotar_bitacora(run, f"Corrida creada: {escenarios} x {reps} repeticiones")
    return run


def pendientes(run: str) -> list[str]:
    progreso = registro.leer_json(registro.dir_run(run) / "progreso.json", {"conversaciones": {}})
    return [c for c, estado in progreso["conversaciones"].items() if estado == "pendiente"]


def analizar(run: str) -> None:
    resultado = invariantes.analizar_run(run)
    m = metricas.calcular(run, resultado)
    registro.escribir_json(registro.dir_run(run) / "metricas.json", m)
    registro.anotar_bitacora(
        run, f"Análisis automático: {m['invariantes_violados_total']} invariantes violados, "
             f"objetivos {m['objetivos_logrados']}"
    )
    print(f"Objetivos logrados: {m['objetivos_logrados']}")
    print(f"Invariantes violados: {m['invariantes_violados'] or 'ninguno'}")
    print(f"Turnos de infraestructura (no cuentan como error del bot): "
          f"{m['turnos_de_infraestructura']}")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("iniciar")
    p.add_argument("--escenarios", required=True, help="ids separados por coma, o 'desarrollo'")
    p.add_argument("--reps", type=int, default=2)
    p = sub.add_parser("pendientes")
    p.add_argument("run")
    p = sub.add_parser("marcar")
    p.add_argument("run")
    p.add_argument("conversacion")
    p.add_argument("estado", choices=["hecha", "infra", "error", "pendiente"])
    p = sub.add_parser("analizar")
    p.add_argument("run")
    args = parser.parse_args()

    if args.cmd == "iniciar":
        pedidos = args.escenarios
        ids = cat.ids("desarrollo") if pedidos == "desarrollo" else pedidos.split(",")
        print(iniciar(ids, args.reps))
    elif args.cmd == "pendientes":
        print("\n".join(pendientes(args.run)))
    elif args.cmd == "marcar":
        registro.marcar_progreso(args.run, args.conversacion, args.estado)
    else:
        analizar(args.run)


if __name__ == "__main__":
    main()
