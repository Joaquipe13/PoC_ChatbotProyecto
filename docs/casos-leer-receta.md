# Casos de prueba de `leer_receta`

Catálogo de las imágenes sintéticas de `tests/fixtures/recetas/` (generadas con `scripts/generar_fixtures_recetas.py`, no son fotos reales — no hay disponibles para esta POC) y el resultado esperado de cada una. Los tests automatizados (`tests/tools/test_leer_receta.py`) usan el LLM fake con estas expectativas fijadas de antemano; la verificación manual contra el LLM real (tarea 7 de la Fase 4) corrió sobre un subconjunto — ver resultado al final de este documento y en `DECISIONES.md`.

| # | Archivo | Campos presentes | Campos faltantes a propósito | `estado` esperado |
|---|---|---|---|---|
| 1 | `01_completa.jpg` | cultivo, lote, adversidad, producto, superficie, tipo de aplicación | ninguno | `ok` |
| 2 | `02_sin_tipo_aplicacion.jpg` | cultivo, lote, adversidad, producto, superficie | tipo_aplicacion | `faltan_datos` (falta `tipo_aplicacion`) |
| 3 | `03_sin_superficie.jpg` | cultivo, lote, adversidad, producto, tipo de aplicación | superficie_ha | `faltan_datos` (falta `superficie_ha`) |
| 4 | `04_dos_productos.jpg` | cultivo, lote, adversidad, 2 productos, superficie, tipo de aplicación | ninguno | `ok` (2 ítems en `receta.items`) |
| 5 | `05_sin_lote.jpg` | cultivo, adversidad, producto, superficie, tipo de aplicación | lote | `faltan_datos` (falta `lote`) |
| 6 | `06_sin_adversidad.jpg` | cultivo, lote, producto, superficie, tipo de aplicación | adversidad | `faltan_datos` (falta `adversidad`) |
| 7 | `07_multiples_faltantes.jpg` | cultivo, producto | lote, adversidad, superficie, tipo_aplicacion | `faltan_datos` (4 campos) |
| 8 | `08_completa_2.jpg` | cultivo, lote, adversidad, producto, superficie, tipo de aplicación | ninguno | `ok` |
| 9 | `09_borrosa.jpg` | (todos, pero ilegibles por desenfoque) | — | `no_resuelto` (`IMAGEN_ILEGIBLE`) |
| 10 | `10_no_es_receta.jpg` | — (es una factura, no una receta) | — | `no_resuelto` (`IMAGEN_ILEGIBLE`) |

## Reglas de conversión (confianza → campo vs. faltante)

Implementadas en `servicios/extraccion_receta.py::convertir_a_receta_y_faltantes`:

- Cada campo viene del LLM con su propio valor y su propia confianza (0 a 1).
- Confianza `< UMBRAL_CONFIANZA_CAMPO` (0,6 por defecto) o valor `null` → el campo no entra en la `Receta`, entra como `CampoFaltante` con pregunta sugerida y `tipo_entrada` (texto, botones, etc.).
- `productos`: si ningún producto extraído supera el umbral, la lista queda vacía y se agrega un `CampoFaltante` de campo `"productos"`.
- La imagen se marca `legible=false` (vía el propio LLM, o si su respuesta no es JSON válido) → `no_resuelto` con `IMAGEN_ILEGIBLE`, sin intentar extraer nada más.

## Verificación manual contra el LLM real (tarea 7)

Corrida el 12/09/2026 contra Gemini real (`uv run python` puntual, no automatizado en CI — ver DECISIONES.md para el detalle completo):

- `01_completa.jpg`: todos los campos extraídos correctamente con confianza alta.
- `07_multiples_faltantes.jpg`: cultivo y producto extraídos correctamente; lote, adversidad, superficie y tipo de aplicación devueltos como `null`/confianza baja, tal como se esperaba.
- `10_no_es_receta.jpg`: el LLM identificó correctamente que no es una receta (`legible: false`).

No se corrieron las 10 contra el LLM real en esta sesión (costo/tiempo); las 7 restantes quedan cubiertas por los tests automatizados con LLM fake, que fijan la expectativa por caso pero no validan que el LLM real efectivamente lea la imagen así.
