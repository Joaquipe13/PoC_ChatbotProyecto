# Decisiones

Registro de qué se decidió y por qué. Una entrada por decisión relevante, en orden cronológico (más reciente arriba). Formato libre; como mínimo: qué se decidió, por qué, y qué alternativas se descartaron si las hubo.

## Fase 0 — Setup

### Gestor de dependencias: `uv`

Se eligió `uv` sobre `poetry` por velocidad de instalación en CI y simplicidad de `pyproject.toml` estándar (PEP 621) sin secciones propietarias. Era una decisión abierta en `plandefases.md` (#4); se cierra acá. Si el entorno de la cátedra o de la máquina de defensa no tiene `uv` disponible, la alternativa directa es `poetry install` sobre el mismo `pyproject.toml` (puede requerir ajustar `[tool.poetry]` si `poetry` no soporta el formato PEP 621 puro en la versión instalada — **verificar** si se necesita el cambio).

### Imagen Docker de Postgres: `pgvector/pgvector:0.8.6-pg16`

Imagen oficial del proyecto pgvector (no `ankane/pgvector`, deprecada desde pgvector 0.6.0), pinneada a una versión exacta (0.8.6 sobre Postgres 16) en vez del tag rolling `pg16`, para reproducibilidad entre desarrollo y el día de la defensa. `pg_trgm` viene incluido en la imagen base de Postgres (contrib), no requiere instalación aparte.

### SDK de Gemini: `google-genai`

Se usa el paquete `google-genai` (`from google import genai`), no el más viejo `google-generativeai`. Alcanzó disponibilidad general en mayo de 2025 y es el recomendado por Google para funciones nuevas (multimodal, structured output) que se van a necesitar en la Fase 4. Verificado por búsqueda web el 11/09/2026; **verificar** que siga siendo la recomendación vigente antes de la Fase 2/4, que son las primeras que lo usan de verdad.

### `GEMINI_MODEL` por defecto: `gemini-3.5-flash-lite`

Se probó primero con el alias `-latest`, pero se reemplazó por `gemini-3.5-flash-lite` (fijado directamente por el usuario en `.env.example` y `config.py` el 11/09/2026, presumiblemente confirmado en la consola de Google AI Studio). Un alias `-latest` es más resistente a que Google discontinúe una versión puntual, pero una versión fija es más reproducible para tests y demo. **Verificar** antes de la Fase 2 en adelante que este modelo siga vigente y soporte entrada multimodal (necesaria para `leer_receta`, Fase 4); si Google lo discontinúa antes del 30/09, reemplazar acá y en `.env.example`.

### `WHATSAPP_GRAPH_VERSION`: confirmado `v26.0`

El 11/09/2026 no se pudo confirmar con una fuente oficial la versión vigente y se dejó `v23.0` como placeholder marcado `(verificar)`. El 12/09/2026, con credenciales reales cargadas en `.env` (token de System User + `WHATSAPP_PHONE_NUMBER_ID` del número de prueba), se hizo una llamada real de lectura:

```
GET https://graph.facebook.com/v26.0/{WHATSAPP_PHONE_NUMBER_ID}?fields=verified_name,display_phone_number,quality_rating,code_verification_status
```

Respuesta `HTTP 200` con los datos del número de prueba (`verified_name: "Test Number"`, `display_phone_number: "+1 555-604-4720"`). Confirma tres cosas a la vez: `v26.0` es una versión vigente de Graph API, el `WHATSAPP_ACCESS_TOKEN` configurado es válido, y `WHATSAPP_PHONE_NUMBER_ID` es correcto. `.env.example` actualizado a `v26.0`.

**Pendiente para la Fase 8** (no cubierto por este chequeo, que fue de solo lectura): envío real de un mensaje a un destinatario verificado, y el handshake + validación de firma del webhook, que requieren el código de `canales/whatsapp/` y un túnel HTTPS.

### Modelo de embeddings: `sentence-transformers/paraphrase-multilingual-mpnet-base-v2` (confirmado con benchmark)

Ya justificado en `plandefases.md` (decisión abierta #3): buen soporte de español, calidad superior a MiniLM para similitud semántica de nombres de producto y texto normativo, tamaño manejable en CPU.

**Confirmado con benchmark real (Fase 1, tarea 11)** el 12/09/2026, corriendo `scripts/benchmark_embeddings.py` sobre 200 nombres de producto sintéticos en esta máquina (CPU, sin GPU):

- Carga del modelo (primera vez, incluye descarga de ~1 GB): 110,6 s; con el modelo ya cacheado localmente, 10,7 s.
- Embeber 200 nombres: 2,20-2,93 s totales → **11-15 ms/nombre** en batches de 32.
- Dimensión del embedding: 768 (coincide con `vector(768)` en las migraciones de `catalogo` y `territorio`).

A ese ritmo, embeber el catálogo completo de SENASA (~7.374 productos, más principios activos/cultivos/adversidades) es del orden de 1-2 minutos de cómputo puro, insignificante frente al tiempo del crawl (Fase 2, throttled a ~1 req/s). **Decisión cerrada**, no queda como decisión abierta. Dimensión 768 fijada en las migraciones SQL de la Fase 1; si se cambia de modelo más adelante hay que migrar esas columnas `vector` también.

### Excepción de cuota agotada del LLM: detección heurística por texto

No se pudo verificar contra documentación oficial el tipo exacto de excepción que levantan `google-genai` y `groq` ante un 429/cuota agotada. `src/fitosanitarios/llm/client.py` detecta el caso buscando "429", "RESOURCE_EXHAUSTED" o "RATE LIMIT" en el texto de la excepción, en vez de capturar una clase específica. **Verificar** antes de la Fase 2 (primera llamada real) y reemplazar por el tipo de excepción correcto si existe uno más específico.
