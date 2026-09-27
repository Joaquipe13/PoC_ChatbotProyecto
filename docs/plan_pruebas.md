# Plan de pruebas del chatbot (con un usuario simulado por Gemini)

Prueba de punta a punta del sistema experto, conversando con él como lo haría un
operario. Complementa los tests automáticos (`uv run pytest`, sin red): acá el bot corre
con Gemini real, contra una copia de la base de desarrollo, y del otro lado hay un usuario
simulado, también con Gemini, que sigue cada caso.

## Objetivo

Verificar que, en conversaciones realistas, el bot:

1. elige la herramienta correcta para cada pedido y pregunta lo que falta;
2. responde con datos del registro, de las normas o del marbete, **siempre con su fuente**,
   sin inventar números, normas ni dosis;
3. dice que no sabe (o que no aplica) cuando no hay con qué responder;
4. no se sale de su tema ni muestra su configuración.

## Cómo funciona la prueba

- **Casos:** `evals/escenarios/plan_*.yaml`. Cada uno tiene una **persona** (quién escribe
  y cómo), un **objetivo**, los **datos** que esa persona tiene (a veces una foto de receta)
  y un **comportamiento** (qué hace si el bot le pregunta algo). Además tiene
  **expectativas** que el simulador no ve: qué tools se tienen que usar o no, y qué tiene que
  decir o no el bot.
- **Usuario simulado** (`evals/agente_prueba.py`): Gemini recibe solo la persona, el
  objetivo, los datos y el comportamiento; lee lo que contestó el bot y decide qué escribir,
  si mandar la foto o si terminar. Al terminar declara si logró el objetivo.
- **El bot** corre turno a turno por el mismo camino que WhatsApp (`evals/chat.py`), con
  Gemini real y una copia de la base (`fitosanitarios_eval`), así lo que agenda o registra
  no toca la base de desarrollo.
- **Verificación automática** (`evals/invariantes.py`): después de cada corrida se revisan
  las expectativas de cada caso y los invariantes de todas las conversaciones (ningún
  número sin respaldo en una tool, ninguna cita no verificada, ningún dictamen sin evaluar,
  nada de la configuración a la vista, etc.).
- **Informe:** `evals/runs/<corrida>/informe_plan.md`, con una tabla por caso y cada
  conversación completa.

Un caso **pasa** si el simulador logró el objetivo y no falló ninguna expectativa ni
invariante. Un turno que falla por cuota o red de Gemini se reintenta una vez y, si vuelve
a fallar, el caso queda como `infra` (no cuenta como error del bot).

## Casos

| Caso | Área | Qué se prueba | Qué se exige |
|---|---|---|---|
| `plan_receta_foto_apta` | Receta por foto | Foto de receta, pedido de la localidad, confirmación y dictamen | `leer_receta`, `evaluar_viabilidad_legal`, un dictamen |
| `plan_receta_foto_incompleta` | Receta por foto | Foto con datos faltantes: el bot los pide y los completa | `leer_receta`, `completar_receta` |
| `plan_foto_no_es_receta` | Receta por foto | Una factura en vez de una receta | no evalúa ni dictamina nada |
| `plan_dictamen_y_agenda` | Dictamen y agenda | Receta sin problemas dada por texto, agendado con pronóstico | sin observaciones, `agendar_aplicacion`, pronóstico |
| `plan_dictamen_dosis_observada` | Dictamen | Dosis muy por encima del registro | dice que está por encima del rango y no ofrece agendar |
| `plan_banda_de_producto` | Productos | Banda de un producto y de uno ambiguo (Roundup) | `validar_producto_registro`, no va al marbete |
| `plan_productos_por_banda` | Productos | Listado de productos banda verde para soja | `consultar_productos`, ninguno banda II ni III |
| `plan_distancia_con_producto` | Distancias | Distancia al pueblo con un producto (sin decir la banda), por avión | `listar_limitaciones`, 3000 m |
| `plan_comparaciones` | Distancias | Avión contra tierra; amarilla contra verde | `listar_limitaciones`, no el RAG |
| `plan_equipos_sin_norma` | Distancias | Drone y mochila, que las normas no nombran | aviso de drones y de mochila |
| `plan_localidad_sin_normativa` | Distancias | Rosario (sin ordenanza cargada) | aclara que usa la provincial, 500 m |
| `plan_marbete` | Marbete | Carencia y envases vacíos de Vertimec | `consultar_marbete`, cita la página |
| `plan_normativa` | Normativa | Viento en El Trébol y texto del art. 33 de la Ley 11.273 | cita la Ordenanza 841/2010, art. 4; `consultar_articulo` |
| `plan_eventos_y_agenda` | Operación | Inicio y fin de una aplicación con "la mosquito", agenda semanal | `registrar_evento`, `consultar_agenda` |
| `plan_fuera_de_dominio` | Límites | Clima, pedido de instrucciones internas, fútbol | no evalúa nada ni muestra su configuración |

También se pueden correr los escenarios anteriores de la evaluación conversacional
(`--casos desarrollo`).

## Cómo correrlo

```bash
docker compose up -d db
uv run python -m evals.base_eval crear          # copia de la base de desarrollo (una vez)
uv run python -m evals.agente_prueba            # los 15 casos del plan
uv run python -m evals.agente_prueba --casos plan_marbete,plan_normativa   # algunos
uv run python -m evals.base_eval borrar         # al terminar
```

Hace falta al menos una `GEMINI_API_KEY_*` real en `.env` (mejor varias: el bot y el
simulador las usan en orden inverso para repartir la cuota). La corrida completa tarda del
orden de 20 a 30 minutos. El caso `plan_receta_foto_apta` usa
`data/recetas_ejemplo/01_apta_terrestre.jpg`, que no está en el repositorio: se genera con
`uv run python scripts/generar_recetas_ejemplo_el_trebol.py`.

## Cómo leer el resultado

- **✅** el caso pasó. **❌** el simulador no logró el objetivo o falló una expectativa o un
  invariante (el informe dice cuál y en qué turno). **⚙️ infra**: la cuota o la red no
  dejaron terminar.
- Un ❌ no es automáticamente un error del bot: el simulador también es un LLM y puede
  equivocarse o rendirse antes de tiempo. Hay que leer la conversación del caso en el
  informe antes de sacar una conclusión.
- Gemini varía entre corridas (ignora la temperatura): para distinguir un error de una
  variación, repetir el caso (`--casos <id> --reps 3`).
