# Agente de recetas fitosanitarios (TP2 IA)

POC de un agente conversacional por WhatsApp que lee recetas agronómicas de fitosanitarios, las contrasta con el registro de SENASA y la normativa de 10 localidades, y dictamina si la aplicación es viable/legal.

- Plan de trabajo: [`plandefases.md`](plandefases.md) — leerlo antes de tocar código, identificar la fase en curso y trabajar solo en esa fase.
- Arquitectura, contratos y reglas de negocio: skill `agente-fitosanitarios` (`.claude/skills/agente-fitosanitarios/SKILL.md`).
- Decisiones tomadas y por qué: [`DECISIONES.md`](DECISIONES.md).
- Problemas encontrados y cómo se resolvieron: [`DIFICULTADES.md`](DIFICULTADES.md).

## Levantar el entorno

Requisitos: Python 3.12, [uv](https://docs.astral.sh/uv/), Docker.

```bash
cp .env.example .env          # completar valores (o dejar USE_FIXTURES=true para desarrollar sin LLM/DB reales)
uv sync --dev                 # instala dependencias (incluye grupo dev: pytest, ruff)
docker compose up -d db       # Postgres 16 + pgvector + pg_trgm
```

Verificar que las extensiones quedaron instaladas:

```bash
docker compose exec db psql -U postgres -d fitosanitarios -c "SELECT extname FROM pg_extension;"
```

## Correr tests y lint

```bash
uv run pytest -q
uv run ruff check .
```

Los tests nunca salen a la red: con `USE_FIXTURES=true` (default) el LLM es un fake determinista y no hace falta ninguna API key.

## Correr la demo

Con Postgres levantado y al menos una `GEMINI_API_KEY_*` real en `.env`:

```bash
uv run jupyter notebook notebooks/demo_e2e.ipynb   # o notebooks/demo_sin_whatsapp.ipynb
```

Correr todas las celdas con kernel limpio ("Restart & Run All"). El guion completo, con el mensaje exacto de cada caso y el resultado esperado, está en [`docs/guion-demo.md`](docs/guion-demo.md). Para el canal real de WhatsApp (opcional, requiere credenciales de Meta y un túnel HTTPS), ver [`docs/setup-whatsapp.md`](docs/setup-whatsapp.md).

## Canal web (GUI de chat)

Alternativa al canal WhatsApp para probar el agente por navegador, sin depender del número de prueba de Meta ni de un túnel HTTPS (ver Fase 11 en `plandefases.md` y `DECISIONES.md`). Reutiliza el mismo orquestador; solo cambia el transporte.

```bash
USE_FIXTURES=false uv run uvicorn fitosanitarios.canales.web.app_produccion:app --port 8001
```

Abrir `http://localhost:8001/` — soporta texto, adjuntar foto de receta y los botones/listas de las repreguntas (renderizados como chips clickeables a partir de los mismos patrones `[Opción]` / `- opción` que ya emite el formateador). "Nueva conversación" arranca un `thread_id` nuevo sin reiniciar el servidor.

**`USE_FIXTURES=false` es necesario** para un canal real (mismo criterio que `evals/run_evals.py`, ver más abajo): el modelo del agente siempre es Gemini real, pero `leer_receta` y `responder_consulta_normativa` resuelven su LLM interno según este flag — con `USE_FIXTURES=true` (el default de `.env`, pensado para tests) esas dos tools usan un LLM fake y degradan en silencio (p. ej. cualquier foto da "no pude leer la imagen"). El servidor loguea un warning al arrancar si detecta el flag en `true`.

Para medir la exactitud de ruteo contra el LLM real (sale a la red, no es parte de `pytest`):

```bash
USE_FIXTURES=false uv run python evals/run_evals.py
```

## Estado del proyecto

**Fases 0 a 11 completadas — proyecto listo para entrega y defensa.** (Setup; Dominio y contratos; Scraper SENASA; Ingesta SIG y normativa; `leer_receta`; Tools de validación y dictamen; `responder_consulta_normativa`; Orquestador; Canal WhatsApp; Extensiones; Demo y documentación). El núcleo experto queda expuesto de punta a punta: webhook FastAPI, cliente de Graph API, normalización de número argentino y dos notebooks de demo (`demo_e2e.ipynb`, `demo_sin_whatsapp.ipynb`) verificados corriendo con kernel limpio contra Gemini y Postgres reales. **Prueba manual con el número de prueba real de Meta verificada (12/09/2026):** cloudflared + servidor local + webhook suscripto, mensaje real recibido y respondido de punta a punta — ver `docs/setup-whatsapp.md` y `DIFICULTADES.md` por los dos ajustes de configuración que hicieron falta.

Documentos de la Fase 1: [`docs/modelo-datos.md`](docs/modelo-datos.md) (diagrama ER + consultas SQL de las tools RAG), [`docs/matriz-parametros.md`](docs/matriz-parametros.md), [`docs/especificacion-plantillas.md`](docs/especificacion-plantillas.md), [`docs/contrato-insumos.md`](docs/contrato-insumos.md).

Catálogo SENASA (Fase 2): listado completo real cargado (7.370 productos), detalle completo de una muestra de 187 (el resto queda como corrida de fondo pendiente, ver `DECISIONES.md`). Snapshot versionado en `data/senasa/snapshot/` (fuera de git; fixtures de ~50 productos reales en `tests/fixtures/senasa/` sí están versionadas).

Insumos SIG/normativa (Fase 3): pipeline completo (`validador.py`, `loader_geo.py`, `loader_normativa.py`, `loader_reglas.py`) probado de punta a punta contra Postgres real con fixtures sintéticas (2 localidades, normativa provincial y nacional) — ver `docs/validacion-insumos.md`. Los insumos reales de las 10 localidades del caso de estudio todavía no los subió el equipo.

`leer_receta` (Fase 4): extracción multimodal (Gemini real) verificada contra 3 imágenes sintéticas con 3/3 aciertos — ver `docs/casos-leer-receta.md`.

Tools de validación y dictamen (Fase 5): `validar_producto_registro`, `consultar_productos`, `evaluar_riesgo` y `evaluar_viabilidad_legal` probadas de punta a punta contra Postgres real (catálogo SENASA + localidades; hasta el 26/09/2026 eran localidades inventadas, San Carlos Centro y Colonia Vecina, y desde entonces los tests usan una copia de los insumos reales), incluidos los 3 resultados del dictamen (APTA, OBSERVADA, NO_EVALUABLE) y el caso exacto del plan (lote a 80 m de una escuela con regla de 100 m).

`responder_consulta_normativa` (Fase 6): RAG con verificación de citas en código (una cita alucinada por el LLM se descarta y queda como advertencia, nunca pasa). `RAG_UMBRAL_SIMILITUD` recalibrado de 0,75 a 0,35 con scores reales — ver `DECISIONES.md`. En el camino se encontró y corrigió un bug real: tests de integración con un modelo de embeddings fake estaban corrompiendo silenciosamente los embeddings reales de la base de desarrollo cada vez que corría la suite completa.

Orquestador (Fase 7): agente LangGraph (`create_agent` + `ToolStrategy(RespuestaAgente)`) con las 6 tools, límite de repreguntas por campo, log estructurado por turno (`operacion.turno`) y formateo a mensajes de WhatsApp. Evaluado con un dataset de 41 conversaciones reales contra Gemini real (`evals/`): 89 % de exactitud de ruteo (24/27 casos con tool esperada). El propio proceso de evaluación encontró y corrigió dos bugs reales: una excepción no controlada de una tool que rompía el turno entero (ahora degrada a `tipo="error"`), y un caso de dosis ambigua entre adversidades donde se comparaba contra un rango incorrecto en vez de devolver "no verificable". Limitaciones documentadas: sin rotación de API key para el LLM del agente (a diferencia del cliente Gemini standalone) y contador de repreguntas en memoria de proceso, no persistido — ver `DECISIONES.md`.

Canal WhatsApp (Fase 8): webhook FastAPI (`canales/whatsapp/webhook.py`) con handshake, validación de firma en tiempo constante, deduplicación por `message.id` persistida en Postgres (`operacion.mensaje_whatsapp`) y procesamiento en background; cliente de Graph API (texto, botones, listas, descarga de media); normalización del número argentino en un único punto. Se encontró y resolvió un problema real de diseño: pedirle al LLM que transporte una foto real como argumento de tool (`imagen_base64`) es inviable por el límite de tokens de salida — se resolvió con una tool "ligada" a la imagen del turno por clausura, sin argumentos (ver `DECISIONES.md`). `notebooks/demo_sin_whatsapp.ipynb` corrido de punta a punta con kernel limpio contra Gemini y Postgres reales, como plan B de la defensa. Pendiente (requiere credenciales/teléfono reales del usuario): la prueba manual con el número de prueba de Meta a través de un túnel HTTPS — ver `docs/setup-whatsapp.md`.

Extensiones (Fase 9): `resolver_vehiculo` (interpreta en lenguaje natural el equipo de aplicación contra un catálogo chico curado a mano, sin embeddings), `registrar_evento` (inicio/fin de una aplicación real, asociada a receta+vehículo+lote) y `consultar_agenda` (tareas del día de un operario con su estado, reusando `fecha_prevista` de `operacion.receta`). Alcance definido junto con el usuario en esta misma sesión, ya que ni la skill ni el material fuente especifican estos RF — ver `plandefases.md` y `DECISIONES.md`. Decisión de diseño clave: `registrar_evento`/`consultar_agenda` obtienen el `thread_id` del operario inyectando un `config: RunnableConfig` en la tool (no expuesto al LLM), verificado empíricamente con un test de ruteo antes de construir el resto de la fase.

Demo, documentación y defensa (Fase 10): [`docs/guion-demo.md`](docs/guion-demo.md) con los 6 casos obligatorios (APTA, OBSERVADA, consulta de productos, repregunta, fuera de dominio, no resuelto) más 3 adicionales, todos verificados contra datos reales; `notebooks/demo_e2e.ipynb` corrido de punta a punta con kernel limpio. Al armar el guion se encontró y corrigió un bug real que venía arrastrándose desde la Fase 7 sin diagnosticar: `servicios/dosis.py` solo reconocía la unidad `"cm³"` con el superíndice unicode, nunca `"cm3"` (como lo escribe cualquiera desde un celular) — daba `NO_EVALUABLE` en el caso APTA exacto del plan. `evals/run_evals.py` (dos corridas consecutivas, mismo resultado): 79 % de exactitud de ruteo, por debajo del objetivo de 90 % — reportado sin inflar el número, con el análisis caso por caso de por qué en `DECISIONES.md` (ninguno es una regresión de esta fase; la mitad son repreguntas correctas que la métrica cuenta mal, la otra mitad es un patrón preexistente ya documentado desde antes de la Fase 8).

Canal web (Fase 11): GUI de chat (`canales/web/`) como alternativa al canal WhatsApp para desarrollo y demo — decidido con el usuario tras cargar los insumos reales de un único municipio, tras encontrar el canal WhatsApp poco confiable para iterar rápido en las pruebas. Reutiliza el mismo `orquestador/turno.py::ejecutar_turno` de WhatsApp (misma separación LLM-orquesta/núcleo-decide, mismo checkpointer Postgres); solo cambia el transporte: HTML+JS autocontenido sin dependencias externas, con equivalentes de navegador para las modalidades de entrada de WhatsApp que usa el agente (texto, `<input type=file>` para la foto de receta, botones/listas renderizados como chips a partir de los mismos patrones de texto `[Opción]`/`- opción` que ya emitía el formateador). El canal WhatsApp (Fase 8) no se tocó — queda como implementación futura, ver `docs/setup-whatsapp.md`.
