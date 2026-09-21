# Evaluación conversacional (Fase 12)

Un agente **simulador** (un usuario que no conoce el sistema) conversa por WhatsApp simulado con el
bot; cada conversación queda registrada; unos **invariantes** en código y un agente **analista** las
interpretan. El orquestador del bot es Gemini real: es la prueba más realista posible sin usuarios.

Todo esto sale a la red y gasta cuota: **no corre con `pytest` ni en CI**. Lo único que corre con
`uv run pytest evals` son los tests de los invariantes (sin red).

## Piezas

| Archivo | Qué es |
|---|---|
| `chat.py` | Harness de un turno por vez, por el mismo camino que el webhook de WhatsApp. `--nuevo`, `--imagen`, `--cerrar`, `--replay`. |
| `registro.py` | Rutas y logger (JSONL por conversación, `meta.json`, `progreso.json`, bitácora). |
| `base_eval.py` | Clona la base como `<base>_eval`. El harness se niega a correr contra otra. |
| `corrida.py` | `iniciar`, `pendientes`, `marcar`, `analizar` (invariantes + métricas). Corridas reanudables. |
| `invariantes.py` | Chequeos automáticos sin LLM (números y citas con respaldo, dictamen, plantilla, repreguntas, prompt, confirmación…). |
| `metricas.py` | Métricas por corrida para comparar. |
| `escenarios/*.yaml` | Persona, objetivo, datos y comportamiento del simulador; `expectativas_duras` y `tools_esperadas` solo para el análisis. |
| `../.claude/agents/simulador-operario.md` | Definición del simulador. |
| `../.claude/agents/analista-conversaciones.md` | Definición del analista (solo lectura). |
| `run_evals.py`, `run_consultas_normativa.py` | Evals de un turno (ruteo y consultas de normativa). |

## Cómo se corre

```bash
uv run python -m evals.base_eval crear                    # clon de la base para las corridas
uv run python -m evals.corrida iniciar --escenarios desarrollo --reps 2   # imprime el run_id
uv run python -m evals.corrida pendientes <run_id>        # qué conversaciones faltan
# por cada conversación pendiente, el simulador (subagente) corre:
#   uv run python -m evals.chat --run <run_id> --thread sim-<escenario>__<n> "mensaje"
uv run python -m evals.corrida analizar <run_id>          # invariantes.json + metricas.json
# el analista lee evals/runs/<run_id>/ y deja analisis.json e informe.md
uv run python -m evals.chat --replay evals/runs/<run_id>/<escenario>__<n>.jsonl   # verificar un arreglo
uv run python -m evals.base_eval borrar                   # al terminar
```

El simulador es un subagente de Claude Code (`.claude/agents/`), no un script: conversa llamando al
CLI. **Los agentes de `.claude/agents/` se registran al iniciar Claude Code**; en la sesión donde se
crearon se usó un agente general que lee solo la definición del simulador.

## Independencia

- El simulador no recibe código, prompt del sistema, reglas ni respuestas esperadas, y no puede usar
  `--interno`. Su herramienta es solo Bash; que no lea el repositorio es una regla de su definición,
  no una restricción técnica.
- El analista es de solo lectura y no ve el historial de arreglos (`DIFICULTADES.md`, git).
- Los escenarios `holdout` solo se usan para medir, no para decidir arreglos.

## Lo que hay que saber

- `gemini-3.5-flash-lite` **ignora el parámetro de temperatura**: no se puede bajar. Las repeticiones
  de una misma conversación varían (se vio en el piloto). Un hallazgo que aparece en 1 de 2
  repeticiones sigue siendo un hallazgo.
- Un turno que falla por cuota o por red se registra como `infra` y no cuenta como error del bot.
- "Objetivo logrado" es lo que **declara el simulador**: no verifica el contenido. Lo verifica el
  analista.
- Las corridas viven en `evals/runs/` (ignorado por git). Lo que se arregla deja un test permanente
  (o una conversación en `evals/golden/`) y una línea en `DIFICULTADES.md`.
