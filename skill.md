---
name: agente-fitosanitarios
description: Arquitectura, contratos y reglas del agente experto que valida recetas agronómicas de fitosanitarios por WhatsApp (TP2 IA UTN FRRo con LangChain, PostgreSQL con JSONB y pgvector, vademécum SENASA, capas SIG y normativa municipal). Usala siempre que planifiques, implementes, testees, revises o documentes este proyecto o su plandefases.md, aunque no se nombre la skill.
---

# Agente de recetas fitosanitarios

POC de un sistema experto conversacional: el operario manda por WhatsApp la foto de una receta agronómica o una consulta. Un LLM orquestador interpreta el mensaje, elige la tool y sus parámetros, repregunta lo que falta o avisa que no puede resolverlo. Un núcleo determinista contrasta la receta con el registro de SENASA, las capas SIG y la normativa de las localidades cargadas (hoy El Trébol, Sastre y San Jorge, en Santa Fe, más la ley provincial), y emite un dictamen citable.

Requisitos de la cátedra: LangChain como base y demostrar agentes, RAG, embeddings y NLP/LLM.

## Cómo trabajar en este repo

- Leé `plandefases.md` e identificá la fase en curso. Trabajá solo en esa fase. Si todavía no existe, la tarea es generarlo, no implementar.
- Antes de usar una API externa o una clase de librería, verificala en la documentación vigente. Lo que no verificaste va marcado "(verificar)", nunca inventado.
- Al cerrar la fase: corré los criterios de aceptación, actualizá `DECISIONES.md` (qué se decidió y por qué) y `DIFICULTADES.md` (qué falló y cómo se resolvió), y frená hasta que el usuario confirme.
- Los tests nunca salen a la red: fixtures para SENASA, WhatsApp y el LLM.

## Principio central: el LLM orquesta, el núcleo decide

- LLM: entiende el mensaje, elige tool, arma argumentos, repregunta, detecta fuera de dominio y redacta como mucho una línea de intro.
- Servicios deterministas: matching de productos, jurisdicción, distancias, dosis, reglas y dictamen.
- El LLM nunca inventa números, normas, artículos, n.º de registro ni dosis. Si un dato no viene de un resultado de tool, no va en la respuesta.
- Ausencia de evidencia no es aprobación: un chequeo obligatorio que no corrió impide un dictamen APTA.
- Motivo: un dictamen legal tiene que ser reproducible y auditable, y un LLM con cuota gratuita puede fallar o alucinar. Esta separación además da tests confiables.

## Glosario del dominio

- **Receta agronómica**: documento firmado por un ingeniero agrónomo que prescribe una aplicación: cultivo, lote, adversidad, productos, dosis, superficie y tipo de aplicación.
- **Formulado / marca**: producto comercial registrado en SENASA con n.º de inscripción (puede traer sufijo, p. ej. "42768 BIO").
- **Principio activo**: sustancia activa con concentración (%, g/L).
- **Aptitud**: herbicida, insecticida, fungicida, acaricida, coadyuvante, etc.
- **Adversidad**: plaga, maleza o enfermedad objetivo.
- **Banda/clase toxicológica**: Ia y Ib roja, II amarilla, III azul, IV verde. SENASA la devuelve como "III / LIGERAMENTE PELIGROSO / AZUL" y con errores de tipeo ("AMAREILLO"), así que hay que normalizarla.
- **Marbete**: etiqueta aprobada del producto, con usos, dosis y restricciones. En SENASA suele venir solo como PDF.
- **Tipo de aplicación**: terrestre o aérea; la normativa suele fijar distancias distintas para cada una.
- **Zona protegida**: escuela, curso de agua, zona urbana u otra definida por la norma.
- **Jurisdicción**: localidad del caso de estudio (identificada por `jurisdiccion_id`), con su polígono, sus zonas protegidas, su normativa y sus reglas.

## Arquitectura

```
canales/whatsapp  →  orquestador  →  tools  →  servicios  →  datos
(webhook, envío)     (create_agent,   (fachadas   (localidad,    (Postgres + pgvector:
                      estado,          finas)      dosis, reglas, productos, usos, chunks,
                      formateador)                 matching, RAG) geometrías, reglas, estado)
```

- Los adaptadores (`canales/`, `senasa/`) son los únicos que conocen formatos crudos. Nada del payload de Meta ni del JSON HAL de SENASA pasa de ahí.
- Las tools validan la entrada, llaman servicios y devuelven `ResultadoTool`. No tienen lógica de negocio.
- Los servicios son funciones puras o casi puras, testeables sin LLM.
- `evaluar_viabilidad_legal` ejecuta internamente los chequeos de producto y riesgo (en paralelo) sobre la receta confirmada. `validar_producto_registro` y `evaluar_riesgo` quedan expuestas para consultas sueltas. Así el pipeline del dictamen no depende de que el LLM encadene bien las tools, y se ahorran llamadas.

Estructura sugerida:

```
src/fitosanitarios/
  config.py
  llm/            cliente con rotación de keys y modelo fake para tests
  dominio/        modelos pydantic, enums, catálogo de motivos
  datos/          migraciones SQL por schema, repositorios y retrievers
  senasa/         cliente de la API, crawler, normalizador, parser de dosis
  insumos/        loaders y validadores de SIG, normativa y reglas
  servicios/      localidad, dosis, matching, reglas, dictamen, recursos, ubicacion, formato (lo que usa más de una tool)
  tools/          una carpeta por tool: tool.py (schema + lógica + la tool de LangChain),
                  prompts.py (DESCRIPCION, lo que lee el LLM), mensajes.py (lo que lee el
                  operario: preguntas, avisos, plantilla de respuesta), utils.py si hace falta
  orquestador/    agente (create_agent, TOOLS, ToolCallLimitMiddleware), prompt de sistema,
                  estado, formateador, plantillas, respuesta_directa (tipo por tool, sin 2ª llamada)
  canales/whatsapp/  webhook FastAPI, cliente Graph, normalización de números
evals/  tests/  notebooks/  data/ (crudos fuera de git, salvo muestras y fixtures)
```

## Base de datos: relacional + JSONB + vectores

Requisito de la cátedra: PostgreSQL con JSON y vectores, consultado con RAG a través de tools, sin terminar en una tabla plana.

- Un solo motor: PostgreSQL con JSONB y pgvector. Entidades relacionales con claves foráneas, JSONB para lo semiestructurado y columnas `vector` en las tablas de entidad que se buscan por significado.
- Nada de tablas planas: ni una tabla genérica "documento + embedding + metadata" (la `langchain_pg_embedding` del PGVector legacy o la tabla por defecto de `PGVectorStore`), ni el vademécum volcado en una tabla ancha, ni CSVs importados tal cual.
- Toda consulta de conocimiento pasa por una tool RAG: el LLM elige la tool y sus parámetros tipados; la tool ejecuta SQL parametrizado que combina joins, filtros sobre columnas y JSONB y distancia vectorial; lo recuperado es el contexto con el que se valida o se genera. El LLM nunca escribe SQL.
- Criterio por columna: relacional si se filtra, se joinea o se valida (banda, estado, tipo de zona, distancia, FKs); JSONB si es semiestructurado o variable (crudo de API, GeoJSON, dosis parseada, extracción del LLM, trazas); vector solo donde hay búsqueda por similitud.
- Retrievers propios (`BaseRetriever`) con SQL parametrizado. `PGVectorStore` solo si se mapea sobre una tabla de entidad con columnas propias (`id_column`, `content_column`, `embedding_column`, `metadata_columns`; verificar).

### Tablas mínimas por schema

| Tabla | Relaciones | JSONB | vector |
|---|---|---|---|
| `catalogo.firma` | 1:N producto | datos | — |
| `catalogo.producto` | N:1 firma · N:M principio_activo · 1:N uso_registrado, documento | toxicidad, crudo_api (detalle sin base64) | marca + activos + concentración |
| `catalogo.principio_activo` | N:M producto vía `producto_principio_activo` (concentración, unidad) | — | nombre |
| `catalogo.cultivo` | 1:N uso_registrado | sinonimos | nombre + sinónimos |
| `catalogo.adversidad` | 1:N uso_registrado | sinonimos | nombre común + científico ("yuyo colorado" → Amaranthus) |
| `catalogo.uso_registrado` | N:1 producto, cultivo, adversidad, documento | dosis (texto, min, max, unidad, base), condiciones (momento, volumen, carencia) | — |
| `catalogo.documento` | N:1 producto | extraccion (salida del LLM + confianza; en los marbetes, páginas y si tiene texto) | — |
| `catalogo.fragmento_marbete` | N:1 documento, producto | — | fragmento de una página del marbete (RAG de marbetes) |
| `territorio.provincia` | 1:N localidad, norma | — | — |
| `territorio.localidad` | N:1 provincia · 1:N zona_protegida, norma | limite (GeoJSON) | — |
| `territorio.zona_protegida` | N:1 localidad | geometria (GeoJSON), propiedades | — (se carga del GeoJSON; desde que la localidad se resuelve por nombre, ninguna tool la consulta) |
| `territorio.norma` | N:1 localidad, provincia o nacional · 1:N articulo, regla_distancia | metadatos | — |
| `territorio.articulo` | N:1 norma | metadatos (capítulo, página, OCR) | texto del artículo |
| `territorio.fragmento_norma` | N:1 norma, articulo (NULL en fallos y normas sin PDF) | — | fragmento de 800 caracteres (RAG de normativa) |
| `territorio.regla_distancia` | N:1 norma, articulo | — (bandas TEXT[]) | — |
| `operacion.receta` | N:1 localidad · 1:N receta_item, dictamen | datos_extraidos (campos + confianza), ubicacion | — |
| `operacion.receta_item` | N:1 receta, producto (null hasta resolverlo) | dosis_declarada | — |
| `operacion.dictamen` | N:1 receta | chequeos, citas | — |
| `operacion.turno` | por thread de conversación | entrada, tool_calls, salida | — |

Más las tablas propias del checkpointer de LangGraph.

- Índices: HNSW (`vector_cosine_ops`) en cada embedding, GIN en los JSONB que se consultan, `pg_trgm` en nombres (marca, principio activo, cultivo, adversidad) y full-text en español sobre `articulo`.
- Sin PostGIS: `localidad` y `zona_protegida` guardan el GeoJSON y su bounding box en columnas numéricas. Hoy ninguna consulta es geográfica: la localidad se resuelve por nombre (ver "Geo").
- `docs/modelo-datos.md` documenta el diagrama ER (mermaid) y la consulta SQL de cada tool RAG. Es material para la defensa.

### Tools RAG sobre la base

| Tool | Qué recupera | Qué se hace con lo recuperado |
|---|---|---|
| `validar_producto_registro` | candidatos por embedding de producto + trigram; joins a activos y usos; cultivo y adversidad resueltos por embedding | validación en código: registro y banda (sin cultivo), autorización y dosis registrada para un cultivo |
| `evaluar_riesgo` | localidad por nombre, reglas de localidad + provincia + nación con norma y artículo, banda de cada producto, dosis del uso registrado | banda de la aplicación (la más peligrosa), distancia mínima por tipo de zona y rango de dosis en código. Una dosis fuera de rango va primero, como observación, y no se ofrece agendar |
| `responder_consulta_normativa` | fragmentos de las normas (incluidos fallos y normas sin PDF) y reglas de `reglas.csv` por embedding, filtrados por localidad, provincia y nacional; la pregunta se reformula antes de buscar | el LLM responde solo con esos fragmentos; citas verificadas en código. Sin respaldo: "No cuento con esa información" |
| `consultar_marbete` | el producto por trigram + embedding; los fragmentos de SU marbete por búsqueda híbrida (similitud + BM25) con la pregunta reformulada | el LLM responde solo con esos fragmentos; cada página citada se verifica en código. Sin respaldo: "No cuento con esa información" |
| `consultar_productos` | productos registrados por cualquier combinación de cultivo, adversidad, principio activo (resueltos por embedding), aptitud (JSONB del registro), banda, firma y marca; una localidad + distancia a la zona urbana se traduce en las bandas permitidas ahí (`servicios/limitaciones.py`) | una lista por tipo de aplicación (una sola si coinciden), una fila por producto con registro, banda y dosis. Filtro que no está en el registro: se omite y se avisa. Informa lo registrado; no recomienda qué aplicar (eso lo prescribe el agrónomo) |

### Otras tools de normativa (deterministas, sin RAG)

Agregadas después de la Fase 6 para lo que no necesita ni conviene resolver por similitud: un número de artículo exacto, o la lista completa de límites de una localidad (que tiene que ser completa, no "lo más parecido").

| Tool | De dónde sale | Nota |
|---|---|---|
| `consultar_articulo` | `territorio.articulo` por número exacto (+ norma, si la nombró) | texto literal del PDF, sin que el LLM lo reescriba; distinto de `responder_consulta_normativa` (embedding + redacción). Sin localidad ni norma nombrada busca en la provincial y nacional y lo avisa |
| `listar_limitaciones` | `territorio.regla_distancia` de la localidad (municipal + provincial + nacional), filtrada por tipo de zona/aplicación/banda si los dio | lista completa con norma y artículo citando cada fila, con la *Distancia mínima que rige* arriba (la más restrictiva, como el dictamen); con `distancia_m`, qué tipos y bandas se pueden a esa distancia y cuáles solo con excepción (`permitido=S`). Con `producto`, la banda del registro manda sobre la dicha. Comparaciones (avión contra tierra, dos bandas) en una sola llamada. Drone y mochila, con aviso de que las normas no los nombran. Nunca bloquea el dictamen (eso lo hace `evaluar_riesgo`/`evaluar_viabilidad_legal` con las `permitido=N`) |

### Tools de la receta y de la operación

| Tool | Qué hace |
|---|---|
| `leer_receta` | extrae la receta de la foto (LLM multimodal). Ligada a la foto del turno, sin argumentos para el LLM; con foto, es siempre la primera llamada (middleware `LeerLaFotoPrimero`) |
| `completar_receta` | aplica lo que dice el operario (datos faltantes o correcciones) sobre la última receta leída, tomada del artifact y no de lo que recuerde el LLM, y la vuelve a mostrar |
| `resolver_vehiculo` | identifica el equipo ("la mosquito") contra `catalogo.vehiculo` |
| `registrar_evento` | inicio y fin de una aplicación real; `thread_id` sale del `config`, no del LLM |
| `consultar_agenda` | tareas de uno o varios días ("hoy", "jueves y viernes", "semanal"), resueltos en código |
| `agendar_aplicacion` | agenda la receta evaluada: pregunta fecha y hora, avisa choques (uno por cultivo y lote) y suma el pronóstico del tiempo de la franja (Open-Meteo) |

`docs/matriz-parametros.md` tiene los argumentos de cada una tal como están en el código.

## Contratos

```python
class Cita(BaseModel):
    fuente: Literal["normativa", "senasa"]
    jurisdiccion_id: str | None
    norma: str | None          # "Ordenanza 914/2018"
    articulo: str | None       # "8"
    registro_senasa: str | None
    documento: str | None      # "marbete", "detalle API", nombre del PDF

class CampoFaltante(BaseModel):
    campo: str                 # "ubicacion_lote"
    motivo: str
    pregunta_sugerida: str
    tipo_entrada: Literal["texto", "ubicacion", "botones", "lista", "imagen"]
    opciones: list[str] | None = None

class ResultadoTool(BaseModel):
    estado: Literal["ok", "observado", "faltan_datos", "no_resuelto", "error"]
    datos: dict | None = None          # payload tipado por tool (modelo propio serializado)
    faltantes: list[CampoFaltante] = []
    motivo: MotivoNoResuelto | None = None
    citas: list[Cita] = []
    advertencias: list[str] = []
    chequeos_no_realizados: list[str] = []

class RespuestaAgente(BaseModel):      # response_format del agente
    tipo: Literal[
        "confirmacion_receta", "dictamen", "consulta_producto", "consulta_normativa",
        "repregunta", "fuera_de_dominio", "no_resuelto", "ayuda", "error",
        # Fase 9 (extensiones RF6/RF7/RF9):
        "consulta_vehiculo", "evento_registrado", "agenda",
        "detalle_bandas", "agendar_aplicacion",  # seguimiento del dictamen
        "consulta_articulo", "limitaciones",     # consultas de normativa sin LLM en el texto
        "consulta_marbete",                      # RAG de marbetes
    ]
    faltantes: list[CampoFaltante] = []  # solo si repregunta sin haber llamado tools
```

- Estado `ok`: todo cumple. `observado`: corrió y algo no cumple. `faltan_datos`: el usuario puede aportar lo que falta. `no_resuelto`: el sistema no tiene cómo resolverlo. `error`: falla técnica.
- Los casos esperables (producto no encontrado, lote fuera de cobertura) se devuelven como estado, nunca como excepción. Las excepciones quedan para bugs.
- Las tools devuelven contenido y artifact (`response_format="content_and_artifact"`): un resumen corto para el LLM y el `ResultadoTool` completo como artifact. El formateador toma `RespuestaAgente.tipo` y renderiza los artifacts de las tools ejecutadas en el turno actual, así el LLM no puede alterar números ni citas.
- Toda afirmación sobre normativa o registro lleva su `Cita`.
- **`intro` (una línea que el LLM redactaba) se sacó** ("Menos tokens por turno", ver DECISIONES.md): el formateador ya la ignoraba en casi todos los tipos y sacarla evitó una segunda llamada a Gemini solo para escribirla.
- **`return_direct=True` en 12 de las 14 tools** (todas menos `evaluar_riesgo` y `resolver_vehiculo`): el turno termina apenas corre la tool, sin una segunda llamada al modelo para elegir `tipo`. Ese `tipo` sale de `orquestador/respuesta_directa.py::TIPO_POR_TOOL` (una tabla tool → tipo) según el nombre de la tool y su `estado` (`no_resuelto`/`faltan_datos` pisan el tipo por defecto). `evaluar_riesgo` sigue pasando por el modelo porque su resultado puede ser un dictamen completo o solo el detalle de bandas, según de qué se venía hablando; `resolver_vehiculo` porque alimenta a otra tool, no termina el turno.

### Catálogo `MotivoNoResuelto`

| Motivo | Cuándo |
|---|---|
| `JURISDICCION_NO_CUBIERTA` | la localidad no está entre las cargadas ni es un municipio conocido de una provincia con normativa |
| `SIN_REGLA_APLICABLE` | la jurisdicción no tiene regla para ese tipo de zona o aplicación |
| `PRODUCTO_NO_ENCONTRADO` | ningún candidato supera el umbral de matching |
| `SIN_USOS_REGISTRADOS` | el producto no tiene cultivos/dosis estructurados ni extraídos del marbete. En `validar_producto_registro` no se muestra como no resuelto: registro, banda, dosis no verificada y, si hay marbete con texto, lo que dice |
| `NORMATIVA_SIN_RESPALDO` | ningún fragmento supera el umbral de similitud |
| `IMAGEN_ILEGIBLE` | la extracción no alcanza la confianza mínima en campos clave |
| `LIMITE_REPREGUNTAS` | 2 intentos fallidos por el mismo dato |
| `VEHICULO_NO_ENCONTRADO` | Fase 9: `resolver_vehiculo` no reconoce la descripción |
| `SIN_EVENTO_EN_CURSO` | Fase 9: `registrar_evento("finalizar")` sin un `iniciar` previo |
| `ARTICULO_NO_ENCONTRADO` | `consultar_articulo`: el número no está en la norma (o en ninguna, o en varias sin desambiguar) |
| `MARBETE_SIN_RESPALDO` | `consultar_marbete`: el producto no tiene marbete con texto, ningún fragmento pasa el umbral o el LLM no cita ninguna página verificable |

Fuera de dominio no es un motivo de tool: lo decide el orquestador antes de llamar tools.

### Matriz de parámetros

| Tool | Requeridos | Opcionales | Si falta |
|---|---|---|---|
| `leer_receta` | imagen de la receta | — | pedir la foto, nítida y completa |
| `completar_receta` | al menos un dato de la receta (cultivo, localidad, tipo de aplicación, lote, superficie, dosis) | — | sin receta leída en la conversación: pide la foto |
| `validar_producto_registro` | producto | cultivo (sin él: registro y banda), adversidad, dosis + unidad | producto ambiguo: lista de candidatos |
| `evaluar_riesgo` | localidad o municipio (texto), tipo de aplicación, productos, cultivo, dosis + unidad | provincia, adversidad (pasa a requerida si las dosis registradas varían por adversidad) | localidad: lista de las cargadas |
| `evaluar_viabilidad_legal` | receta confirmada: localidad, tipo de aplicación, productos con dosis, cultivo | provincia, adversidad, superficie | localidad: lista de las cargadas. Receta incompleta o con "NO FIGURA": no evalúa |
| `agendar_aplicacion` | fecha, hora (texto del operario, resuelto en código) | localidad (para el pronóstico), datos de la receta | fecha: pregunta el día. Hora: muestra la agenda de ese día y pregunta el horario |
| `responder_consulta_normativa` | pregunta, jurisdicción (explícita o de la receta en curso) | provincia, tipo de aplicación, tipo de zona | jurisdicción: lista de las localidades cargadas |
| `consultar_productos` | al menos un filtro: cultivo, adversidad, principio activo, aptitud, banda, firma, marca, o localidad + distancia | cualquier combinación; tipo de aplicación (sin él, aérea y terrestre), provincia | distancia sin localidad: lista de las cargadas |
| `consultar_marbete` | producto, pregunta | — | producto ambiguo: lista de candidatos |
| `consultar_articulo` | número de artículo | norma, localidad, provincia | número: pedirlo. Número en varias normas: lista para elegir |
| `listar_limitaciones` | localidad (o de la receta en curso) | provincia, tipo de aplicación, banda, tipo de zona, distancia_m, producto | localidad: lista de las cargadas. Producto con variantes de distinta banda: lista para elegir |
| `resolver_vehiculo` | descripción del vehículo | — | no se repregunta: si no lo reconoce, `VEHICULO_NO_ENCONTRADO` y lo resuelve quien la llama |
| `registrar_evento` | acción (iniciar/finalizar) | vehículo y lote (solo iniciar), id de receta | no se repregunta: `faltan_datos` si iniciar sin vehículo/lote |
| `consultar_agenda` | — | día o días como los dijo (default: hoy) | no aplica |

Fuentes para completar un parámetro, en orden: mensaje actual, receta en curso, turnos previos. Nunca por suposición.

**Tope de llamadas.** `ToolCallLimitMiddleware(run_limit=4)`: pasadas 4 llamadas a tools en el mismo turno, las siguientes reciben un aviso y no se ejecutan (evita bucles que agotan la cuota gratuita del LLM).

**Foto primero.** En un turno con foto, el middleware `LeerLaFotoPrimero` deja en la primera llamada al modelo solo `leer_receta`, con `tool_choice` por nombre: leerla no depende de que el modelo lo decida (a veces contestaba "mandame la foto" con la foto adjunta).

## Política del orquestador

Por cada mensaje:

1. ¿Es del dominio? Recetas, productos fitosanitarios registrados o normativa de aplicación de las localidades cargadas. Si no, responder `fuera_de_dominio`. Además es requisito de Meta: desde el 15/01/2026 la API de WhatsApp Business no admite asistentes de propósito general.
2. Intención: receta nueva (foto), confirmación o corrección de receta, evaluar receta, consulta de producto (`validar_producto_registro` si pregunta por uno puntual, `consultar_productos` si pide un listado), consulta normativa, comando ("nueva receta", "cancelar"), ayuda o saludo.
3. ¿Están los requeridos? Si faltan, responder repregunta sin llamar a la tool.
4. Llamar la tool con argumentos validados por schema.
5. Leer el estado del resultado: `ok`/`observado` → responder. `faltan_datos` → repregunta. `no_resuelto` → informar. `error` → mensaje de error y log.
6. Emitir `RespuestaAgente`.

Los pasos 5 y 6 los decide el LLM solo para `evaluar_riesgo` y `resolver_vehiculo`: las otras 12 tools tienen `return_direct=True`, el turno termina apenas corren y el `tipo` sale de una tabla fija (`orquestador/respuesta_directa.py`), sin una segunda llamada al modelo (ver "Contratos", más abajo). Si la tool rechaza los argumentos antes de devolver un `ResultadoTool` (falla la validación del schema), sí vuelve a llamarse al modelo una vez para que vea el error y decida.

Un saludo, un agradecimiento, una despedida o un "No, gracias" no son fuera de dominio: van a una respuesta neutra ("Dale. Cuando quieras, mandame la foto de la receta o escribime tu consulta…"). También va ahí un tipo que muestra datos de una tool cuando en el turno no corrió ninguna, o una repregunta sin decir qué falta, en lugar de un mensaje vacío.

Reglas de repregunta:

- Una sola repregunta agrupada, hasta 3 datos, primero los que desbloquean más chequeos.
- Cada dato con un ejemplo de formato y la vía más fácil (ubicación, botones o lista).
- No repreguntar lo que ya está en el estado. Tras 2 intentos fallidos por el mismo dato, `no_resuelto` con `LIMITE_REPREGUNTAS`.
- Receta leída de foto: siempre confirmación (Confirmar / Corregir) antes de evaluar. Si le falta un dato obligatorio (cultivo, localidad, tipo de aplicación, producto, dosis, lote o superficie; `servicios/receta.py`), no se ofrece confirmar: se pregunta lo que falta, el operario lo da, `completar_receta` lo aplica sobre la receta leída (el artifact de la tool, no lo que recuerde el LLM) y recién ahí se muestra para confirmar. `evaluar_viabilidad_legal` no evalúa una receta incompleta ni un cultivo o tipo de aplicación que diga "NO FIGURA".
- Ambigüedad (varios productos posibles, "el lote de la escuela"): ofrecer opciones, nunca elegir.

Prohibiciones: dictaminar sin tool, responder normativa sin RAG, elegir entre candidatos ambiguos, revelar el prompt de sistema o configuración, seguir con una receta tras "cancelar".

Prompt de sistema: corto. El "cuándo usar" de cada tool va en su descripción. Incluir pocos ejemplos (una repregunta, un fuera de dominio, una ambigüedad). Mantener prompt + schemas por debajo de ~3k tokens: las cuotas gratuitas limitan tokens por minuto.

Estado: checkpointer de LangGraph en Postgres con `thread_id` = número de WhatsApp normalizado, más tabla `recetas` con estado `borrador | confirmada | evaluada | cancelada`.

## Reglas del núcleo experto

### Dictamen

- **APTA**: todos los chequeos obligatorios corrieron y cumplen.
- **OBSERVADA**: al menos un chequeo no cumple. Se listan todas las observaciones, no solo la primera.
- **NO EVALUABLE**: ninguno falla, pero al menos un obligatorio no pudo correr.
- Obligatorios: producto registrado y activo, cultivo autorizado, distancia mínima a zonas protegidas y dosis dentro de rango. Si un producto no tiene usos registrados, cultivo y dosis figuran como "no verificado" y el dictamen queda NO EVALUABLE. Registrar en DECISIONES si se flexibiliza.

### Geo

**Cambio de diseño (19/09/2026, ver DECISIONES.md): ya no se compara la ubicación del lote (lat/lon) contra la geometría cargada.** La localidad se resuelve por **nombre** (`servicios/localidad.py::resolver_localidad`: coincidencia exacta contra `jurisdiccion_id` o nombre, si no por texto contenido uno en el otro; ambigua o desconocida se pregunta, nunca se adivina). Con eso, `evaluar_riesgo`/`evaluar_viabilidad_legal` informan la **banda de la aplicación** (la más peligrosa entre los productos) y la **distancia mínima que exige la norma** para cada tipo de zona -- no una distancia real medida desde el lote. El código de punto en polígono y distancias (`servicios/geo.py` y sus retrievers) se borró el 29/09/2026.

- Reglas candidatas (`datos/retrievers/territorio.py::reglas_candidatas`): las de la localidad, las provinciales de su provincia y las nacionales. Aplica la que coincide en `tipo_zona`, `tipo_aplicacion` (o `todas`) y banda del producto (o `todas`). Con varias, gana la más restrictiva (mayor `distancia_min_m`), citando todas.
- `regla_distancia.permitido`: `N` (prohibición) es la única que usan el dictamen y el agendado -- dentro de esa distancia no se puede. `S` (condicional) nunca bloquea ni ablanda una `N`; solo sirve para consultas ("¿puedo aplicar a X m bajo alguna condición?", `listar_limitaciones` con `distancia_m`).
- Una localidad sin `localidad.geojson` (22/09/2026, ver DECISIONES.md, "Localidades y normas sin fuente oficial") igual puede tener reglas de distancia cargadas: sin geometría no hay zonas protegidas propias ni límite, pero `reglas.csv` no depende de eso.

### Dosis

- Normalizar unidades a una base común por hectárea (L/ha, kg/ha). Convertir cm³ y g. "Cada 100 L de agua" requiere volumen de caldo; si no está, `faltan_datos`.
- Comparar contra el rango registrado para cultivo (+ adversidad). Fuera del rango por más de `DOSIS_TOLERANCIA_PCT` → observación, indicando si está por encima o por debajo y cuánto (`servicios/dictamen.py::observacion_de_dosis`, la usan el dictamen y `evaluar_riesgo`).
- Rangos distintos por adversidad y adversidad desconocida: `faltan_datos`.
- Usos con `fuente = marbete_extraido`: mencionar la fuente en la cita.

### RAG de normativa

- Índice (23/09/2026, ver DECISIONES.md, "RAG de limitaciones"): `territorio.fragmento_norma`, cada norma partida con el `RecursiveCharacterTextSplitter` de la cursada (800/120, `servicios/fragmentos.py`), incluidos los fallos y normas sin PDF; y cada regla de `reglas.csv` con `texto` + `embedding`. `contexto_normativo_por_similitud` busca los dos juntos. La tabla de qué se puede a una distancia (`listar_limitaciones`) sigue siendo determinista.
- Chunk para `consultar_articulo` = un artículo, con metadata `ambito` (municipal/provincial/nacional, según la carpeta), `jurisdiccion_id` (localidad, provincia o nacional), `norma`, `articulo`, `pagina` y `archivo`.
- PDF sin capa de texto: OCR (Tesseract) antes de chunkear, marcado para revisión manual.
- Filtro previo en la misma consulta SQL, con join `articulo → norma`: normas de la localidad del lote, provinciales de su provincia y nacionales. Después, similitud con pgvector.
- Por debajo de `RAG_UMBRAL_SIMILITUD`: `NORMATIVA_SIN_RESPALDO`.
- El LLM responde solo con los fragmentos recuperados. Cada artículo citado se verifica en código contra la metadata de esos fragmentos; si no está, se descarta la cita y se marca advertencia.
- Formato: veredicto corto (Sí / No / Depende), la regla en una oración y la cita.

### Matching de productos

- Candidatos por trigram (`pg_trgm`) y embeddings sobre marca + principio activo + concentración. Score combinado y top-5.
- Un candidato claro: usarlo. Varios cercanos: repregunta con lista. Ninguno sobre el umbral: `PRODUCTO_NO_ENCONTRADO`.

## Formato de respuestas (WhatsApp)

- `*negrita*` para títulos de sección, listas con `-` o `1.`, sin tablas, sin encabezados `#`, sin links largos.
- Hasta 4096 caracteres por mensaje; si se pasa, partir por sección, nunca a mitad de una lista.
- Coma decimal y unidad separada ("2,5 L/ha", "80 m"), fechas dd/mm/aaaa. Los n.º de registro van tal cual.
- Íconos solo para estado: ✅ cumple, ❌ no cumple, ⚠️ no verificado o advertencia.
- Botones con título corto (≤ 20 caracteres), listas de hasta 10 filas.
- Sección Fuentes al final siempre que haya citas.

### Plantillas de referencia (datos ficticios)

Forma de cada plantilla. Las salidas reales actuales, una por cada `tipo`, están en `docs/especificacion-plantillas.md`.

**Confirmación de receta**
```
*Leí la receta N° 0042*. Confirmá los datos:
- *Cultivo:* soja
- *Lote:* 4
- *Adversidad:* malezas de hoja ancha
- *Producto:* Glifosato 48 % — 2 L/ha
- *Superficie:* 35 ha
- *Tipo de aplicación:* no figura ⚠️
[Confirmar] [Corregir]
```

**Dictamen**
```
*Dictamen* — San Carlos Centro
*Resultado:* ❌ OBSERVADA

*Observaciones*
1. Dosis de Glifosato Full 48 SL: 5 L/ha, por encima del rango registrado para soja (2–3 L/ha).

*Condiciones de aplicación* — San Carlos Centro · terrestre · banda IV (verde)
- *Distancia mínima a escuelas:* 100 m (Ordenanza 914/2018, art. 8)

*Fuentes*
- Ordenanza 914/2018, art. 8 (San Carlos Centro)
- SENASA, Reg. 12345 (marbete)
```

**Repregunta**
```
Para evaluar la receta me faltan 2 datos:
1. *Localidad*: ¿en qué localidad se aplica? (p. ej. "El Trébol")
2. *Tipo de aplicación*: elegí una opción.
[Terrestre] [Aérea]
```

**No resuelto**
```
⚠️ *No pude completar la evaluación*
*Qué no pude determinar:* la distancia mínima a zonas protegidas.
*Por qué:* la localidad no está entre las cargadas en el sistema.
*Qué sí evalué:* el producto está registrado y autorizado para soja ✅
*Qué podés hacer:* consultar la ordenanza de esa localidad o al área de ambiente del municipio.
```

**Consulta de productos**
```
*Productos registrados para yuyo colorado en soja* (3 de 23)
1. Marca A · Reg. SENASA 12345 · Banda III (azul) · 1,5–2 L/ha
2. Marca B · Reg. SENASA 23456 · Banda IV (verde) · 2–3 L/ha
3. Marca C · Reg. SENASA 34567 · Banda IV (verde) · 0,8–1 L/ha
Es lo que figura en el registro; qué aplicar lo define la receta del ingeniero agrónomo.

*Fuentes*
- SENASA, vademécum (datos al 11/09/2026)
```

**Consulta normativa**
```
*No.* En San Carlos Centro la distancia mínima para aplicación terrestre a establecimientos educativos es de 100 m.

*Fuentes*
- Ordenanza 914/2018, art. 8 (San Carlos Centro)
```

**Fuera de dominio**
```
Solo puedo ayudarte con recetas de fitosanitarios: leer y validar recetas, verificar productos registrados en SENASA y responder dudas sobre la normativa de aplicación de las localidades cargadas. ¿Me mandás una receta o una consulta sobre eso?
```

## Datos

### SENASA (vademécum)

- Fuente: API REST detrás de `https://aps2.senasa.gov.ar/vademecum/app/publico` (base `https://aps2.senasa.gov.ar/adt_api/api`, JSON HAL, sin auth). Listado: `productosAgroquimicosFormulados/search/publicSearchProductosFormuladosDTO`. Detalle: `productosAgroquimicosFormulados/search/publicSearchProducto?producto=...&projection=productoFormuladoPublicoProjection`. Relevado el 11/09/2026; verificar antes de usar.
- Usos y dosis: `aplicacionesPorProducto[]` cuando existe (pocos productos). Si no, del PDF Marbete en `productoDocumentos[].contenido` (base64). Muchos productos no tienen ninguno de los dos.
- Se scrapea una vez con throttling (~1 req/s), checkpoint reanudable y User-Agent identificable. Se guarda un snapshot versionado; el sistema nunca consulta SENASA en vivo.
- Se carga normalizado en el schema `catalogo` (ver "Base de datos"), nunca como tabla plana.
- Limpiar HTML en `sustanciasActivas` (`<b>`), normalizar mayúsculas y tildes ("Algodon") y colores de banda.

### Contrato de insumos manuales (lo carga el equipo)

Formato propuesto; se congela al cerrar la Fase 1 y cualquier cambio va a DECISIONES.

```
data/insumos/
├── <provincia>/                    p. ej. santa-fe
│   ├── ley-NNNNN-AAAA.pdf          normativa provincial (una o más)
│   ├── reglas.csv                  opcional (reglas de la normativa provincial)
│   └── <jurisdiccion_id>/          municipio de esa provincia, p. ej. san-carlos-centro
│       ├── localidad.geojson
│       ├── ordenanza-914-2018.pdf  normas municipales vigentes (una o más)
│       └── reglas.csv              opcional: sin él, las distancias se leen del PDF
└── normativa-general/
    └── nacional/
        ├── ley-NNNNN-AAAA.pdf
        └── reglas.csv              opcional
```

- Nombres de carpeta (`provincia`, `jurisdiccion_id`): minúsculas, sin tildes, palabras separadas por guion. Son la clave que une geometría, normativa y reglas. La provincia de una localidad es la carpeta que la contiene; la normativa provincial vive en esa misma carpeta.
- PDFs: `<tipo>-<numero>-<anio>.pdf`, con tipo `ordenanza | decreto | resolucion | ley`. De ahí sale la cita ("Ordenanza 914/2018") y el ámbito (municipal, provincial o nacional) sale de la carpeta. Solo normas vigentes; si una fue modificada, va también la modificatoria o el texto ordenado.
- `localidad.geojson`: `FeatureCollection` en EPSG:4326 (lat/lon). Cada feature lleva la propiedad `tipo`:
  - `limite`: exactamente una, `Polygon` o `MultiPolygon`, con propiedades `nombre` y `provincia` (igual al nombre de la carpeta de la provincia que la contiene).
  - `escuela`, `curso_agua`, `zona_urbana` u `otro`: zonas protegidas, con propiedad `nombre`. Pueden ser `Point`, `LineString` o `Polygon` (una escuela como punto, un arroyo como línea); la distancia se calcula igual.
- `reglas.csv`: columnas `tipo_zona, tipo_aplicacion, bandas, distancia_min_m, norma, articulo, observaciones`.
  - Una fila significa: dentro de `distancia_min_m` de una zona `tipo_zona` no se puede hacer una aplicación `tipo_aplicacion` con productos de las bandas indicadas.
  - `tipo_zona`: los valores de `tipo` del GeoJSON, salvo `limite`. `tipo_aplicacion`: `terrestre | aerea | todas`. `bandas`: `todas` o lista con `;` (`Ia;Ib;II`).
  - `norma`: nombre de un PDF de la misma carpeta, sin extensión (`ordenanza-914-2018`). `articulo`: número.
  - `observaciones`: condiciones que el modelo no cubre (aviso previo, horarios, viento). El dictamen las muestra como advertencia.
- El validador falla con mensajes claros si: a una carpeta de localidad o de provincia le falta al menos una norma (PDF o `.md`); el GeoJSON no tiene exactamente un `limite` o trae un tipo desconocido; una geometría es inválida o cae fuera de Argentina; la `provincia` del límite no coincide con la carpeta de la provincia donde está la localidad; una regla cita una norma que no está en su carpeta; un nombre de archivo o carpeta no respeta la convención.
- El validador avisa (sin fallar) si: un PDF no tiene texto extraíble (escaneado, va por OCR); una jurisdicción no tiene filas en `reglas.csv` (sus distancias se leen del PDF); una localidad no tiene `localidad.geojson` (es opcional desde el 22/09/2026).
- Para testear, `tests/fixtures/insumos/` es una copia congelada de `data/insumos/` (desde el 26/09/2026 no hay datos inventados; ver DECISIONES.md). `scripts/generar_fixtures_insumos.py` la regenera.
- Los loaders cargan todo al schema `territorio`: los archivos son la fuente, pero las tools consultan la base.

## Canal WhatsApp: gotchas

- Número de prueba gratuito, hasta 5 destinatarios verificados. Token de System User; el temporal del panel vence enseguida.
- Webhook: handshake `hub.verify_token`/`hub.challenge`, validar `X-Hub-Signature-256` con App Secret en tiempo constante, 200 inmediato y procesamiento en segundo plano, deduplicar por `message.id`, recorrer todos los `entry[].changes[].value.messages[]` e ignorar `statuses`.
- Imagen: `GET /{media-id}` devuelve una URL válida 5 minutos; descargar con Bearer. JPEG/PNG hasta 5 MB. Cachear la extracción por hash de la imagen.
- Ubicación: mensaje `location` con `latitude`/`longitude`.
- Argentina: `from` llega como `549XXXXXXXXXX`; en modo desarrollo enviar a `54XXXXXXXXXX` (sin el 9) o falla con 131030. Normalizar en un solo lugar (`WHATSAPP_AR_QUITAR_9`).
- Ventana de 24 h: el operario inicia; el bot nunca escribe primero.
- Túnel HTTPS (cloudflared/ngrok) para desarrollo y defensa. El notebook de demo es el plan B sin WhatsApp.

## LLM y cuotas

- Proveedor por configuración: Gemini Flash (multimodal, principal) o Groq. Verificar modelos y cuotas vigentes; no hardcodear límites.
- Rotación de `GEMINI_API_KEY_1..5` ante 429, en el agente (`RotarKeyAnteCuota`) y en las llamadas sueltas de las tools. Si se agotan todas, el turno responde el mensaje de error técnico.
- Cachear `leer_receta` por hash de imagen y la extracción de marbetes por n.º de registro.
- Con `USE_FIXTURES=true` todo el flujo corre sin red (LLM grabado o fake, SENASA desde snapshot).

## Tests y evaluación

- Unitarios de servicios (localidad, dosis, reglas, matching, parser de dosis) con casos borde: localidad ambigua, unidades raras, rangos con coma decimal, empates de matching.
- Tools con base de test (Docker) y fixtures.
- Retrievers con tests de integración contra Postgres real (Docker) y la copia de los insumos reales; por ejemplo, que el filtro por jurisdicción excluya artículos de otras localidades.
- Test de esquema: no existe ninguna tabla genérica de documentos + embedding.
- Orquestador con LLM fake: ruteo, repregunta, límite de repreguntas, fuera de dominio, cancelar.
- Snapshot de cada plantilla.
- `evals/` con 40+ conversaciones etiquetadas y script que reporta exactitud de ruteo, citas inválidas y dictámenes fuera de plantilla. Metas: ruteo ≥ 90 %, 0 citas inventadas, 100 % por plantilla.

## Convenciones

- Python 3.12, pydantic v2, FastAPI, pytest, ruff, type hints en todo.
- Dominio en español (`receta`, `evaluar_riesgo`, `jurisdiccion_id`); infraestructura genérica puede ir en inglés.
- Configuración solo por `config.py` leyendo `.env` (nunca versionado). Variables: `DATABASE_URL`, `LLM_PROVIDER`, `GEMINI_API_KEY_1..5`, `GEMINI_MODEL`, `GROQ_API_KEY`, `GROQ_MODEL`, `EMBEDDINGS_MODEL`, `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_APP_SECRET`, `WHATSAPP_VERIFY_TOKEN`, `WHATSAPP_GRAPH_VERSION`, `WHATSAPP_AR_QUITAR_9`, `SENASA_BASE_URL`, `SENASA_REQ_POR_SEG`, `DOSIS_TOLERANCIA_PCT`, `RAG_UMBRAL_SIMILITUD`, `METEO_BASE_URL`, `METEO_HORIZONTE_DIAS`, `MODO_DEMO_REFORMULACION`, `USE_FIXTURES`.
- Logs estructurados por turno (intención, tools, estados, latencia, tokens). Nunca tokens de API, imágenes ni números de teléfono completos.
- Commits chicos, uno por tarea del plan.
