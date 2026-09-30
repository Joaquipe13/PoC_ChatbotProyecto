# Agente de recetas fitosanitarios (TP2 IA)

POC de un agente conversacional por WhatsApp que lee recetas agronómicas de fitosanitarios, las contrasta con el registro de SENASA y la normativa de las localidades cargadas (El Trébol, Sastre y San Jorge, en Santa Fe, más la ley provincial), y dictamina si la aplicación es viable/legal.

- Plan de trabajo: [`plandefases.md`](plandefases.md) — leerlo antes de tocar código, identificar la fase en curso y trabajar solo en esa fase.
- Arquitectura, contratos y reglas de negocio: skill `agente-fitosanitarios` (`.claude/skills/agente-fitosanitarios/SKILL.md`).
- Decisiones tomadas y por qué: [`DECISIONES.md`](DECISIONES.md). Resumen para arrancar: [`DECISIONES_PRINCIPALES.md`](DECISIONES_PRINCIPALES.md).
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
uv run python -m pytest -q
uv run ruff check .
```

Los comandos van con `python -m` (`python -m pytest`, `python -m notebook`, `python -m uvicorn`) y no con el ejecutable directo (`uv run pytest`, `uv run jupyter`): con un venv creado sobre el Python de la Microsoft Store, los ejecutables que arma uv fallan con "uv trampoline failed to canonicalize script path".

Los tests nunca salen a la red: con `USE_FIXTURES=true` (default) el LLM es un fake determinista y no hace falta ninguna API key.

## Correr la demo

Con Postgres levantado y al menos una `GEMINI_API_KEY_*` real en `.env`:

```bash
uv run python -m notebook notebooks/demo_e2e.ipynb   # los casos del guion de la demo
```

Correr todas las celdas con kernel limpio ("Restart & Run All"): cada celda es un caso, con el mensaje exacto y el resultado esperado. `notebooks/demo_sin_whatsapp.ipynb` es un recorrido más corto: un caso por tipo de consulta. Para el canal real de WhatsApp (opcional, requiere credenciales de Meta y un túnel HTTPS), ver [`docs/setup-whatsapp.md`](docs/setup-whatsapp.md).

## Chat desde un notebook

Para conversar con el bot sin WhatsApp (sin el número de prueba de Meta ni un túnel HTTPS): `notebooks/chat.ipynb`, con el mismo orquestador y el mismo formato de respuesta que WhatsApp.

```bash
docker compose up -d db
uv run python -m notebook notebooks/chat.ipynb
```

La celda de ejemplo con foto usa `data/recetas_ejemplo/`, que no está en git: en un clon nuevo, generar las recetas antes con `uv run python scripts/generar_recetas_ejemplo_el_trebol.py`.

Correr la celda de preparación y escribir en el chat: texto, foto de una receta (*Foto*) y las opciones del bot (`[Confirmar] [Corregir]`, `[Agendar] [No, gracias]`) como botones. Sin widgets: `enviar("mensaje")`, `enviar(foto="ruta.jpg")` y `nueva()`. El notebook usa `canales/notebook.py::Conversacion`, que también sirve desde un script. Fija `USE_FIXTURES=false`: con `true` (el default de `.env`, pensado para tests) `leer_receta` y las respuestas con RAG usan un LLM fake.

Hasta el 28/09/2026 había un canal web (`canales/web/`, Fase 11); se sacó y lo reemplaza este notebook (ver `DECISIONES.md`).

Para medir la exactitud de ruteo contra el LLM real (sale a la red, no es parte de `pytest`):

```bash
USE_FIXTURES=false uv run python evals/run_evals.py
```

## Estado del proyecto

**Fases 0 a 10 y 12 completadas (la 11 se retiró) — proyecto listo para entrega y defensa.** (Setup; Dominio y contratos; Scraper SENASA; Ingesta SIG y normativa; `leer_receta`; Tools de validación y dictamen; `responder_consulta_normativa`; Orquestador; Canal WhatsApp; Extensiones; Demo y documentación). El núcleo experto queda expuesto de punta a punta: webhook FastAPI, cliente de Graph API, normalización de número argentino y dos notebooks de demo (`demo_e2e.ipynb`, `demo_sin_whatsapp.ipynb`) verificados corriendo con kernel limpio contra Gemini y Postgres reales. **Prueba manual con el número de prueba real de Meta verificada (12/09/2026):** cloudflared + servidor local + webhook suscripto, mensaje real recibido y respondido de punta a punta — ver `docs/setup-whatsapp.md` y `DIFICULTADES.md` por los dos ajustes de configuración que hicieron falta.

Documentos de la Fase 1: [`docs/modelo-datos.md`](docs/modelo-datos.md) (diagrama ER + consultas SQL de las tools RAG), [`docs/matriz-parametros.md`](docs/matriz-parametros.md), [`docs/especificacion-plantillas.md`](docs/especificacion-plantillas.md), [`docs/contrato-insumos.md`](docs/contrato-insumos.md).

Catálogo SENASA (Fase 2): listado completo real cargado (7.370 productos), detalle completo de una muestra de 187 (el resto queda como corrida de fondo pendiente, ver `DECISIONES.md`). Snapshot versionado en `data/senasa/snapshot/` (fuera de git; fixtures de ~50 productos reales en `tests/fixtures/senasa/` sí están versionadas).

Insumos SIG/normativa (Fase 3): pipeline completo (`validador.py`, `loader_geo.py`, `loader_normativa.py`, `loader_reglas.py`) cargado con los insumos reales: El Trébol, Sastre y San Jorge (Santa Fe) más la Ley 11.273 y su decreto. No se llegó a las 10 localidades del plan. `tests/fixtures/insumos/` es una copia congelada de esos insumos (desde el 26/09/2026 los tests no usan datos inventados).

`leer_receta` (Fase 4): extracción multimodal (Gemini real) verificada contra 3 imágenes sintéticas con 3/3 aciertos.

Tools de validación y dictamen (Fase 5): `validar_producto_registro`, `consultar_productos`, `evaluar_riesgo` y `evaluar_viabilidad_legal` probadas de punta a punta contra Postgres real (catálogo SENASA + localidades; hasta el 26/09/2026 eran localidades inventadas, San Carlos Centro y Colonia Vecina, y desde entonces los tests usan una copia de los insumos reales), incluidos los 3 resultados del dictamen (APTA, OBSERVADA, NO_EVALUABLE) y el caso exacto del plan (lote a 80 m de una escuela con regla de 100 m).

`responder_consulta_normativa` (Fase 6): RAG con verificación de citas en código (una cita alucinada por el LLM se descarta y queda como advertencia, nunca pasa). `RAG_UMBRAL_SIMILITUD` recalibrado de 0,75 a 0,35 con scores reales — ver `DECISIONES.md`. En el camino se encontró y corrigió un bug real: tests de integración con un modelo de embeddings fake estaban corrompiendo silenciosamente los embeddings reales de la base de desarrollo cada vez que corría la suite completa.

Orquestador (Fase 7): agente LangGraph (`create_agent` + `ToolStrategy(RespuestaAgente)`) con las 6 tools, límite de repreguntas por campo, log estructurado por turno (`operacion.turno`) y formateo a mensajes de WhatsApp. Evaluado con un dataset de 41 conversaciones reales contra Gemini real (`evals/`): 89 % de exactitud de ruteo (24/27 casos con tool esperada). El propio proceso de evaluación encontró y corrigió dos bugs reales: una excepción no controlada de una tool que rompía el turno entero (ahora degrada a `tipo="error"`), y un caso de dosis ambigua entre adversidades donde se comparaba contra un rango incorrecto en vez de devolver "no verificable". Limitación documentada: el contador de repreguntas vive en memoria del proceso, no persistido — ver `DECISIONES.md`. (La rotación de API keys en el agente se agregó el 28/09/2026, con hasta 5 keys.)

Canal WhatsApp (Fase 8): webhook FastAPI (`canales/whatsapp/webhook.py`) con handshake, validación de firma en tiempo constante, deduplicación por `message.id` persistida en Postgres (`operacion.mensaje_whatsapp`) y procesamiento en background; cliente de Graph API (texto, botones, listas, descarga de media); normalización del número argentino en un único punto. Se encontró y resolvió un problema real de diseño: pedirle al LLM que transporte una foto real como argumento de tool (`imagen_base64`) es inviable por el límite de tokens de salida — se resolvió con una tool "ligada" a la imagen del turno por clausura, sin argumentos (ver `DECISIONES.md`). `notebooks/demo_sin_whatsapp.ipynb` corrido de punta a punta con kernel limpio contra Gemini y Postgres reales, como plan B de la defensa. Probado de punta a punta con el número de prueba de Meta a través de un túnel HTTPS — ver `docs/setup-whatsapp.md` y `DIFICULTADES.md`.

Extensiones (Fase 9): `resolver_vehiculo` (interpreta en lenguaje natural el equipo de aplicación contra un catálogo chico curado a mano, sin embeddings), `registrar_evento` (inicio/fin de una aplicación real, asociada a receta+vehículo+lote) y `consultar_agenda` (tareas del día de un operario con su estado, reusando `fecha_prevista` de `operacion.receta`). Alcance definido junto con el usuario en esta misma sesión, ya que ni la skill ni el material fuente especifican estos RF — ver `plandefases.md` y `DECISIONES.md`. Decisión de diseño clave: `registrar_evento`/`consultar_agenda` obtienen el `thread_id` del operario inyectando un `config: RunnableConfig` en la tool (no expuesto al LLM), verificado empíricamente con un test de ruteo antes de construir el resto de la fase.

Demo, documentación y defensa (Fase 10): el guion de la demo (hoy en `notebooks/demo_e2e.ipynb`) con los 6 casos obligatorios (APTA, OBSERVADA, consulta de productos, repregunta, fuera de dominio, no resuelto) más 3 adicionales, todos verificados contra datos reales; `notebooks/demo_e2e.ipynb` corrido de punta a punta con kernel limpio. Al armar el guion se encontró y corrigió un bug real que venía arrastrándose desde la Fase 7 sin diagnosticar: `servicios/dosis.py` solo reconocía la unidad `"cm³"` con el superíndice unicode, nunca `"cm3"` (como lo escribe cualquiera desde un celular) — daba `NO_EVALUABLE` en el caso APTA exacto del plan. `evals/run_evals.py` (dos corridas consecutivas, mismo resultado): 79 % de exactitud de ruteo, por debajo del objetivo de 90 % — reportado sin inflar el número, con el análisis caso por caso de por qué en `DECISIONES.md` (ninguno es una regresión de esta fase; la mitad son repreguntas correctas que la métrica cuenta mal, la otra mitad es un patrón preexistente ya documentado desde antes de la Fase 8).

Canal web (Fase 11): se sacó el 28/09/2026 y lo reemplaza `notebooks/chat.ipynb` (ver `DECISIONES.md`).

Evaluación conversacional (Fase 12): un usuario simulado conversa con el bot por el mismo camino que WhatsApp, con invariantes automáticos sobre cada conversación — ver [`evals/README.md`](evals/README.md).

Limpieza del 29/09/2026: se borró el código que quedó sin uso cuando la localidad pasó a resolverse por nombre (punto en polígono y distancias al lote, `servicios/geo.py`), más otros restos sin llamadores, y los docs de prueba manual y guiones que se superponían (ver `DECISIONES.md`).
