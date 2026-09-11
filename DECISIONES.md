# Decisiones

## Fase 4 — `leer_receta`

### Corrección a la Fase 1: `Receta` no tenía campo `adversidad`

Al diseñar `extraccion_receta.py` se encontró que `dominio/modelos.py::Receta` (Fase 1) no tenía un campo `adversidad` a nivel receta -- solo `RecetaItem.adversidad`, por producto. Pero la plantilla de referencia de la skill (confirmación de receta) muestra `adversidad` como un campo único de la receta completa ("*Adversidad:* malezas de hoja ancha"), no por producto. Se agregó `Receta.adversidad: str | None` y la columna correspondiente `operacion.receta.adversidad TEXT` en la migración 003 (todavía no hay datos reales cargados en esa tabla, se pudo editar la migración directamente sin migración incremental). `RecetaItem.adversidad` queda para el caso, menos común, de que un ítem individual tenga una adversidad distinta a la de la receta.

### API real de LangChain verificada: `@tool(nombre, args_schema=..., response_format="content_and_artifact")` funciona tal cual en `langchain-core` 1.6.3

Confirmado instanciando la tool de verdad (no solo leyendo documentación): `leer_receta.name`, `.args_schema` y `.response_format` devuelven lo esperado. Coincide con lo que asumía la skill.

### Cliente Gemini extendido con `generar_con_imagen` (multimodal)

`llm/client.py` tenía solo `generar(prompt)` (texto). Se agregó `generar_con_imagen(imagen: bytes, prompt, *, system=None, mime_type="image/jpeg")`, reutilizando la misma rotación de keys y manejo de cuota que `generar`. Verificado con `google.genai.types.Part.from_bytes` + una lista `[Part, texto]` como `contents` -- confirmado funcionando contra la API real (ver más abajo). Solo `ClienteGemini` lo implementa; `ClienteGroq` no (la skill designa a Gemini como "multimodal, principal").

### Umbral de confianza por campo: 0,6

No estaba fijado por la skill ni por el plan (dejaba "confianza por campo" sin un número). Se eligió 0,6 como punto de partida razonable (ni tan laxo que acepte lecturas dudosas, ni tan estricto que repregunte todo el tiempo con una extracción típicamente buena). **Sin calibrar contra un volumen real de fotos** -- ajustar en base a los resultados de la Fase 10 (demo) o antes si hay quejas de repreguntas de más/de menos.

### OCR clásico (Tesseract) como segunda señal: no implementado en esta sesión

La tarea 3 de la Fase 4 pide "implementar el fallback/comparación con OCR clásico (Tesseract) como segunda señal, no como reemplazo" del LLM multimodal. Tesseract sigue sin estar instalado en esta máquina (mismo hallazgo que la Fase 3, ver DIFICULTADES.md), y la extracción multimodal por sí sola dio 100% de precisión en la verificación manual contra 3 imágenes reales (ver abajo). Se decide **no** escribir código de comparación con OCR que no se puede ejercitar ni una vez en esta sesión (se preferiría código real y probado a código muerto). Pendiente para cuando Tesseract esté disponible: usar `pytesseract.image_to_string` sobre la misma imagen y comparar contra los campos que extrajo el LLM (coincidencia de substring, por ejemplo) para subir o bajar la confianza reportada, nunca para reemplazar la extracción del LLM.

### Verificación manual contra el LLM real (tarea 7): 3/3 casos correctos

Corrido el 12/09/2026 contra Gemini real, sobre imágenes sintéticas (no hay fotos reales de recetas disponibles para esta POC -- generadas con `scripts/generar_fixtures_recetas.py`, texto renderizado con PIL, no fotografías):

- `01_completa.jpg` (todos los campos presentes, mismo caso que el ejemplo de referencia de la skill: soja, lote 4, malezas de hoja ancha, Glifosato 48% 2 L/ha, 35 ha, terrestre): los 6 campos extraídos con confianza 1.0, `faltantes=[]`.
- `07_multiples_faltantes.jpg` (solo cultivo y producto presentes en la imagen): cultivo y producto extraídos correctamente con confianza 1.0; lote, adversidad, superficie y tipo de aplicación devueltos como `null`/confianza 0.0 -- se generaron los 4 `CampoFaltante` esperados, ninguno de más ni de menos.
- `10_no_es_receta.jpg` (una factura, no una receta): el LLM respondió `{"legible": false}` tal cual se le pidió en el prompt.

No se corrieron las 7 imágenes restantes contra el LLM real (costo/tiempo); quedan cubiertas solo por los tests con LLM fake (`tests/tools/test_leer_receta.py`, `tests/servicios/test_extraccion_receta.py`), que fijan la expectativa por caso pero no validan que el LLM real lea la imagen igual.

## Fase 3 — Ingesta SIG y normativa

### Idempotencia de `loader_normativa.py`/`loader_reglas.py`: borrar y reinsertar por alcance, no `ON CONFLICT`

`territorio.norma.archivo` no es único globalmente (el mismo nombre de PDF puede repetirse en distintas carpetas de localidades distintas), así que un `ON CONFLICT` compuesto sería más complejo que el beneficio que da acá. En cambio, antes de cargar una localidad/provincia/ámbito nacional, se borran sus normas existentes (`DELETE ... WHERE localidad_id = %s`, con cascada a `articulo` y `regla_distancia` por las FK `ON DELETE CASCADE`) y se reinsertan desde cero. Mismo patrón que ya usaba `zona_protegida` en `loader_geo.py` (Fase 1). Consecuencia: los archivos de insumos son la fuente de la verdad, no un merge incremental -- correr el loader dos veces da el mismo resultado, pero un cambio manual directo en la base se pierde en la siguiente carga.

### Regex de artículos: soporta "Art.", "Artículo"/"Articulo" (con o sin tilde) y "N°/Nº" antes del número

Diseñado y verificado contra un PDF real generado con fpdf2 (sin biblioteca de renderizado con tildes especiales, así que el texto de las fixtures usa "Articulo" sin tilde). Encontrado en el camino: la primera versión del regex solo aceptaba "í" acentuada, no "i" simple -- fallaba en "Articulo 8.-" real. Corregido a `[ií]culo`. No soporta numeración romana (caso borde mencionado en el plan); un PDF así no matchea ningún artículo y `chunkear_articulos` devuelve `[]` (no se inventa un artículo "1" con todo el texto adentro).

### Tesseract no probado con OCR real

Tesseract OCR no está instalado en esta máquina de desarrollo (`tesseract --version` → command not found). `pytesseract` sí está instalado como dependencia Python, pero `extraer_texto_o_ocr()` nunca llegó a ejecutar una imagen real por Tesseract en esta sesión: todos los PDF de las fixtures tienen capa de texto (generados con fpdf2, no son escaneos). El código captura cualquier excepción del bloque de OCR (incluido "Tesseract no está instalado") y sigue marcando `requiere_revision=True` sin rompar la carga -- pero el resultado real de OCR sobre un PDF escaneado de verdad queda sin validar hasta que se instale Tesseract (`https://github.com/UB-Mannheim/tesseract/wiki` para Windows) y se pruebe con un PDF escaneado real o una fixture generada a partir de una imagen.

## Fase 2 — Scraper SENASA y base de productos

### Forma real de la API de SENASA (difiere de lo que asumía la skill)

Verificado en vivo el 12/09/2026 (endpoints de listado y detalle, ~190 productos reales). Diferencias concretas con la descripción original de la skill:

- `claseToxicologica` en el **detalle** es un objeto `{id, claseTox, precaucion, advertencia, color}` (ej. `{claseTox: "IV", color: "VERDE", advertencia: "PRODUCTO QUE NORMALMENTE NO OFRECE PELIGRO"}`), no el string concatenado `"III / LIGERAMENTE PELIGROSO / AZUL"` que describía la skill. La banda (`Ia|Ib|II|III|IV`) sale directo de `claseTox`; el color, de `color` (con la variante "AMAREILLO" documentada en la skill, no observada en esta muestra pero igual soportada). En el **listado**, `claseToxicologica` sigue siendo un string simple (`"IV"`, `"S/D"`).
- `productoDocumentos[]` trae distintos **tipos de documento** identificados por el campo `nombre`: `"HDS"` (hoja de seguridad, sin dosis por cultivo) vs. `"Marbete"` (la etiqueta con la tabla de dosis, lo que realmente sirve para extracción). La skill no distinguía esto; el loader y `extraccion_marbete.py` filtran explícitamente por `nombre == "Marbete"` (ver `DocumentoProducto.es_marbete` en `cliente.py`).
- El detalle real pesa más de lo esperado (57-90 KB incluso **sin** PDFs) por redundancia propia de Spring Data REST: el objeto `producto` completo viene reincrustado una vez por cada `principioActivo`, cada `envase`, cada `productoFirma`, etc. `DetalleProducto` (cliente.py) solo mapea los campos que el pipeline necesita y descarta el resto (pydantic `extra="ignore"`), en vez de intentar modelar la respuesta completa.
- `totalElements` del listado a la fecha: 7.370 (la skill decía "≈ 7.374" al 11/09; la diferencia es esperable, el catálogo cambia).

### Snapshot en JSON Lines, no `.parquet`

El ejemplo original del plan (`data/senasa/snapshot/latest.parquet`) asumía un dump columnar. La estructura real por producto es profundamente anidada y de longitud variable (N principios activos, N usos registrados, N documentos por producto), lo que no mapea limpio a un esquema parquet plano sin aplanar antes. Se usa `.jsonl` (una línea por producto, `{"listado": {...}, "detalle": {...}|null}`) como snapshot versionado: el plan permitía "dump o parquet" explícitamente. `senasa/loader.py` (`construir_snapshot`/`leer_snapshot`) implementa esto.

### Rotación de Gemini: 5 slots, no 3

La skill y `plandefases.md` documentan `GEMINI_API_KEY_1..3`. El usuario cargó 5 keys reales en `.env` (con nombres `GEMINI_API_KEY`, `GEMINI_API_KEY2..5`, sin el guion bajo antes del número). Se renombraron a la convención documentada (`GEMINI_API_KEY_1..5`) y se extendió `config.py`/`.env.example` a 5 slots en vez de 3, ya que más keys de rotación es estrictamente mejor contra 429 y el usuario ya las tenía disponibles. Documentado acá porque se aparta del número exacto que fija la skill.

### Extracción de marbete por LLM: verificada con un caso real

Task 8 de la Fase 2 pide revisión manual de una muestra antes de dar la extracción por buena. Se probó `extraccion_marbete.py` con Gemini real contra la página 9 del marbete de SENASA reg. 36.515 ("DECIS 10 EC", Bayer) -- una tabla CULTIVO/PLAGA/DOSIS de 12 filas. Resultado: **12/12 filas extraídas correctamente** (cultivo, adversidad con nombre científico, dosis), revisadas a mano contra el texto original. Limitación encontrada: cuando la unidad de dosis está una sola vez en el encabezado de la tabla ("DOSIS (ml/hl)") y no se repite por fila, el LLM extrae la dosis como número pelado ("5", no "5 ml/hl"), que `parser_dosis.py` no puede parsear tal cual (le falta la unidad). Pendiente para cuando se generalice esta extracción: instruir al prompt para que propague la unidad del encabezado a cada fila, o post-procesar con el contexto de la tabla completa en vez de fila por fila.

### Carga real verificada: catálogo completo (listado) + muestra de detalle

Estado final de esta sesión, cargado en Postgres local (Docker) desde el snapshot `data/senasa/snapshot/productos_2026-09-12.jsonl`:

| Tabla | Filas |
|---|---|
| `catalogo.producto` | 7.370 (el listado completo real) |
| `catalogo.firma` | 435 |
| `catalogo.principio_activo` | 105 |
| `catalogo.cultivo` | 73 |
| `catalogo.adversidad` | 185 |
| `catalogo.uso_registrado` | 1.031 |

Los 7.370 productos tienen datos del **listado** (marca, firma, clase toxicológica simple, principios activos en texto). Solo 187 de ellos (los crawleados con detalle en esta sesión) tienen además banda toxicológica normalizada, principios activos estructurados con concentración/unidad, y los 1.031 usos registrados (de esos 187, 28 tenían `aplicacionesPorProducto`, que es de donde salen los usos). **El detalle completo de los ~7.180 productos restantes no se bajó en esta sesión** por tiempo (a ~1 req/s son varias horas) -- queda como tarea de fondo, no bloquea el resto de las fases porque Fase 4-6 pueden avanzar con esto y datos stub, y la Fase 5 ya tiene casos reales (con y sin usos registrados) para probar contra.

Ineficiencia encontrada y no resuelta en esta sesión: `loader.py` llama `modelo_embeddings.encode()` una vez por texto (marca, principio activo, cultivo, adversidad) en vez de acumular y embeber en lotes. La carga de 7.370 productos tardó ~15 minutos: aceptable para esta corrida, pero se recomienda batchear antes de correr el loader sobre un detalle completo (~7.370 x varios embeddings cada uno).

### PDFs separados a disco durante el crawl, no después

Hallazgo real: `crawl_detalle` guardaba el detalle completo con los PDFs en base64 embebidos (un snapshot combinado con solo ~190 productos con documentos llegó a pesar 88 MB). Se corrigió moviendo la separación de PDFs (`productoDocumentos[].contenido` -> archivo en `data/senasa/crudo/documentos/`, campo puesto en `null` en el JSON) al propio `crawl_detalle` (tarea 5 del plan), no a un paso posterior. Snapshot resultante de los mismos ~190 productos: 2,4 MB.

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
