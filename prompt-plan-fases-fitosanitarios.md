# Prompt: generar `plandefases.md` del agente de recetas fitosanitarias

> **Documento histórico (11/09/2026).** Es el prompt con el que se generó `plandefases.md` al
> arrancar el proyecto; no describe el estado actual. La propuesta que menciona
> (`docs/propuesta-tp2-fitosanitarios.md`) nunca se agregó al repo. Lo vigente está en la skill
> (`.claude/skills/agente-fitosanitarios/SKILL.md`), `README.md` y `DECISIONES.md`.

## Cómo usarlo

1. Guardá la skill `agente-fitosanitarios` (la tarjeta que acompaña este documento).
2. Copiá la propuesta a `docs/propuesta-tp2-fitosanitarios.md` en el repo.
3. Abrí Claude Code en la raíz del repo y pegá el prompt de abajo tal cual.

---

````markdown
Vas a planificar (no implementar) la POC del TP2 de IA: un agente conversacional por WhatsApp que lee recetas agronómicas de fitosanitarios, las contrasta con el registro de SENASA y la normativa de 10 localidades, y dictamina si la aplicación es viable/legal. Tu única salida en esta tarea es el archivo `plandefases.md` en la raíz del repo. No escribas código, no instales dependencias y no crees otros archivos.

## 0. Antes de empezar

1. Cargá la skill `agente-fitosanitarios` y leela completa. Es la fuente de verdad de arquitectura, contratos, política del orquestador, formato de respuestas y convenciones. Si algo de este prompt la contradice, gana este prompt y lo anotás en "Decisiones abiertas".
2. Leé `docs/propuesta-tp2-fitosanitarios.md` (tools, RAGs, RF1–RF11 y stack).
3. Si ya hay código en el repo, relevalo y planificá sobre lo existente en vez de rehacerlo.

## 1. Decisiones cerradas (no las reabras)

- Framework base: LangChain, requisito de la cátedra. Agente con la API v1 (`langchain.agents.create_agent`, middleware, `response_format`) sobre LangGraph, con checkpointer en Postgres. No uses `AgentExecutor` ni `initialize_agent`. Verificá la API vigente en la documentación antes de fijar nombres en el plan.
- Persistencia: PostgreSQL con JSONB + pgvector (recomendación del profesor, reemplaza a Chroma) para el modelo del dominio, los vectores y el estado de conversación, según la sección 2.2. Supabase o Neon para desarrollar, Docker local para la defensa.
- Geo: geopandas + shapely + pyproj en Python, sin PostGIS. Distancias siempre en CRS métrico (`estimate_utm_crs()`), con punto y polígonos en la misma proyección.
- LLM: proveedor intercambiable por configuración (Gemini Flash multimodal como principal, Groq como alternativa), con rotación de API keys y manejo de 429. No asumas cuotas: se verifican en la consola de cada proveedor y quedan en `.env`.
- Embeddings: sentence-transformers multilingüe; elegí y justificá el modelo en el plan.
- Canal: WhatsApp Cloud API con número de prueba (sección 4). No hay GUI.
- Entrega: 30/09/2026. El núcleo (RF1–RF5, RF10, RF11) se completa antes de tocar extensiones.

## 2. Principios de diseño

### 2.1 El LLM orquesta, el núcleo experto decide

El orquestador es un LLM porque interpreta mejor cómo escribe un operario de campo ("arrancamos con el glifo en el 4, el de al lado de la escuela"). Pero el dictamen tiene que ser reproducible y citable:

- El LLM decide qué tool usar, con qué parámetros, cuándo repreguntar y cuándo declarar que no puede resolver.
- Los servicios deterministas deciden si algo cumple: matching de productos, jurisdicción, distancias, rangos de dosis, reglas por jurisdicción y combinación del dictamen.
- El LLM nunca inventa números, normas, artículos, registros ni dosis. Todo dato de la respuesta sale de un resultado de tool.
- Ausencia de evidencia no es aprobación: si un chequeo obligatorio no pudo correr, la receta no sale APTA.

### 2.2 Datos: PostgreSQL con JSON y vectores, consultado con RAG vía tools (requisito de la cátedra)

- Modelo relacional normalizado con claves foráneas, en tres schemas: `catalogo` (vademécum SENASA), `territorio` (provincias, localidades, zonas protegidas, normas, artículos y reglas) y `operacion` (recetas, ítems, dictámenes y trazas).
- JSONB para lo semiestructurado: crudo de la API, GeoJSON, dosis parseada, extracción del LLM, chequeos y citas del dictamen, trazas. Columnas `vector` en las entidades que se buscan por significado: producto, principio activo, cultivo, adversidad y artículo.
- La base no puede terminar siendo una tabla plana: ni la tabla genérica de documentos + embedding + metadata de LangChain (la propuesta menciona `langchain_postgres.PGVector`; no se usa su tabla por defecto), ni el vademécum en una tabla ancha, ni CSVs importados tal cual.
- Toda consulta de conocimiento pasa por una tool RAG con retrievers propios que ejecutan SQL parametrizado (joins + filtros sobre columnas y JSONB + distancia vectorial). El LLM elige tool y parámetros; nunca escribe SQL.
- Se suma la tool `consultar_productos` (productos registrados por cultivo, adversidad, principio activo o banda). Reutiliza los retrievers del catálogo y deja explícito el RAG sobre la base. Informa lo registrado; no recomienda qué aplicar.
- Tablas mínimas, índices y la consulta de cada tool: sección "Base de datos" de la skill.

## 3. Requisitos del orquestador (cada punto necesita tareas y criterios de aceptación propios)

### 3.1 Ruteo y extracción de parámetros
- Por cada mensaje (texto, foto, ubicación o respuesta a botón) clasifica la intención y elige tool(s): `leer_receta`, `validar_producto_registro`, `consultar_productos`, `evaluar_riesgo`, `evaluar_viabilidad_legal`, `responder_consulta_normativa`, o ninguna.
- Arma los argumentos desde el mensaje actual, la receta en curso (estado) y los turnos previos, en ese orden. Nunca completa un parámetro por suposición.
- Cada tool tiene un schema pydantic con requeridos y opcionales, documentados en `docs/matriz-parametros.md`.
- Normaliza lo informal ("glifo" → candidatos de producto, "el 4" → lote 4, "con el avión" → aplicación aérea). Si la normalización es ambigua, repregunta con opciones en vez de elegir.

### 3.2 Repreguntar cuando faltan datos
- Si faltan parámetros requeridos no llama a la tool: pide lo que falta.
- Una sola repregunta agrupada (hasta 3 datos por mensaje, priorizados), en lenguaje simple, con un ejemplo del formato esperado y la forma más fácil de darlo: pedir la ubicación del lote como mensaje de ubicación de WhatsApp, botones si hay pocas opciones, lista si hay hasta 10.
- No repregunta lo que ya sabe; lo respondido queda en el estado de la receta.
- Tras 2 intentos fallidos por el mismo dato, corta y responde como "no resuelto" explicando qué faltó.
- Antes de evaluar una receta leída de una foto, pide confirmación de los datos extraídos (Confirmar / Corregir).
- Las tools también pueden devolver `faltan_datos` (por ejemplo, el producto tiene dosis distintas por plaga y la receta no la indica); el orquestador lo trata igual.

### 3.3 Detectar lo que el sistema experto no puede resolver
Planificá tres casos, cada uno con su respuesta:
- **Fuera de dominio**, detectado por el orquestador antes de llamar tools: todo lo que no sea recetas, productos fitosanitarios registrados o normativa de las jurisdicciones cargadas. Responde breve explicando el alcance. También es requisito de política: desde el 15/01/2026 Meta no admite asistentes de IA de propósito general en la API de WhatsApp Business, solo bots con una función de negocio acotada.
- **No resuelto**, reportado por una tool con motivo tipado: lote fuera de las jurisdicciones cargadas, jurisdicción sin regla aplicable, producto no encontrado, producto sin usos/dosis registrados, dosis no comparable, normativa sin fragmento por encima del umbral, imagen ilegible, servicio caído o cuota agotada. La respuesta dice qué no se pudo determinar, por qué, qué sí se evaluó y qué puede hacer el usuario.
- **Parcial**: parte de la evaluación corrió y parte no. Dictamen NO EVALUABLE u OBSERVADA, con la lista de chequeos no realizados.
Definí el catálogo de motivos (enum) y una plantilla de mensaje por motivo.

### 3.4 Respuestas formateadas y ordenadas
- El orquestador devuelve salida estructurada (`RespuestaAgente` vía `response_format`) con el tipo de respuesta, una intro opcional de una línea y, si repregunta sin haber llamado tools, los campos faltantes.
- Un formateador determinista arma el texto con plantillas por tipo (confirmación de receta, dictamen, consulta de producto, consulta normativa, repregunta, fuera de dominio, no resuelto, error), tomando los datos de los artifacts de las tools ejecutadas en el turno y no del texto del LLM.
- Formato WhatsApp: `*negrita*`, listas con `-` o `1.`, sin tablas ni encabezados markdown, hasta 4096 caracteres por mensaje (partir por sección), coma decimal con unidad separada ("2,5 L/ha"), fechas dd/mm/aaaa y sección final "Fuentes" con norma, artículo, jurisdicción y n.º de registro SENASA.
- Tests de snapshot por plantilla.

### 3.5 Estado, evaluación y trazas
- Estado por conversación (thread = número de WhatsApp) con checkpointer en Postgres, más tabla de recetas con estado (borrador, confirmada, evaluada). Comandos "nueva receta" y "cancelar".
- Set de evaluación en `evals/` con al menos 40 conversaciones etiquetadas: ruteo (tool y args esperados), repregunta (campos faltantes esperados), fuera de dominio, no resuelto (motivo esperado) y ambigüedad. Metas: ruteo ≥ 90 %, 0 citas inventadas, 100 % de dictámenes renderizados por plantilla. Tests del flujo con LLM fake, sin red.
- Log por turno: intención, tool calls con args, estado de cada resultado, latencia y tokens. Nunca loguear tokens de API ni imágenes.

## 4. Canal: WhatsApp Cloud API con número de prueba (relevado el 11/09/2026)

Es viable para la POC. Planificá estas condiciones:
- Requiere cuenta de Meta for Developers, app con el producto WhatsApp y portfolio de negocio; no requiere verificación de negocio. El número de prueba es gratuito y solo envía a hasta 5 destinatarios verificados por código.
- El token temporal del panel vence rápido: usar token de System User con permisos `whatsapp_business_messaging` y `whatsapp_business_management`.
- Webhook: URL pública HTTPS (túnel tipo cloudflared o ngrok, también el día de la defensa), handshake GET con `hub.verify_token` y `hub.challenge`, suscripción al campo `messages`, validación de `X-Hub-Signature-256` con el App Secret en tiempo constante, respuesta 200 inmediata con procesamiento en segundo plano, deduplicación por `message.id` (Meta reintenta) y recorrido de todos los `entry[].changes[].value.messages[]`, ignorando `statuses`.
- Entrantes: `text`; `image` (media id → `GET /{media-id}` → URL válida 5 minutos → descarga con Bearer; JPEG/PNG hasta 5 MB); `location` (lat/lon, la vía natural para la ubicación del lote); `interactive` (`button_reply`, `list_reply`). Cualquier otro tipo recibe un mensaje de "tipo no soportado".
- Salientes: texto, botones (máximo 3) y listas (máximo 10 filas). El operario siempre inicia la conversación (ventana de 24 h), así que no hacen falta plantillas salvo `hello_world` para probar.
- Gotcha de Argentina: el webhook trae el número como `549XXXXXXXXXX`, pero en modo desarrollo la allowlist y el envío van sin el 9 (`54XXXXXXXXXX`); si no, error 131030. Función de normalización con tests y flag de configuración.
- Versión de Graph API configurable; verificá la vigente.
- Plan B para la defensa: el notebook de demo invoca el mismo orquestador sin pasar por WhatsApp.

## 5. Base de productos: scraping del vademécum de SENASA (relevado el 11/09/2026)

No hay API pública documentada, pero `https://aps2.senasa.gov.ar/vademecum/app/publico` es una SPA que consume una API REST (Spring Data REST, JSON HAL) sin autenticación. El scraper consume esas mismas llamadas en vez de parsear HTML. Verificá cada endpoint en DevTools antes de escribir parsers y guardá respuestas reales como fixtures:

- Listado paginado: `GET https://aps2.senasa.gov.ar/adt_api/api/productosAgroquimicosFormulados/search/publicSearchProductosFormuladosDTO?page=0&size=15&sort=numeroInscripcion,desc` → `_embedded.productosAgroquimicosFormulados[]` con `id`, `numeroInscripcion`, `marca`, `nombreFirma`, `claseToxicologica` y `sustanciasActivas` (string con `<b>` alrededor de la concentración). `page.totalElements` ≈ 7.374.
- Detalle: `GET https://aps2.senasa.gov.ar/adt_api/api/productosAgroquimicosFormulados/search/publicSearchProducto?producto=<URL codificada de .../productosAgroquimicosFormulados/{id}>&projection=productoFormuladoPublicoProjection` → `claseToxicologica` (clase, advertencia, color), `tipoPresentacion.abreviatura`, `productosAptitudes[].nomenclador.descripcion`, `principiosActivos[]` (nombre, concentración, unidad), `estadoProducto`, toxicidad para abejas/peces/aves, `aplicacionesPorProducto[]` y `productoDocumentos[]`.
- Hallazgo clave para `evaluar_riesgo`: la dosis por cultivo/plaga no está estructurada en la mayoría de los productos. En una muestra de 27: 4 tenían `aplicacionesPorProducto` (`cultivo`, `adversidad`, `dosis` en texto libre como "1,9 L/ha – 2,2 L/ha", `momentoAplicacion`, `volumenPorAplicacion`, `periodoCarencia`); 17 traían el marbete (etiqueta) como PDF en base64 en `productoDocumentos[].contenido`; 10 no tenían documentos.
- Los detalles pesan cientos de KB por los PDFs embebidos: estimá volumen y duración antes del crawl completo.
- La búsqueda avanzada filtra por principio activo, aptitud, cultivo, adversidad y clase toxicológica; relevá esos parámetros si sirven para acotar.

Estrategia a planificar:
1. Crawl del listado completo y luego del detalle con throttling (~1 req/s), User-Agent que identifique el proyecto académico, reintentos con backoff y checkpoint reanudable. Crudo en JSONB sin los base64; PDFs a disco.
2. Normalización al schema `catalogo` (sección 2.2): firma, producto, principio activo (N:M con concentración), cultivo, adversidad y uso registrado, con `dosis` y `condiciones` en JSONB, `fuente` (`senasa_estructurado` | `marbete_extraido`), `confianza` y embeddings en producto, principio activo, cultivo y adversidad.
3. Usos desde marbete: texto con pdfplumber y extracción estructurada con LLM solo para productos y cultivos del caso de estudio, cacheada, con revisión manual de una muestra.
4. Parser de dosis en texto libre (coma decimal, rangos, cm³/ha, g/ha, kg/ha, "cada 100 L", mezclas). Lo que no parsea queda como texto y la tool responde "sin dosis registrada" en vez de adivinar.
5. Matching de nombre comercial con embeddings + similitud trigram (`pg_trgm`), top-k con score; si hay empate, repregunta con opciones.
6. Snapshot versionado (dump o parquet) con su loader: demo y tests no dependen de SENASA. Fixtures de ~50 productos para tests sin red.

## 6. Insumos que provee el equipo

Las capas SIG de los municipios (límites y zonas protegidas) y los PDFs de normativa los carga el equipo a mano. El plan no incluye tareas para conseguirlos, digitalizarlos ni scrapearlos. Sí incluye su contrato de formato, validadores, loaders y datos sintéticos para desarrollar sin depender de los reales.

Estructura: una carpeta por localidad en `data/insumos/localidades/<jurisdiccion_id>/` con su GeoJSON (límite y zonas protegidas), sus ordenanzas en PDF y un `reglas.csv` (distancias mínimas por tipo de zona, tipo de aplicación y banda toxicológica, con norma y artículo). Aparte, `data/insumos/normativa-general/` con las leyes provinciales (`provincial/<provincia>/`) y nacionales (`nacional/`), cada una con su `reglas.csv` opcional. El detalle de nombres, propiedades y validaciones está en la skill.

## 7. Estructura de fases (usá exactamente esta numeración)

| Fase | Nombre | Alcance mínimo |
|---|---|---|
| 0 | Setup | estructura del repo, dependencias, `.env.example` y `config.py`, Docker Compose con Postgres (pgvector y pg_trgm), CI con lint y tests, cliente LLM con rotación de keys y fake para tests, `README`, `DECISIONES.md` y `DIFICULTADES.md` iniciales |
| 1 | Dominio y contratos | modelos pydantic (Receta, ResultadoTool, Dictamen, Cita, CampoFaltante, RespuestaAgente), modelo de datos de la sección 2.2 (`docs/modelo-datos.md` con diagrama ER y la consulta de cada tool RAG, migraciones SQL por schema con índices HNSW, GIN y trigram), catálogo de motivos de no resolución, matriz de parámetros, especificación de plantillas, contrato de insumos manuales con validadores |
| 2 | Scraper SENASA y base de productos | sección 5 completa |
| 3 | Ingesta SIG y normativa | loaders de capas y reglas, carga al schema `territorio` con chunking de normativa por artículo (tabla `articulo` ligada a `norma`) y embeddings por artículo, validación cruzada jurisdicción ↔ polígono ↔ normativa ↔ reglas |
| 4 | `leer_receta` | extracción multimodal con salida estructurada y confianza por campo, comparación con OCR clásico, set de recetas sintéticas con campos faltantes a propósito |
| 5 | Tools de validación y dictamen | retrievers SQL del catálogo y del territorio; `validar_producto_registro`; `consultar_productos`; `evaluar_riesgo` (jurisdicción por punto en polígono, distancia a zonas protegidas propias y vecinas dentro de un radio, dosis contra rango registrado con tolerancia configurable); `evaluar_viabilidad_legal` como motor de reglas determinista |
| 6 | `responder_consulta_normativa` | retriever SQL con join artículo → norma, búsqueda filtrada por la jurisdicción (y normas provinciales/nacionales si están cargadas), umbral de abstención, verificación de que cada cita esté entre los fragmentos recuperados |
| 7 | Orquestador | sección 3 completa |
| 8 | Canal WhatsApp | sección 4 completa |
| 9 | Extensiones (opcional, recortable) | RF6–RF9: `resolver_vehiculo`, `registrar_evento`, `consultar_agenda`, identificación por número; sin romper el núcleo |
| 10 | Demo, documentación y defensa | notebook E2E con kernel limpio, README, DECISIONES, DIFICULTADES y guion de demo con casos APTA, OBSERVADA, consulta de productos, repregunta, fuera de dominio y no resuelto, más una parte que muestre el modelo de datos y las consultas RAG |

Las fases 4, 5 y 6 pueden avanzar con datos stub; la 7 puede arrancar con tools stub, pero no se cierra sin las reales.

## 8. Formato obligatorio de cada fase en `plandefases.md`

1. **Objetivo** (1–2 líneas) y **RF que cubre**.
2. **Depende de** (fases e insumos) y **qué habilita**.
3. **Entregables**: archivos y módulos concretos.
4. **Tareas** numeradas, cada una de medio día como máximo.
5. **Criterios de aceptación** verificables con un comando o test concreto (por ejemplo: "`pytest tests/servicios/test_geo.py` pasa" o "un lote a 80 m de una escuela con regla de 100 m devuelve OBSERVADA con cita").
6. **Casos borde** que cubre.
7. **Riesgos y mitigación**.
8. **Estimación** en horas (rango).
9. Cierre fijo: "No avanzar a la fase siguiente sin confirmación del usuario."

Al principio del documento: diagrama de arquitectura (mermaid), diagrama de dependencias entre fases, tabla resumen (fase, horas, núcleo o extensión) y "Decisiones abiertas". Al final: riesgos transversales (cuotas del LLM, cambios en la API de SENASA o de Meta, túnel el día de la defensa) y qué recortar si no se llega al 30/09.

## 9. Reglas para escribir el plan

- No inventes endpoints, parámetros ni nombres de clases de librerías: lo que no verificaste va marcado "(verificar)".
- Todo test corre sin red: fixtures para SENASA, WhatsApp y respuestas del LLM.
- Criterio transversal de aceptación: no existe ninguna tabla genérica de documentos + embeddings, y cada retriever tiene test de integración contra Postgres real (Docker) con datos sintéticos.
- Secretos solo en `.env` (no versionado); nunca loguear tokens.
- Nombres de dominio en español (`receta`, `evaluar_riesgo`), consistentes con la skill.
- Al terminar, respondé en el chat con el total de horas, las 3 fases más riesgosas y las decisiones abiertas. No empieces a implementar.
````

---

## Notas del relevamiento (11/09/2026)

**WhatsApp:** el número de prueba del Cloud API sigue disponible, es gratis y admite hasta 5 destinatarios ([Meta — Get Started](https://developers.facebook.com/docs/whatsapp/cloud-api/get-started/)). Token permanente vía System User ([Meta — Get Started](https://developers.facebook.com/documentation/business-messaging/whatsapp/get-started)). La URL de un media descargado vence a los 5 minutos ([Meta — Media](https://developers.facebook.com/documentation/business-messaging/whatsapp/business-phone-numbers/media)). El problema del 9 en números argentinos está documentado en [chatwoot#13932](https://github.com/chatwoot/chatwoot/issues/13932). La política del 15/01/2026 prohíbe asistentes de propósito general y permite bots de negocio acotados ([TechCrunch](https://techcrunch.com/2025/10/18/whatssapp-changes-its-terms-to-bar-general-purpose-chatbots-from-its-platform/), [respond.io](https://respond.io/blog/whatsapp-general-purpose-chatbots-ban)).

**SENASA:** endpoints y muestra de 27 productos relevados en vivo desde la [consulta pública del vademécum](https://aps2.senasa.gov.ar/vademecum/app/publico). SENASA no publica un dataset abierto equivalente: la [página del Registro Nacional de Terapéutica Vegetal](https://www.argentina.gob.ar/senasa/programas-sanitarios/productosveterinarios-fitosanitarios-y-fertilizantes/registro-nacional-de-terapeutica-vegetal) remite al mismo vademécum.

**LangChain:** `create_agent` reemplaza a `create_react_agent` y `AgentExecutor` ([LangChain v1](https://docs.langchain.com/oss/python/releases/langchain-v1)). La tabla por defecto de los vector stores de Postgres es genérica (id, contenido, embedding y metadata JSON), o sea plana; `PGVectorStore` permite mapear una tabla propia con columnas personalizadas ([PGVectorStore](https://docs.langchain.com/oss/python/integrations/vectorstores/pgvectorstore)).

## Carga de capas SIG y normativa (por fuera del plan)

- **Formato:** el que define la sección "Contrato de insumos manuales" de la skill; queda congelado al cerrar la Fase 1.
- **Cuándo subirlas:** al arrancar la Fase 3. Se pueden preparar en paralelo durante la Fase 2, que no depende de ellas.
- **Mínimo para arrancar:** 2 localidades completas (GeoJSON, ordenanzas y `reglas.csv`) y las leyes provinciales para validar el pipeline. Las 10 localidades tienen que estar cargadas antes de cerrar la Fase 5.

```
data/insumos/
├── localidades/
│   └── san-carlos-centro/            una carpeta por localidad (minúsculas, sin tildes, con guiones)
│       ├── localidad.geojson         límite + zonas protegidas, EPSG:4326
│       ├── ordenanza-914-2018.pdf    <tipo>-<numero>-<anio>.pdf
│       └── reglas.csv
└── normativa-general/
    ├── provincial/
    │   └── santa-fe/
    │       ├── ley-NNNNN-AAAA.pdf
    │       └── reglas.csv            opcional
    └── nacional/
        ├── ley-NNNNN-AAAA.pdf
        └── reglas.csv                opcional
```

- **`localidad.geojson`:** cada feature lleva la propiedad `tipo`. Tiene que haber exactamente un `limite` (polígono, con `nombre` y `provincia`); el resto son zonas protegidas (`escuela`, `curso_agua`, `zona_urbana`, `otro`, con `nombre`) y pueden ir como punto, línea o polígono.
- **`reglas.csv`:** `tipo_zona, tipo_aplicacion, bandas, distancia_min_m, norma, articulo, observaciones`. Una fila = "a menos de X m de una zona de este tipo no se puede aplicar (terrestre/aérea/todas) productos de estas bandas", y `norma` es el nombre del PDF de esa carpeta sin extensión. Hace falta porque el chequeo de distancia es determinista y no se resuelve con RAG.