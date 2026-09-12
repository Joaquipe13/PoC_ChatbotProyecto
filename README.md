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

## Estado del proyecto

Fases 0 a 9 completadas (Setup; Dominio y contratos; Scraper SENASA; Ingesta SIG y normativa; `leer_receta`; Tools de validación y dictamen; `responder_consulta_normativa`; Orquestador; Canal WhatsApp; Extensiones). El núcleo experto queda expuesto de punta a punta: webhook FastAPI, cliente de Graph API, normalización de número argentino y `notebooks/demo_sin_whatsapp.ipynb` como plan B, verificado corriendo con kernel limpio contra Gemini y Postgres reales. Falta la prueba manual con el número de prueba real de Meta (requiere credenciales y túnel del usuario, ver `docs/setup-whatsapp.md`). Próxima: **Fase 10 — Demo, documentación y defensa**, pendiente de confirmación del usuario (ver `plandefases.md`).

Documentos de la Fase 1: [`docs/modelo-datos.md`](docs/modelo-datos.md) (diagrama ER + consultas SQL de las tools RAG), [`docs/matriz-parametros.md`](docs/matriz-parametros.md), [`docs/especificacion-plantillas.md`](docs/especificacion-plantillas.md), [`docs/contrato-insumos.md`](docs/contrato-insumos.md).

Catálogo SENASA (Fase 2): listado completo real cargado (7.370 productos), detalle completo de una muestra de 187 (el resto queda como corrida de fondo pendiente, ver `DECISIONES.md`). Snapshot versionado en `data/senasa/snapshot/` (fuera de git; fixtures de ~50 productos reales en `tests/fixtures/senasa/` sí están versionadas).

Insumos SIG/normativa (Fase 3): pipeline completo (`validador.py`, `loader_geo.py`, `loader_normativa.py`, `loader_reglas.py`) probado de punta a punta contra Postgres real con fixtures sintéticas (2 localidades, normativa provincial y nacional) — ver `docs/validacion-insumos.md`. Los insumos reales de las 10 localidades del caso de estudio todavía no los subió el equipo.

`leer_receta` (Fase 4): extracción multimodal (Gemini real) verificada contra 3 imágenes sintéticas con 3/3 aciertos — ver `docs/casos-leer-receta.md`.

Tools de validación y dictamen (Fase 5): `validar_producto_registro`, `consultar_productos`, `evaluar_riesgo` y `evaluar_viabilidad_legal` probadas de punta a punta contra Postgres real (catálogo SENASA + San Carlos Centro), incluidos los 3 resultados del dictamen (APTA, OBSERVADA, NO_EVALUABLE) y el caso exacto del plan (lote a 80 m de una escuela con regla de 100 m).

`responder_consulta_normativa` (Fase 6): RAG con verificación de citas en código (una cita alucinada por el LLM se descarta y queda como advertencia, nunca pasa). `RAG_UMBRAL_SIMILITUD` recalibrado de 0,75 a 0,35 con scores reales — ver `DECISIONES.md`. En el camino se encontró y corrigió un bug real: tests de integración con un modelo de embeddings fake estaban corrompiendo silenciosamente los embeddings reales de la base de desarrollo cada vez que corría la suite completa.

Orquestador (Fase 7): agente LangGraph (`create_agent` + `ToolStrategy(RespuestaAgente)`) con las 6 tools, límite de repreguntas por campo, log estructurado por turno (`operacion.turno`) y formateo a mensajes de WhatsApp. Evaluado con un dataset de 41 conversaciones reales contra Gemini real (`evals/`): 89 % de exactitud de ruteo (24/27 casos con tool esperada). El propio proceso de evaluación encontró y corrigió dos bugs reales: una excepción no controlada de una tool que rompía el turno entero (ahora degrada a `tipo="error"`), y un caso de dosis ambigua entre adversidades donde se comparaba contra un rango incorrecto en vez de devolver "no verificable". Limitaciones documentadas: sin rotación de API key para el LLM del agente (a diferencia del cliente Gemini standalone) y contador de repreguntas en memoria de proceso, no persistido — ver `DECISIONES.md`.

Canal WhatsApp (Fase 8): webhook FastAPI (`canales/whatsapp/webhook.py`) con handshake, validación de firma en tiempo constante, deduplicación por `message.id` persistida en Postgres (`operacion.mensaje_whatsapp`) y procesamiento en background; cliente de Graph API (texto, botones, listas, descarga de media); normalización del número argentino en un único punto. Se encontró y resolvió un problema real de diseño: pedirle al LLM que transporte una foto real como argumento de tool (`imagen_base64`) es inviable por el límite de tokens de salida — se resolvió con una tool "ligada" a la imagen del turno por clausura, sin argumentos (ver `DECISIONES.md`). `notebooks/demo_sin_whatsapp.ipynb` corrido de punta a punta con kernel limpio contra Gemini y Postgres reales, como plan B de la defensa. Pendiente (requiere credenciales/teléfono reales del usuario): la prueba manual con el número de prueba de Meta a través de un túnel HTTPS — ver `docs/setup-whatsapp.md`.

Extensiones (Fase 9): `resolver_vehiculo` (interpreta en lenguaje natural el equipo de aplicación contra un catálogo chico curado a mano, sin embeddings), `registrar_evento` (inicio/fin de una aplicación real, asociada a receta+vehículo+lote) y `consultar_agenda` (tareas del día de un operario con su estado, reusando `fecha_prevista` de `operacion.receta`). Alcance definido junto con el usuario en esta misma sesión, ya que ni la skill ni el material fuente especifican estos RF — ver `plandefases.md` y `DECISIONES.md`. Decisión de diseño clave: `registrar_evento`/`consultar_agenda` obtienen el `thread_id` del operario inyectando un `config: RunnableConfig` en la tool (no expuesto al LLM), verificado empíricamente con un test de ruteo antes de construir el resto de la fase.
