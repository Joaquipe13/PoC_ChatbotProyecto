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

Fases 0 (Setup), 1 (Dominio y contratos), 2 (Scraper SENASA), 3 (Ingesta SIG y normativa), 4 (`leer_receta`) y 5 (Tools de validación y dictamen) completadas. Próxima: **Fase 6 — `responder_consulta_normativa`**, pendiente de confirmación del usuario (ver `plandefases.md`).

Documentos de la Fase 1: [`docs/modelo-datos.md`](docs/modelo-datos.md) (diagrama ER + consultas SQL de las tools RAG), [`docs/matriz-parametros.md`](docs/matriz-parametros.md), [`docs/especificacion-plantillas.md`](docs/especificacion-plantillas.md), [`docs/contrato-insumos.md`](docs/contrato-insumos.md).

Catálogo SENASA (Fase 2): listado completo real cargado (7.370 productos), detalle completo de una muestra de 187 (el resto queda como corrida de fondo pendiente, ver `DECISIONES.md`). Snapshot versionado en `data/senasa/snapshot/` (fuera de git; fixtures de ~50 productos reales en `tests/fixtures/senasa/` sí están versionadas).

Insumos SIG/normativa (Fase 3): pipeline completo (`validador.py`, `loader_geo.py`, `loader_normativa.py`, `loader_reglas.py`) probado de punta a punta contra Postgres real con fixtures sintéticas (2 localidades, normativa provincial y nacional) — ver `docs/validacion-insumos.md`. Los insumos reales de las 10 localidades del caso de estudio todavía no los subió el equipo.

`leer_receta` (Fase 4): extracción multimodal (Gemini real) verificada contra 3 imágenes sintéticas con 3/3 aciertos — ver `docs/casos-leer-receta.md`.

Tools de validación y dictamen (Fase 5): `validar_producto_registro`, `consultar_productos`, `evaluar_riesgo` y `evaluar_viabilidad_legal` probadas de punta a punta contra Postgres real (catálogo SENASA + San Carlos Centro), incluidos los 3 resultados del dictamen (APTA, OBSERVADA, NO_EVALUABLE) y el caso exacto del plan (lote a 80 m de una escuela con regla de 100 m).
