# Dificultades

Registro de qué falló y cómo se resolvió. Una entrada por dificultad relevante, en orden cronológico (más reciente arriba).

## Fase 5 — Tools de validación y dictamen

### Test de `evaluar_riesgo` fallaba por asumir una sola zona "escuela" en el resultado

`test_riesgo_observado_por_distancia_a_escuela` usaba `next(z for z in ... if z["tipo"]=="escuela")` asumiendo que solo iba a haber una zona de tipo escuela en el radio de búsqueda. Con `RADIO_BUSQUEDA_ZONAS_M=2000`, la escuela de colonia-vecina también entra en el radio desde un punto en San Carlos Centro, así que el resultado real trae dos zonas `tipo="escuela"` (la cercana, que no cumple, y la lejana, que sí). El `next()` agarraba la que aparecía primero en la lista, que no siempre era la cercana, y el test fallaba de forma intermitente según el orden de la consulta SQL. Se corrigió filtrando por `not z["cumple"]` en vez de solo por tipo. No es un bug del código de producción: el comportamiento (reglas de la jurisdicción del lote aplicadas a zonas de localidades vecinas) es exactamente el que pide la skill; el bug estaba en la suposición del test.

## Fase 3 — Ingesta SIG y normativa

### Regex de artículos no reconocía "Articulo" sin tilde

Primera versión de `_PATRON_ARTICULO` en `loader_normativa.py` usaba `í?culo` (í acentuada opcional + "culo" literal), pensado para "Artículo". Al probarlo contra el PDF real generado para la fixture de San Carlos Centro (texto "Articulo 8.-", sin tilde porque así se generó el PDF de prueba), no matcheó ningún artículo -- `chunkear_articulos` devolvía `[]`. Causa: el patrón no contemplaba la "i" simple entre "art" y "culo", solo la "í" acentuada opcional. Corregido a `[ií]culo` (acepta cualquiera de las dos). Se detectó de inmediato al probar contra el PDF real en vez de solo con texto sintético en memoria.

### `fpdf2`: `multi_cell` sin resetear X entre llamadas

El script que genera las fixtures de normativa (PDFs de prueba) fallaba con `FPDFException: Not enough horizontal space to render a single character` al segundo `multi_cell()`. Causa: `multi_cell` deja el cursor X desplazado después de escribir, y la siguiente llamada heredaba una posición X reducida (menos ancho disponible) hasta que llegaba a cero. Se corrigió llamando `pdf.set_x(pdf.l_margin)` antes de cada `multi_cell`.

## Fase 2 — Scraper SENASA y base de productos

### `sustanciasActivas` (y otros campos) llegan como `null`, no ausentes

El crawl del listado completo (7.370 productos) falló en el primer intento: `ProductoListado` esperaba `sustancias_activas: str` y un producto (un coadyuvante sin principio activo declarado) trae `"sustanciasActivas": null` explícito en el JSON. `Field(default="")` no alcanza para este caso -- el default de pydantic solo aplica cuando la clave *falta*, no cuando está presente con valor `null`. Se corrigió con un `field_validator(mode="before")` que normaliza `None -> ""` en `marca`, `nombre_firma` y `sustancias_activas` (`cliente.py`). Se agregó test de regresión (`test_producto_listado_tolera_sustancias_activas_null`).

### Migración sin `UNIQUE` en `firma.nombre` y `adversidad.nombre_comun`

Al escribir `loader.py` (que hace upsert por `ON CONFLICT` para deduplicar firmas/adversidades entre productos) se encontró que esas dos columnas no tenían restricción `UNIQUE` en la migración de la Fase 1 -- sin eso, `ON CONFLICT DO NOTHING`/`DO UPDATE` no tiene nada contra qué chocar y cada producto insertaría una fila nueva en vez de reusar la existente. Se corrigió agregando `UNIQUE` a ambas columnas en `001_catalogo.sql` (ya no había datos reales cargados todavía, solo se había verificado que la migración corriera; se recreó el volumen de Docker para aplicar el cambio limpio).

### Falso hallazgo inicial: "0/180 con aplicaciones/documentos" (bug de un script propio, no de los datos)

Al revisar los resultados del crawl de 180 productos (muestreados cada 40 posiciones a lo largo de los 7.370), un script ad hoc de inspección buscaba las claves `aplicacionesPorProducto`/`productoDocumentos` (camelCase, como vienen de la API) contra `detalle.jsonl`, que en realidad se escribe con `DetalleProducto.model_dump_json()` **sin** `by_alias=True` -- o sea con los nombres de campo en snake_case (`aplicaciones_por_producto`, `producto_documentos`). El resultado "0 de 180" era un falso negativo del propio script, no un hallazgo real sobre los datos de SENASA. Se corrigió el script de inspección usando las claves correctas. Cifras reales sobre los 187 productos con detalle bajados en esta sesión (180 al azar + 7 elegidos a mano):

- 28 (15 %) con `aplicaciones_por_producto` no vacío.
- 105 (56 %) con algún documento; 96 (51 %) con un documento `Marbete` específicamente.

Estas proporciones son consistentes con la muestra de 27 productos que había relevado la cátedra (skill: "~15 % con aplicacionesPorProducto, ~63 % con marbete/documento"). No hay evidencia de que una muestra al azar del catálogo completo rinda peor que elegir productos a mano; se descarta la hipótesis que se había anotado acá antes de detectar el bug.

## Fase 0 — Setup

### Puerto 5432 ocupado por otro proyecto

Al levantar `docker compose up -d db` por primera vez, el puerto 5432 ya estaba tomado por un contenedor de otro proyecto en esta misma máquina (`asistente_viajes_db`, también `pgvector/pgvector`). Se resolvió mapeando este proyecto al puerto 5433 en `docker-compose.yml` y actualizando `DATABASE_URL` en `.env.example` en consecuencia. Si se levanta este proyecto en otra máquina sin ese conflicto, el puerto 5433 sigue funcionando igual (no depende de que 5432 esté libre).

### `uv` no estaba instalado en la máquina de desarrollo

CI usa `uv sync --dev`, pero la máquina de desarrollo local no lo tenía instalado. Para verificar los criterios de aceptación de la Fase 0 se usó un `venv` + `pip install -e . pytest ruff` como alternativa puntual. Recomendado instalar `uv` (`https://docs.astral.sh/uv/getting-started/installation/`) para el flujo de desarrollo día a día, ya que es lo que corre en CI.

**Resuelto (11/09/2026):** se instaló `uv` 0.12.13 con el instalador oficial de Windows (`irm https://astral.sh/uv/install.ps1 | iex`), en `C:\Users\joaqu\.local\bin`. `uv sync --dev` y `uv run pytest`/`uv run ruff check .` corren igual que en CI. Falta agregar `C:\Users\joaqu\.local\bin` al PATH de forma permanente (por ahora se antepone en cada sesión de PowerShell) o reiniciar la terminal para que quede disponible sin hacerlo a mano.

### `ruff` marcó `pytest.raises(Exception)` como demasiado genérico (regla B017)

Los tests que esperaban que `Settings(...)` fallara por falta de una variable requerida usaban `pytest.raises(Exception)`. Se corrigió usando `pydantic.ValidationError`, que es la excepción real que levanta `pydantic-settings` (los `ValueError` de los validadores personalizados en `config.py` también se envuelven en `ValidationError` automáticamente).
