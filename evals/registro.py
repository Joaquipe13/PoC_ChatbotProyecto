"""Rutas y escritura de los logs de las corridas de evaluación.

    evals/runs/<run_id>/
        meta.json                       configuración de la corrida (commit, prompt, modelo…)
        progreso.json                   qué conversaciones están hechas (la corrida es reanudable)
        bitacora.md                     lo que pasó, en orden
        <escenario>__<n>.jsonl          una conversación: un registro por turno
        <escenario>__<n>.estado.json    contador de repreguntas (vive en memoria en producción)
        invariantes.json, metricas.json, analisis.json, informe.md   (los deja `corrida analizar`)

Cada línea de un `.jsonl` es un registro con `tipo_registro`:

- `turno`: `n`, `entrada` ({tipo: texto|imagen, contenido, ruta?}), `tool_calls` (nombre,
  args saneados, estado, motivo, faltantes, citas, chequeos_no_realizados, advertencias,
  datos), `respuesta` ({tipo, faltantes}), `mensajes` (lo que se le muestra al
  usuario, con cómo se enviaría: texto, botones o lista), `latencia_s`, `tokens`,
  `llamadas_tool`, `reintentos_tool`, `infra`, `error`;
- `cierre`: lo que declaró el simulador al terminar (objetivo logrado o por qué abandonó).

No se guardan tokens de API, imágenes ni teléfonos: los threads son sintéticos
(`sim-<escenario>__<n>`) y de una foto solo se guarda su ruta.
"""

import json
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
RUNS = RAIZ / "runs"
ESCENARIOS = RAIZ / "escenarios"
TEMPERATURA = 0.0  # la más baja que acepta Gemini (verificar por modelo)
MAX_TURNOS = 12


def nuevo_run_id() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def dir_run(run: str) -> Path:
    return RUNS / run


def nombre_conversacion(thread: str) -> str:
    """`sim-receta_apta__1` -> `receta_apta__1`."""
    return thread.removeprefix("sim-").removeprefix("replay-")


def ruta_log(run: str, thread: str) -> Path:
    return dir_run(run) / f"{nombre_conversacion(thread)}.jsonl"


def ruta_estado(run: str, thread: str) -> Path:
    return dir_run(run) / f"{nombre_conversacion(thread)}.estado.json"


def leer_registros(ruta: Path) -> list[dict]:
    if not ruta.exists():
        return []
    with ruta.open(encoding="utf-8") as f:
        return [json.loads(linea) for linea in f if linea.strip()]


def leer_turnos(ruta: Path) -> list[dict]:
    return [r for r in leer_registros(ruta) if r["tipo_registro"] == "turno"]


def agregar(ruta: Path, registro: dict) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("a", encoding="utf-8") as f:
        f.write(json.dumps(registro, ensure_ascii=False) + "\n")


def leer_json(ruta: Path, defecto=None):
    if not ruta.exists():
        return defecto
    return json.loads(ruta.read_text(encoding="utf-8"))


def escribir_json(ruta: Path, datos) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")


def anotar_bitacora(run: str, texto: str) -> None:
    ruta = dir_run(run) / "bitacora.md"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("a", encoding="utf-8") as f:
        f.write(f"- {datetime.now():%H:%M:%S} {texto}\n")


def marcar_progreso(run: str, conversacion: str, estado: str) -> None:
    """`estado`: pendiente | hecha | infra | error. Lo usa `--cerrar` de `evals/chat.py`."""
    ruta = dir_run(run) / "progreso.json"
    progreso = leer_json(ruta)
    if progreso is None or conversacion not in progreso["conversaciones"]:
        return
    progreso["conversaciones"][conversacion] = estado
    escribir_json(ruta, progreso)
