# Decisiones

## RAG de equipos: `catalogo.vehiculo` pasa a soportar embeddings y entidades puntuales (post-Fase 11)

### Se revierte la decisión de la Fase 9 ("matching sin embeddings"), a pedido explícito del usuario

La Fase 9 había decidido deliberadamente no usar embeddings para `catalogo.vehiculo` (ver esa sección más abajo): "un puñado de categorías fijas" no lo justificaba. El usuario pidió expresamente agregar búsqueda semántica ("el RAG de los equipos") porque el catálogo dejó de ser solo categorías genéricas: ahora puede tener **equipos puntuales** (una entidad distinta por matrícula/modelo, no una categoría). Con más de una unidad del mismo `tipo_aplicacion` (dos aviones), el matching por substring/trigram ya no alcanza para distinguir "la avioneta grande" de "la dromader" -- se necesita similitud semántica real.

Se agregaron 3 columnas a `catalogo.vehiculo` (migración 001, aplicada a mano a la base de dev con `ALTER TABLE`, ver DIFICULTADES.md de fases previas sobre por qué editar el archivo no alcanza): `matricula TEXT` (nullable -- las categorías genéricas no tienen), `caracteristicas JSONB DEFAULT '{}'` (modelo, motor, capacidad, ancho de faja -- semiestructurado, mismo criterio que `catalogo.producto.toxicidad`) y `embedding vector(768)` con índice HNSW. `servicios/resolucion_vehiculo.py::resolver_vehiculo` ahora requiere `modelo_embeddings` y, si no hay match exacto por substring, calcula un score combinado `0.5 * trigram + 0.5 * (1 - distancia_coseno)` -- mismo patrón que `datos/retrievers/catalogo.py::buscar_productos_por_nombre`, umbral 0,5 (`UMBRAL_SIMILITUD_RAG`, calibrado empíricamente igual que el de normativa: "avioneta grande turbohelice" score ~0,6+ contra el Air Tractor). `tools/resolver_vehiculo.py` y `tools/registrar_evento.py` pasaron de `con_conexion` a `con_conexion_y_modelo` para poder pasarle el modelo al servicio.

`scripts/cargar_vehiculos.py` (nuevo) calcula el embedding de cada fila a partir de nombre + sinónimos + modelo/motor de `caracteristicas` -- hay que correrlo después de tocar la tabla a mano, igual que `loader_normativa.py` para `territorio.articulo`.

### Los 2 aviones nuevos: modelos reales, matrícula ficticia a propósito

Se agregaron "Air Tractor AT-502B" y "PZL M18 Dromader" -- ambos aviones agrícolas reales y de uso común en Argentina (elegidos por ser representativos, no porque el usuario haya dado modelos puntuales), con matrícula `LV-EJEMPLO1`/`LV-EJEMPLO2`. Deliberadamente **no** siguen el formato real de matrícula argentina (`LV-XXX`, 3 letras) para que no se puedan confundir con una matrícula real de un avión existente. `características` incluye motor/capacidad/ancho de faja de cada modelo (datos públicos de fabricante, no verificados contra una ficha técnica puntual -- alcanza para el propósito de esta demo, no para un dictamen).

### Extendido `guardar_receta_en_curso` para aceptar `fecha_prevista`, sin cambiar el comportamiento existente

Al armar el test end-to-end (`scripts/demo_avion_agenda.py`) se encontró que `orquestador/estado.py::guardar_receta_en_curso` nunca escribía `fecha_prevista` -- la columna existe desde la Fase 1 y `consultar_agenda_logica` filtra por ella, pero no había ningún camino (ni de test, ni de código de producción) que la seteara vía esta función; los tests de agenda insertan la fila directo por SQL (ver DIFICULTADES.md). Se agregó `fecha_prevista` a los `INSERT`/`UPDATE` de `guardar_receta_en_curso` (con `COALESCE`, igual que el resto de los campos) -- cambio mínimo y retrocompatible: quien no pase `fecha_prevista` en `campos` obtiene exactamente el comportamiento de antes (`None`, columna sin tocar). No se conectó `guardar_receta_en_curso` al flujo del orquestador real (eso seguiría siendo una fase aparte, ver Fase 0 "Ampliación del modelo Receta"); el script de demo la llama directo, documentado como tal en su propio docstring.

### `scripts/demo_avion_agenda.py`: test end-to-end verificado, corre contra Gemini/embeddings/Postgres reales

Ejercita, en un solo script ejecutable (`uv run python scripts/demo_avion_agenda.py`): `leer_receta` sobre una imagen real (`data/recetas_ejemplo/01_apta_terrestre_lejos.jpg`) → guardar la receta con `fecha_prevista` de hoy → `registrar_evento` (iniciar) con una descripción de avión que **no** es ningún sinónimo cargado ("la avioneta grande turbohelice", resuelta por RAG al Air Tractor) → `consultar_agenda` (confirma `en_curso`) → `registrar_evento` (finalizar) → `consultar_agenda` de nuevo (confirma `finalizada`). Corrido de punta a punta antes de entregarlo: los 5 pasos dieron el resultado esperado.

## Carga de datos reales de El Trébol y recalibración de RAG_UMBRAL_SIMILITUD (post-Fase 11)

### Insumos de El Trébol no respetaban el contrato de la skill: normalizado el formato, no el contenido

Los archivos crudos en `data/insumos/localidades/el-trebol/` venían de fuentes públicas (GeoJSON del límite descargado de INDEC tal cual, con las propiedades propias del shapefile de origen; PDF de la Ordenanza 841/2010 de la Municipalidad de El Trébol) sin adaptar al contrato de `docs/contrato-insumos.md`/skill. Se corrigió solo el formato:

- `el-trebol.geojson` → renombrado a `localidad.geojson` (nombre fijo que exige el contrato; el validador lo reportaba como "falta localidad.geojson").
- Agregadas las propiedades `tipo: "limite"`, `nombre: "El Trébol"` y `provincia: "santa-fe"` al feature del límite -- el GeoJSON de origen no las traía, y sin `tipo: "limite"` `loader_geo.py::cargar_localidad` rompe con un `StopIteration`.
- `ley-055297-2017.pdf` y `ley-11273-1995.pdf` movidas de `normativa-general/provincial/` a `normativa-general/provincial/santa-fe/`: el loader espera una subcarpeta por provincia y las saltea silenciosamente si están sueltas.

### Zona `zona_urbana` agregada al GeoJSON: aproximación del "Límite Agronómico" del art. 1, marcada como supuesto

La Ordenanza 841/2010 mide las distancias de los artículos 6 y 7 desde el "Límite Agronómico o Límite 0" (art. 1), delimitado por un plano específico adjunto a la ordenanza que no está digitalizado por separado en este proyecto. Se usó el mismo polígono del límite catastral de INDEC (el que ya se carga como `limite` de jurisdicción) como aproximación, agregado además como zona protegida `tipo: "zona_urbana"`. Confirmado con el usuario antes de cargarlo (no es un dato verificado contra el plano real). **Pendiente de verificar**: si el plano del Límite Agronómico difiere del límite catastral INDEC, las distancias de `evaluar_riesgo`/`evaluar_viabilidad_legal` para El Trébol van a estar calculadas contra un límite aproximado, no el legal exacto.

### `reglas.csv` de El Trébol: solo los artículos con distancia numérica (6 y 7); 2, 3 y 9 quedan sin representar

El modelo de `territorio.regla_distancia` (distancia mínima a una zona protegida) no puede representar "prohibido aplicar/circular *dentro* de una zona" (arts. 2 y 3: solo banda D excepcional dentro del límite, terrestre no puede ni entrar) ni una restricción sin distancia numérica fija y sin esa geometría cargada (art. 9: cerca de vías del ferrocarril / Ruta Provincial 13). Se cargaron solo las dos reglas con distancia explícita, confirmadas con el usuario antes de cargar:

| Artículo | Regla | Cargada como (`tipo_zona, tipo_aplicacion, bandas, distancia_min_m`) |
|---|---|---|
| 6 | Aérea prohibida hasta 500 m del Límite 0, todas las bandas | `zona_urbana, aerea, todas, 500` |
| 7 | Aérea Banda Amarilla (II) prohibida hasta 3.000 m del Límite 0 | `zona_urbana, aerea, II, 3000` |
| 2, 3 | Terrestre no circula dentro del límite; solo Banda Verde excepcional adentro | no representable con el modelo actual de reglas |
| 9 | Prohibido cerca de vías del ferrocarril / Ruta Provincial 13 | sin distancia numérica ni geometría de esas vías cargada |

Si más adelante hace falta cubrir 2/3/9, el modelo de reglas necesita un tipo nuevo ("prohibido siempre dentro de la zona", distinto de "prohibido a menos de X metros de la zona").

### `RAG_UMBRAL_SIMILITUD` del `.env` real había drifteado a 0,75; recalibrado a 0,5 con el corpus real ya cargado

`.env.example` y `config.py` siguen documentando 0,35 (la calibración de la Fase 6, sobre un corpus sintético de 9 artículos). El `.env` real de esta máquina (no versionado) tenía 0,75 -- no se pudo determinar cuándo ni por qué volvió a subir respecto del valor documentado. Con el corpus real ya cargado (El Trébol + 2 leyes provinciales, 136 artículos), ninguna consulta -- de El Trébol ni de las localidades de fixtures -- superaba nunca 0,75; el artículo genuinamente correcto scoreaba 0,50-0,63 según la localidad. Se subió el `.env` real a 0,5 (más alto que el 0,35 de la Fase 6, con un corpus más grande y heterogéneo para tener algo más de margen). La discriminación semántica pura sigue siendo débil (en una prueba, una pregunta totalmente fuera de tema scoreó 0,51, por encima de la cita correcta de una pregunta real que scoreó 0,507 en ese caso puntual) -- funciona en la práctica porque la verificación final depende de que el LLM efectivamente pueda citar, entre los fragmentos recuperados, un artículo que responda la pregunta (ver bug de citas abajo), no solo del score de similitud. **No se tocó `.env.example`/`config.py`** (0,35 sigue siendo el default para quien clona el repo); si 0,5 se confirma como mejor valor con más pruebas, actualizar ahí también.

### Bug real: las citas del LLM se descartaban siempre por un mismatch de formato en el número de artículo

`servicios/rag_normativa.py::_armar_contexto` arma el contexto que ve el LLM etiquetando cada fragmento como `"[archivo, art. {numero}, ...]"`. El LLM, al citar el artículo en su respuesta JSON, tiende a copiar ese mismo formato (`"articulo": "art. 7"`) en vez de devolver solo el número tal como pide el prompt de sistema. El matching de citas contra `fragmentos_por_clave` es una comparación exacta de tupla `(norma, numero)`, así que `"art. 7" != "7"` descartaba la cita siempre -- la respuesta correcta del LLM terminaba en la advertencia "citó un artículo que no está entre los fragmentos recuperados" y la tool devolvía `no_resuelto` (`NORMATIVA_SIN_RESPALDO`) aunque el LLM hubiera respondido bien. No es un problema específico de El Trébol: afecta a cualquier localidad; simplemente nunca se había probado con Gemini real después de la Fase 6 (los tests usan un LLM fake que no reproduce este estilo de respuesta). Corregido con `_normalizar_numero_articulo` (extrae solo los dígitos), aplicado a ambos lados del matching antes de comparar. Verificado con dos preguntas reales contra El Trébol con Gemini real: ambas citan ahora el artículo correcto (7 y 3 respectivamente). Los 90 tests de `tools`/`servicios` siguen pasando sin cambios.

### 3 recetas de ejemplo generadas para El Trébol, con producto/dosis reales del catálogo SENASA ya cargado

`scripts/generar_recetas_ejemplo_el_trebol.py` (nuevo, análogo a `generar_fixtures_recetas.py` de la Fase 4 pero con datos reales en vez de sintéticos) genera 3 imágenes en `data/recetas_ejemplo/` (gitignored) pensadas para ejercitar las reglas de distancia recién cargadas: una APTA (terrestre, lejos del límite urbano), una OBSERVADA por distancia (aérea, banda amarilla, ~300 m del límite -- viola arts. 6 y 7 a la vez) y una OBSERVADA por dosis (mismo tipo de aplicación y ubicación que la APTA, pero con la dosis muy por encima de lo registrado). Los tres usan productos reales con dosis registrada real (Flyer 10 Ec, reg. 41881, Banda II; Imazamox 70 Wg Brilliance, reg. 41759, Banda III) -- no números inventados. Las coordenadas de "cerca"/"lejos" del límite se calcularon con `pyproj.Geod` (geodésico real), no a ojo, mismo criterio que la Fase 5 con San Carlos Centro. Los tres casos se corrieron contra `evaluar_viabilidad_legal_logica` real antes de darlos por buenos, lo cual destapó un cuarto hallazgo (ver DIFICULTADES.md): los 3 dieron `JURISDICCION_NO_CUBIERTA`, porque el `limite` cargado es la mancha urbana de INDEC, no el partido/municipio real -- ningún punto de campo (donde está cualquier lote real) cae dentro. Las 3 imágenes quedan generadas igual, con el resultado esperado y este bloqueo documentados en `data/recetas_ejemplo/notas.txt`, para usarlas en cuanto se cargue el polígono de jurisdicción correcto.

## Fase 10 — Demo, documentación y defensa

### "cm3" sin el superíndice unicode: un bug real, no una limitación aceptada

Al armar el guion de la demo se encontró la causa raíz de un resultado que venía apareciendo desde la Fase 7 (documentado hasta ahora como "limitación conocida"): `Dosis 170.0 cm3/ha: unidad no reconocida` en el caso exacto del plan (Flyer 10 Ec, soja, 170 cm³/ha). `servicios/dosis.py::_FAMILIAS_UNIDAD` solo reconocía la clave `"cm³"` (con el superíndice unicode "³"), nunca `"cm3"` (ASCII, "3" normal) -- y el operario (o el LLM que transcribe lo que escribió) casi nunca usa el superíndice, que ni siquiera está en un teclado de celular estándar. Se corrigió agregando `"cm3"` como alias en `_FAMILIAS_UNIDAD`, sin tocar `parser_dosis.py` (que normaliza el texto de SENASA, un problema distinto). Esto abre camino a que el caso APTA del guion de demo (`docs/guion-demo.md`) funcione con la redacción natural que cualquier persona escribiría, no solo con el argumento estructurado exacto que usaban los tests de `evaluar_viabilidad_legal_logica`.

### Resultado de evals antes de la entrega: 79 % (23/29), por debajo del objetivo de 90 %

Se corrió `evals/run_evals.py` dos veces seguidas contra Gemini real al cerrar esta fase; ambas corridas dieron el mismo resultado exacto (79 %, 23/29, los mismos 6 casos incorrectos) -- no es ruido de muestreo, es reproducible. Se investigó cada caso incorrecto contra el detalle de `evals/ultima_corrida.json` en vez de reportar el número a secas:

- **3 casos (`repregunta_04`, `repregunta_05`, `repregunta_08`)**: la métrica de ruteo los marca "incorrectos" porque el LLM invocó alguna tool (`validar_producto_registro`/`responder_consulta_normativa`) antes de repreguntar, cuando lo esperado era no llamar ninguna. Pero el `tipo_obtenido` final de los tres es `repregunta`, con una pregunta sensata (pide el cultivo o la localidad faltante) -- la conversación termina bien para el operario. Es una limitación de la métrica ("qué tool se llamó primero"), no un error de comportamiento observable.
- **3 casos (`ambiguedad_01`, `ruteo_13`, `ruteo_16`)**: preguntan por UN producto puntual sin mencionar el cultivo ("¿el producto X está autorizado para algún cultivo en particular?"). El LLM a veces llama `consultar_productos` en vez de `validar_producto_registro` + repregunta -- pese a que la propia descripción de la tool ya dice explícitamente "no para preguntar por un producto puntual". `consultar_productos` ni siquiera acepta un nombre de producto como filtro, así que la llamada es un error categórico del LLM en esos casos, no una elección defendible. Antes de la Fase 7 esto directamente hacía `raise ValueError` sin capturar (`consultar_productos` llamada sin ningún filtro); con la excepción ya capturada, ahora se ve el resultado real en vez de un "error" que quedaba afuera del denominador de la métrica -- por eso el número bajó de 89 % (24/27, Fase 7) a 79 % (23/29): son más casos *visibles*, no más casos *rotos*.

No se hizo más ingeniería de prompt para forzar el número a 90 %: la guía de la propia tool ya es explícita y el LLM la ignora en un puñado de frases límite -- es variabilidad inherente de un LLM con temperatura no nula, no un bug determinístico corregible. Documentado tal cual, sin inflar el número (ver "qué recortar" en `plandefases.md`, que pide exactamente esto para la meta de evals).

## Fase 9 — Extensiones (resolver_vehiculo, registrar_evento, consultar_agenda)

### Alcance definido por el usuario, no inferido de la skill

La skill `agente-fitosanitarios` no menciona vehículo/evento/agenda en ningún lado (confirmado por grep contra `SKILL.md`, cero resultados): RF6-RF9 solo estaban nombrados en `plandefases.md`, sin especificar. Antes de escribir código se le preguntó al usuario, por chat, qué es "un vehículo", "un evento" y "una agenda" en este dominio y cuáles de las 4 extensiones abordar. Definiciones y alcance confirmados: `resolver_vehiculo` (interpretar en lenguaje natural el vehículo a partir de una descripción informal), `registrar_evento` (inicio/fin de una aplicación, asociada a receta+vehículo+lote), y una tercera (`consultar_agenda`: agenda/plan del día con tareas y su estado). Se excluyó explícitamente la identificación automática de un operario recurrente por su número -- el `thread_id` que usan las otras dos tools para scopear datos es infraestructura ya existente desde la Fase 7/8, no esa RF.

### `config: RunnableConfig` inyectado en la tool para saber "de quién" es el turno

`registrar_evento` ("finalizar" necesita encontrar el evento en curso del operario correcto) y `consultar_agenda` ("mi agenda") necesitan `thread_id`, que ninguna tool anterior recibía -- siempre fue puro texto/args del LLM. Se verificó en el código que `orquestador/turno.py::ejecutar_turno` ya arma `config={"configurable": {"thread_id": ...}}` en *todos* los casos (producción y los tests de `test_ruteo.py`), y se confirmó leyendo `langchain_core/tools/base.py` (función `_find_config_param`) que LangChain soporta inyectar un parámetro `config: RunnableConfig` en la función de una `@tool` sin exponerlo en el schema que ve el LLM. Se implementó así en `registrar_evento`/`consultar_agenda`, y se verificó empíricamente con un test de ruteo (`test_ruteo_registrar_evento_usa_el_thread_id_del_turno`) antes de construir el resto de la fase encima -- funcionó al primer intento. Alternativa descartada: repetir el patrón de tool "ligada" por clausura de `crear_tool_leer_receta_ligada` (Fase 8), que hubiera obligado a reconstruir el agente en cada turno de texto (no solo con imagen) para bindear el `thread_id`; se deja documentada como plan B si en algún momento la inyección de config dejara de funcionar (p. ej. un cambio de versión de LangChain).

### Matching de vehículo sin embeddings

A diferencia de `catalogo.producto` (7370 filas, necesita trigram+embedding), `catalogo.vehiculo` es un puñado de categorías fijas ("pulverizador autopropulsado", "pulverizador de arrastre", "mochila", "avión fumigador", "dron"), sembradas directamente en la migración (no hay un crawler ni un loader para esto, es contenido de referencia curado a mano). Se resuelve con sinónimos (JSONB) chequeados como substring de la descripción del operario (case-insensitive, vía `ILIKE`) y similitud de trigram como fallback de typos -- sin columna `vector` ni cargar `sentence-transformers` para esto. Se agregó `tools/_recursos.py::con_conexion` (sin el modelo de embeddings) para no pagar ese costo en las 3 tools nuevas.

### `MotivoNoResuelto` extendido para RFs fuera del alcance de la skill

Se agregaron `VEHICULO_NO_ENCONTRADO` y `SIN_EVENTO_EN_CURSO` al catálogo de `dominio/motivos.py`, que el propio módulo documenta como "reproducidos tal cual" de la skill. Esto no contradice esa fuente de verdad: la skill nunca definió motivos para RF6/RF7 porque no los cubre; extender el catálogo para una funcionalidad fuera de su alcance es una decisión de esta fase, no una desviación de lo que la skill sí especifica para el núcleo.

### Un evento sin receta asociada no aparece en la agenda (verificado en la demo real)

Al correr `notebooks/demo_sin_whatsapp.ipynb` de punta a punta contra Gemini y Postgres reales, "Empecé a aplicar con la mosquito en el lote 4" -> "Terminé de aplicar" -> "¿qué tengo para hoy?" registró correctamente el evento pero la agenda respondió "No tenés tareas agendadas": `registrar_evento` se llamó sin `receta_id` (el operario no tenía una receta confirmada previa en esa conversación) y `consultar_agenda_logica` arma la lista a partir de `operacion.receta`, no de `operacion.evento_aplicacion` de forma independiente. Es el comportamiento esperado según el diseño (ver "Agenda reusa `fecha_prevista`" abajo), no un bug -- pero es una limitación real para un operario que aplica sin una receta cargada de antemano. Documentado para una futura iteración si hiciera falta que la agenda también liste eventos sueltos.

### Agenda reusa `fecha_prevista`, no inventa un concepto de "asignación"

No hay en este dominio un sistema donde un ingeniero agrónomo "asigna" tareas a un operario -- eso hubiera sido una funcionalidad nueva por completo. `consultar_agenda` reusa `operacion.receta.fecha_prevista` (columna que existe desde la Fase 1) como la fecha de la "tarea", combinada con el último `operacion.evento_aplicacion` de esa receta para el estado (pendiente/en_curso/finalizada). Simplificación aceptada para no expandir el alcance más allá de lo confirmado.

## Fase 8 — Canal WhatsApp

### `leer_receta` no puede recibir una foto real como argumento de tool (límite de tokens de salida)

El contrato de `leer_receta` desde la Fase 4 (`imagen_base64: str` como argumento de la tool, ver `tools/leer_receta.py`) asume que el LLM orquestador recibe la imagen y la "pasa" como argumento del tool call. Funciona en los tests de la Fase 7 porque usan imágenes sintéticas de pocos bytes (`b"fake"`), pero al diseñar el canal real se encontró que es inviable para una foto real: una imagen JPEG de WhatsApp de, por ejemplo, 300 KB pesa ~400 KB en base64 (~100 000 tokens en texto), muy por encima del límite de tokens de salida de un tool call de un LLM (unos pocos miles en la mayoría de los modelos); y aunque el límite alcanzara, un LLM no reproduce un string tan largo carácter a carácter de forma confiable -- un solo carácter alterado invalida el base64.

Se resolvió sin tocar el contrato de `leer_receta` (que sigue tal cual para los tests existentes) agregando `tools/leer_receta.py::crear_tool_leer_receta_ligada(imagen_base64)`: una variante de la misma tool, sin parámetros, con la imagen ya "ligada" por clausura de Python. `orquestador/agente.py::construir_tools(imagen_base64=None)` arma la lista de tools reemplazando `leer_receta` por esta variante solo cuando el canal (el webhook) ya descargó una imagen para ese turno puntual; `crear_agente(..., imagen_base64=...)` arma un agente nuevo con esa lista para ese turno. El LLM solo tiene que *decidir* llamar a `leer_receta` (sin argumentos que inventar), nunca transportar los bytes de la imagen. Reconstruir el agente por turno es barato (no reabre el checkpointer de Postgres, que se sigue pasando por referencia) y no afecta el historial de conversación del `thread_id`, que vive en el checkpointer, no en el objeto `agente` en sí.

### Deduplicación de mensajes en Postgres, no en memoria como el contador de repreguntas

A diferencia de `ContadorRepreguntas` (Fase 7, en memoria de proceso, aceptado como simplificación porque solo afecta al flujo de una conversación en curso), la deduplicación de `message.id` de WhatsApp (`canales/whatsapp/dedup.py`) se persiste en una tabla nueva (`operacion.mensaje_whatsapp`, migración 003). Motivo: Meta puede reintentar la entrega de un mensaje después de que el proceso del webhook se haya reiniciado (deploy, crash, restart manual); si la deduplicación fuera solo en memoria, un reinicio en el momento exacto de un reintento causaría un doble procesamiento (dos dictámenes, dos mensajes de WhatsApp duplicados al operario) -- un efecto visible y molesto para el usuario, a diferencia de perder el contador de repreguntas (que como mucho hace repreguntar una vez de más). El `INSERT ... ON CONFLICT DO NOTHING` es atómico, evita necesitar un `SELECT` previo que dejaría una ventana de carrera entre dos entregas casi simultáneas.

### `procesar_mensaje` inyectado en `crear_app`, no construido adentro del módulo del webhook

`canales/whatsapp/webhook.py::crear_app(settings, procesar_mensaje)` recibe la función de procesamiento real como parámetro en vez de construirla ella misma (agente + Gemini + checkpointer de Postgres). Así los tests de protocolo del webhook (`tests/canales/test_webhook.py`: handshake, firma, dedup, `statuses` ignorados) no necesitan credenciales de Gemini ni levantar un checkpointer real -- inyectan un `procesar_mensaje` de prueba que solo registra las llamadas. `canales/whatsapp/app_produccion.py` es el único módulo que arma la versión real (`crear_app_produccion`) y es el entrypoint de `uvicorn`; no lo importa ningún test.

### `WHATSAPP_GRAPH_VERSION` corregido a `v26.0`

El default en `config.py` había quedado en `v23.0` desde una fase anterior mientras `.env.example` ya documentaba `v26.0` como la versión verificada en vivo contra el número de prueba (12/09/2026). Se corrigió el default de `config.py` para que coincida (tarea 11 del plan: "verificar versión vigente y dejarla configurable" -- configurable ya lo era, pero el default estaba desactualizado).

### Notebook de demo: dos observaciones reales del recorrido de punta a punta (no son bugs de esta fase)

Al ejecutar `notebooks/demo_sin_whatsapp.ipynb` con kernel limpio contra Gemini real y Postgres real (criterio de aceptación de esta fase), aparecieron dos comportamientos que ya eran limitaciones conocidas de fases anteriores, no regresiones de la Fase 8: (1) la dosis "170 cm3/ha" del caso de ejemplo del plan sigue dando "unidad no reconocida" en `evaluar_viabilidad_legal" (mismo hallazgo que en los evals de la Fase 7, `ruteo_10`); (2) una pregunta de normativa sobre distancia a escuela en San Carlos Centro, con una redacción distinta a la usada al calibrar `RAG_UMBRAL_SIMILITUD` en la Fase 6, no superó el umbral y devolvió `no_resuelto` en vez de citar el artículo 8 (que sí es el relevante). Ambas quedan documentadas para una futura fase de ajuste fino del núcleo experto (parser de dosis y/o umbral RAG dependiente de la redacción), fuera del alcance de "conectar el canal" de esta fase.

## Fase 7 — Orquestador

### `response_format` necesita `ToolStrategy(RespuestaAgente)` explícito, no la clase pydantic pelada

Verificado interactivamente antes de escribir `agente.py`: pasar `response_format=RespuestaAgente` (la clase pydantic sola) a `create_agent` nunca disparó la extracción de `structured_response` contra un chat model fake -- el grafo terminaba el turno en el primer `AIMessage` sin `tool_calls` y `structured_response` quedaba `None`. Pasando `response_format=ToolStrategy(RespuestaAgente)` explícito, y haciendo que el modelo (real o fake) termine el turno con un `tool_call` al nombre de esa clase, funciona: `structured_response` se llena correctamente. Se usa `ToolStrategy` siempre (no solo en tests) para que el comportamiento sea el mismo con Gemini real.

### Chat model fake propio para testear el agente (`tests/orquestador/fake_chat_model.py`)

Los fakes genéricos de `langchain_core` (`GenericFakeChatModel`, `FakeListChatModel`) no simulan tool-calling de forma controlable turno a turno. Se armó un `BaseChatModel` propio que devuelve, en orden, `AIMessage`s precargados (con o sin `tool_calls`) y no depende de red ni de Postgres. Confirmado con un smoke test que `ToolMessage.artifact` efectivamente llega con la instancia pydantic completa del `ResultadoTool` cuando la tool real se declaró con `response_format="content_and_artifact"` -- eso es lo que permite que `orquestador/turno.py` arme el texto final desde los artifacts, nunca desde el texto libre del LLM.

### Contador de repreguntas en memoria de proceso, no en el estado de LangGraph ni en Postgres

Se evaluó extender el `state_schema` de `create_agent` con campos propios (`receta_en_curso`, `intentos_fallidos`), pero requiere diseñar reducers propios para esos campos y no se justificaba el tiempo para esta fase. Se optó por un `ContadorRepreguntas` en memoria, manejado por `orquestador/turno.py` (fuera de LangGraph), y la receta en curso sí persiste en Postgres (`operacion.receta`, ya existía desde la Fase 1) vía funciones simples en `orquestador/estado.py`. Limitación conocida: el contador de repreguntas no sobrevive un reinicio del proceso -- aceptable para esta POC, la memoria de conversación real (los mensajes) sí persiste en Postgres vía el checkpointer de LangGraph.

### `evaluar_riesgo`/`evaluar_viabilidad_legal` con múltiples productos: cada uno se evalúa por separado contra cada zona

Ver también `docs/matriz-parametros.md`. No se colapsa a "peor caso" por banda: una regla puede aplicar a un producto y no a otro en la misma receta.

### Hallazgo real de datos: dosis ambigua por adversidad no especificada (corregido)

Al correr `test_ruteo_evaluar_viabilidad_legal` contra datos reales, "Flyer 10 Ec" en soja dio `OBSERVADA` por dosis fuera de rango cuando debía dar `APTA` -- el producto tiene rangos de dosis DISTINTOS según la adversidad (160-180 cm³/ha para "Chinche De La Alfalfa", 25-35 para "Oruga De Las Leguminosas"), y `resolver_y_validar_producto` tomaba `usos_cultivo[0]` sin chequear si había ambigüedad. Corregido con `_dosis_sin_ambiguedad_de_adversidad`: si no se especificó adversidad y hay más de un rango distinto entre los usos del cultivo, la dosis queda sin comparar (va a `chequeos_no_realizados`, el dictamen puede terminar `NO_EVALUABLE` en vez de un `OBSERVADA` potencialmente equivocado) -- tal como pide la skill ("Rangos distintos por adversidad y adversidad desconocida: faltan_datos"). Ver `tests/servicios/test_validacion_producto.py`.

### Evals contra Gemini real: 89% de exactitud de ruteo (24/27), con 3 hallazgos reales

Corrida real completa de las 41 conversaciones etiquetadas (`evals/conversaciones.jsonl`) contra Gemini real + Postgres real el 12/09/2026 (`evals/run_evals.py`, sin `--limite`). Resultado: 24/27 casos de ruteo/repregunta/ambigüedad correctos (89%; la meta del plan es ≥90%, quedó 1 punto por debajo). Tres hallazgos concretos:

1. **`consultar_productos` llamada sin ningún filtro rompía el turno entero** (`ValueError` no capturado desde el `model_validator` de `ConsultarProductosArgs`, propagado sin control fuera de `agente.invoke()`). Es un bug real de robustez, no una cuestión de exactitud del LLM: corregido envolviendo `agente.invoke()` en `orquestador/turno.py` con un `try/except` que degrada a `RespuestaAgente(tipo="error")` en vez de crashear. Con esto, esos 2 casos pasan de "error" a una respuesta de error prolija para el usuario (no se corrigió que el LLM elija mal la tool en esos 2 casos puntuales -- "¿el producto X está autorizado para algún cultivo en particular?" no tiene una tool que responda bien esa pregunta tal como está planteada la matriz de parámetros: `validar_producto_registro` pide `cultivo` como requerido, no sirve para "en qué cultivos está autorizado". Queda anotado como gap de cobertura, no como bug).
2. **Dos casos "repregunta" esperados terminaron llamando `responder_consulta_normativa` sin `jurisdiccion_id`** en vez de repreguntar directamente sin llamar ninguna tool. El resultado para el usuario es igual de correcto (la tool devuelve `faltan_datos` con la lista de localidades) porque `responder_consulta_normativa_logica` maneja ese caso -- pero es una forma distinta a la que describe la skill ("si faltan parámetros requeridos no llama a la tool"). Se documenta como comportamiento aceptable (doble red de seguridad: orquestador y tool), no se fuerza al LLM a comportarse distinto vía prompt en esta sesión.
3. **Un caso "ambigüedad" ("¿el glifosato está habilitado para soja?") se resolvió como `consultar_productos`** (listado por principio activo) en vez de `validar_producto_registro` -- una interpretación alternativa defendible ("glifosato" es un principio activo genérico, no una marca puntual), no necesariamente un error.

No se re-corrieron las 41 conversaciones después del fix del punto 1 (el cambio es de manejo de excepciones, no de qué tool elige el LLM; hubiera movido 2 casos de "error" a "incorrecto" sin cambiar la exactitud real de ruteo del LLM). Las otras dos metas de la Fase 7 ("0 citas inventadas", "100% de dictámenes por plantilla") no se midieron con este eval porque están garantizadas por construcción (ver docstring de `evals/run_evals.py`), no por comportamiento del LLM en cada corrida.

### Advertencia de LangGraph sobre serialización de `RespuestaAgente` en el checkpoint

Al correr evals con `InMemorySaver`, apareció: `Deserializing unregistered type fitosanitarios.dominio.modelos.RespuestaAgente from checkpoint. This will be blocked in a future version.` LangGraph serializa el `structured_response` con `msgpack` y, en una versión futura, va a exigir registrar explícitamente los tipos pydantic propios (`allowed_msgpack_modules`) en vez de deserializar cualquier tipo. No rompe nada hoy (`langgraph==1.2.11`), pero **(verificar)** antes de actualizar `langgraph` más adelante: puede hacer falta registrar `RespuestaAgente` explícitamente.

### `crear_modelo_chat_gemini` usa una sola key, sin la rotación de `llm/client.py`

El agente (a diferencia de `extraccion_receta.py`/`rag_normativa.py`, que usan `ClienteGemini` con rotación real) usa `ChatGoogleGenerativeAI` con `gemini_api_keys[0]` nada más. `create_agent` no acepta un cliente con la interfaz custom de rotación; implementar rotación real para el agente completo (reintentar con la siguiente key ante 429 en medio de un tool-calling loop) queda pendiente -- no se hizo por tiempo. Mitigación mínima aceptada para la POC: si la primera key se agota, el agente va a fallar con la excepción sin capturar de LangChain, que ahora al menos no crashea el turno completo (ver el fix de manejo de excepciones arriba), pero tampoco reintenta con otra key.

## Fase 6 — `responder_consulta_normativa`

### `RAG_UMBRAL_SIMILITUD` recalibrado de 0,75 a 0,35 con scores reales

El default de la Fase 0 (0,75) se fijó sin datos reales, como placeholder razonable "a ojo". Al testear el retriever de artículos contra la normativa real cargada en la Fase 3, el artículo genuinamente más relevante a una pregunta bien formulada scoreó 0,50-0,58 de similitud coseno con `sentence-transformers/paraphrase-multilingual-mpnet-base-v2` -- muy por debajo de 0,75. Con el default viejo, **toda** consulta normativa hubiera devuelto `NORMATIVA_SIN_RESPALDO`, sin importar qué tan bien cargada estuviera la normativa. Se bajó a 0,35 (ver `config.py` y `.env.example`), calibrado contra el corpus sintético de 9 artículos de la Fase 3. **Sigue siendo una calibración chica** (9 artículos, no las decenas/cientos que va a haber con las 10 localidades reales); hay que revalidar cuando se cargue normativa real, y considerar si hace falta un umbral distinto por ámbito (municipal/provincial/nacional) si la mezcla de escalas resulta un problema.

### Hallazgo real y su causa raíz: `paraphrase-multilingual-mpnet-base-v2` da scores razonables para retrieval asimétrico pregunta-vs-artículo, PERO se estuvo probando contra datos corrompidos

Al testear por primera vez el retriever con una pregunta real, los scores salían casi en cero (0,03 el mejor, el artículo más relevante scoreaba peor que uno irrelevante). Se investigó a fondo (ver DIFICULTADES.md) y la causa **no** era el modelo de embeddings: era que `tests/insumos/test_loaders_integracion.py` (Fase 3) recargaba `territorio.articulo` con un modelo de embeddings **fake** cada vez que corría contra la base real de desarrollo -- la misma que se usa para verificación manual -- pisando los embeddings reales cargados en la Fase 3 con valores dummy secuenciales. Cada corrida de `pytest -q` completo desde la Fase 3 en adelante corrompía silenciosamente esos 9 embeddings. Se corrigió usando el modelo de embeddings real (la fixture compartida `modelo_embeddings` de `tests/conftest.py`) en `tests/insumos/test_loaders_integracion.py` y en `tests/senasa/test_loader.py` (que tenía el mismo problema sobre `catalogo.producto`, aunque ahí quedaba parcialmente enmascarado porque el score combinado también usa trigram). Costo: esos tests tardan más (cargan el modelo real), pero son correctos.

**Limitación de diseño que queda pendiente, no resuelta en esta sesión**: los tests de integración de `senasa/loader.py` e `insumos/loader_*.py` escriben contra la MISMA base de datos que se usa para desarrollo manual (`DATABASE_URL`), en vez de una base de test aislada. Esto ya causó un bug real (arriba). La corrección aplicada (dejar de usar embeddings fake) resuelve el síntoma, no la causa de fondo: cualquier test de integración que haga `DELETE`/`UPDATE` contra `DATABASE_URL` sigue pudiendo pisar datos reales de otra forma. Una base de test separada (`TEST_DATABASE_URL`, o un schema/DB con sufijo `_test`) sería la solución de fondo; no se implementó por tiempo. Documentado acá para que quede explícito, no oculto.

## Fase 5 — Tools de validación y dictamen

### Servicios probados con la geometría y las reglas reales de San Carlos Centro

`servicios/geo.py` y `servicios/reglas.py` se testearon contra la geometría real de la fixture de San Carlos Centro (Fase 3), no contra coordenadas inventadas. Las coordenadas de los puntos "a 80 m" y "a 100 m" de la Escuela N 12 se calcularon con `pyproj.Geod.fwd()` (geodésico real sobre WGS84), no a ojo -- así el test reproduce literalmente el criterio de aceptación del plan ("un lote a 80 m de una escuela con regla de 100 m devuelve OBSERVADA con cita") con precisión submétrica, verificado contra Postgres real de punta a punta en `tests/tools/test_evaluar_viabilidad_legal.py`.

### Hallazgo real: las reglas de la jurisdicción del lote se aplican a zonas de cualquier localidad dentro del radio (confirmado, no solo documentado)

Al testear `evaluar_riesgo` con radio 2000 m se encontró que la escuela de **colonia-vecina** también entra dentro del radio de búsqueda desde un punto en San Carlos Centro, y el chequeo de distancia se evalúa igual contra las reglas de San Carlos (la jurisdicción del lote), no las de colonia-vecina. Esto es exactamente lo que pide la skill ("Se aplican las reglas de la jurisdicción del lote" a zonas de localidades vecinas), pero causó que un primer test fallara (asumía una sola zona `tipo=="escuela"` en el resultado, cuando en realidad hay dos: la cercana, que no cumple, y la de colonia-vecina, que sí). Se corrigió el test para buscar la zona por distancia, no solo por tipo -- y queda como confirmación de que el comportamiento multi-jurisdicción funciona como se diseñó.

### `EvaluarRiesgoArgs.productos`: lista de nombres, no de `ProductoConBanda`

Documentado como cambio en `docs/matriz-parametros.md`: la Fase 1 había previsto que quien llama a `evaluar_riesgo` proveyera la banda toxicológica de cada producto. En la implementación, la tool resuelve cada producto contra el catálogo (mismo mecanismo que `validar_producto_registro`) y toma la banda del registro -- el operario de campo no suele saber la banda toxicológica de memoria, así que pedírsela como parámetro requerido no tenía sentido práctico.

### `evaluar_viabilidad_legal` no reinvoca las otras tools; llama los mismos servicios

Implementado tal como lo describe la skill ("Arquitectura"): `evaluar_viabilidad_legal_logica` no llama a `validar_producto_registro`/`evaluar_riesgo` como tools, sino que usa directamente `servicios/validacion_producto.py::resolver_y_validar_producto` (compartido con `validar_producto_registro`) y los mismos retrievers de `evaluar_riesgo`. Evita duplicar la lógica de resolución de producto entre las tres tools.

### Multi-producto en `evaluar_riesgo`/`evaluar_viabilidad_legal`: cada producto se evalúa por separado contra cada zona

No se colapsa a un "peor caso" por banda toxicológica: con una receta de 2+ productos, cada uno se evalúa contra cada zona con su propia banda, porque una regla puede aplicar a un producto y no a otro (ej. una regla específica de banda II no aplica a un producto banda IV en la misma receta). Es más conservador (nunca oculta una observación real) a costa de evaluar N×M combinaciones en vez de una sola; para las recetas típicas (1-2 productos, pocas zonas en radio) el costo es insignificante.

### Alcance no cubierto en esta fase

- Task 3.2 del plan original ("evaluar_riesgo... dosis del uso registrado") se cubre solo cuando el producto tiene `aplicacionesPorProducto` estructurado (`fuente=senasa_estructurado`); dosis extraídas de marbete (`fuente=marbete_extraido`, Fase 2 tarea 3) no se implementaron en esta sesión y por lo tanto no hay ninguna para probar el camino de comparación con esa fuente.
- No se implementó un mecanismo de reintento/paralelismo real para "producto y riesgo en paralelo" (la skill menciona "en paralelo" como optimización de latencia, no como requisito funcional); la implementación actual es secuencial. Documentado como posible optimización futura, no como bug.

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

### Canal web como alternativa a WhatsApp (Fase 11)

Después de cerrar la Fase 10 y cargar los insumos reales de un único municipio para empezar a probar, el usuario decidió que el canal WhatsApp (Fase 8) no era práctico para seguir iterando: el número de prueba de Meta admite hasta 5 destinatarios verificados y depende de un túnel HTTPS activo (cloudflared/ngrok) para cada sesión de prueba. Se agregó `canales/web/` como canal alternativo, sin tocar ni recortar el canal WhatsApp existente — queda documentado como implementación futura (`docs/setup-whatsapp.md`).

Diseño: reutiliza sin modificar `orquestador/turno.py::ejecutar_turno`, `orquestador/agente.py::crear_agente` (incluida la tool `leer_receta` ligada a imagen por clausura, ya resuelta en la Fase 8) y `ContadorRepreguntas`. Solo cambia el transporte, siguiendo el mismo patrón de separación protocolo/wiring que WhatsApp (`canal.py` recibe `procesar_mensaje` inyectado, como `webhook.py::crear_app`). Diferencia clave de protocolo: WhatsApp debe responder 200 de inmediato y procesar en background (regla de Meta); el navegador espera la respuesta en la misma request, así que no hace falta cola de background ni deduplicación por `message.id`.

Los botones y listas de WhatsApp nunca fueron elementos interactivos reales del lado del formateador (`orquestador/formateador.py` los renderiza como texto plano con patrones `[Opción]` y `   - opción`, ver skill "Formato de respuestas"); el canal web parsea esos mismos patrones en JavaScript para mostrarlos como chips clickeables, sin necesitar tocar el formateador ni el orquestador.

`thread_id` del canal web: `f"web:{session_id}"`, con `session_id` generado en el navegador (`crypto.randomUUID()`, persistido en `localStorage`) — evita colisión con los números de teléfono normalizados que usa WhatsApp como `thread_id` en el mismo checkpointer/Postgres.

### Ampliación del modelo `Receta`/`RecetaItem` a los campos reales del formulario (12/09/2026)

El usuario definió el conjunto real de campos de una receta agronómica argentina (formato completo, con datos personales/matrículas) y el subconjunto que este proyecto va a manejar, excluyendo datos personales y sensibles (productor, ingeniero agrónomo, matrículas, receta de venta -- esta última se consideró pero el usuario la descartó también por ser un dato de autorización, no de la aplicación en sí):

`numero_receta + cultivo + lote + superficie + (tipo_aplicacion) + (caudal) + ubic_poblado + condiciones + restricciones + observaciones + fecha_emision + validez_dias + 1{(plagas) + nombre_comercial + principio_activo + clase_toxicologica + dosis}n`

Se agregaron a `Receta`: `caudal`, `ubic_poblado`, `condiciones`, `restricciones`, `observaciones`, `fecha_emision`, `validez_dias`; a `RecetaItem`: `principio_activo`, `clase_toxicologica` (más `adversidad` por ítem, que ya existía). `numero` ya cubría `numero_receta`, `superficie_ha` ya cubría `superficie`.

**Criterio para qué bloquea y qué no:** el pedido original del usuario incluía la queja de que el sistema repreguntaba en vez de armar la receta con lo que pudo leer. Se separaron los campos en dos grupos:
- **Alimentan un chequeo legal más adelante** (`cultivo`, `lote`, `superficie_ha`, al menos un `producto`): siguen generando `CampoFaltante` si no se leen con confianza suficiente -- son los únicos que la skill necesita para el dictamen.
- **Descriptivos** (todo lo demás, incluido `tipo_aplicacion` -- que el propio usuario marcó como opcional entre paréntesis en su notación): se toman tal cual los devuelva el LLM, sin campo de confianza propio ni `CampoFaltante`. Si faltan, la `Receta` se arma igual y el hueco se ve en la plantilla de confirmación sin ⚠️ (reservado para los campos del primer grupo). `tipo_aplicacion` sigue siendo obligatorio más adelante para `evaluar_riesgo` (ver `docs/matriz-parametros.md`), pero eso lo repregunta esa tool en su momento, no `leer_receta`.

No se agregaron columnas nuevas a `operacion.receta`: todos los campos nuevos son semiestructurados/descriptivos según el criterio de la skill ("JSONB si es semiestructurado o variable"), así que viajan dentro de `datos_extraidos` (ya JSONB) vía `Receta.model_dump()`, sin migración. `guardar_receta_en_curso` (que persiste la receta en curso) no está conectado todavía al flujo real del orquestador -- sigue siendo así, sin cambios.

También se reforzó `orquestador/prompt_sistema.py` para dejar explícito que, después de `leer_receta`, la respuesta es `confirmacion_receta` con los datos parciales, nunca `repregunta` ni pedir la foto de nuevo -- encontrado como comportamiento inconsistente real (a veces el LLM repreguntaba igual pese a la regla ya existente), documentado en `DIFICULTADES.md`.

**Corrección posterior (mismo día):** `adversidad` había quedado sin querer en el grupo de campos bloqueantes de `leer_receta` (junto a cultivo/lote/superficie_ha) cuando en realidad el usuario la definió como opcional desde el principio (la plaga solo aparece entre paréntesis, a nivel de cada producto, en su notación) -- ni `evaluar_riesgo` ni `evaluar_viabilidad_legal` la exigen (`adversidad: str | None = None` en ambos), así que no tenía sentido que `leer_receta` sí la bloqueara. Se sacó del grupo bloqueante junto con `confianza_adversidad` (que ya no tiene uso, igual que se hizo con `tipo_aplicacion`).

### `consulta_producto`: sin intro del LLM ni sección *Fuentes* aparte

Probando el canal web, una consulta de banda toxicológica devolvía "Acá tenés el resultado de la consulta..." (intro genérica del LLM) seguido de una sección *Fuentes* que solo decía "SENASA, (vademécum)" — no aporta nada que no esté ya en la línea del producto (que siempre trae su propio n.° de registro). El usuario pidió una respuesta directa: banda y dosis, sin ese relleno.

Se sacó el intro del LLM para `consulta_producto` (se agregó a la lista de tipos que ya lo suprimían: `fuera_de_dominio`, `ayuda`, `error`) y se dejó de renderizar `_seccion_fuentes` en esa plantilla. Esto **no** afecta la trazabilidad real: la `Cita` sigue viajando en `ResultadoTool.citas` y quedando logueada en `operacion.turno` como siempre — solo cambia qué texto se le muestra al usuario en el chat, no lo que el sistema verifica o registra. No se tocó la plantilla de `dictamen` ni de `consulta_normativa`: ahí la sección *Fuentes* sí lleva información específica (norma + artículo) que no está repetida en ningún otro lado del mensaje, y es un requisito explícito de la skill ("toda afirmación sobre normativa o registro lleva su Cita").

De paso se agregó la dosis registrada a la rama de `validar_producto_registro` (consulta de un producto puntual), que hasta ahora no la mostraba (solo la mostraba la rama de `consultar_productos`, el listado).

### Excepción de cuota agotada del LLM: detección heurística por texto

No se pudo verificar contra documentación oficial el tipo exacto de excepción que levantan `google-genai` y `groq` ante un 429/cuota agotada. `src/fitosanitarios/llm/client.py` detecta el caso buscando "429", "RESOURCE_EXHAUSTED" o "RATE LIMIT" en el texto de la excepción, en vez de capturar una clase específica. **Verificar** antes de la Fase 2 (primera llamada real) y reemplazar por el tipo de excepción correcto si existe uno más específico.

### Se quita la validación por ubicación del lote: ahora se informa banda y distancia mínima por localidad

**Cambio de planes (19/09/2026).** El dictamen ya no compara la ubicación del lote (lat/lon) contra escuelas, cursos de agua y zona urbana para decir si la aplicación es válida en ese lote. En su lugar, con los datos de la receta contrastados con SENASA, el chatbot informa:
- la **banda toxicológica de la aplicación completa**: la más peligrosa entre los productos de la mezcla (Ia > Ib > II > III > IV), sin perder la banda propia de cada producto;
- según la **localidad o municipio** donde se aplica y el tipo de aplicación, la **distancia mínima** a cada tipo de zona (zona urbana, escuela, curso de agua) que fijan las reglas de esa localidad, provinciales y nacionales, con la más restrictiva citando todas las normas que aplican.

**Qué cambió.** `evaluar_riesgo` y `evaluar_viabilidad_legal` reciben `localidad` (texto) en vez de `lat`/`lon`. Nuevo `servicios/localidad.py` (resuelve el nombre contra las localidades cargadas, sin tildes ni mayúsculas; si es ambiguo devuelve opciones, nunca elige) y `servicios/condiciones_aplicacion.py` (banda de la aplicación + distancias mínimas, función pura). `Dictamen` suma `condiciones`; el formateador agrega la sección *Condiciones de aplicación*. Sin localidad, la tool devuelve `faltan_datos` con la lista de las cargadas; localidad no cargada, `JURISDICCION_NO_CUBIERTA` (el texto del motivo pasó de "el punto no cae en ningún polígono" a "la localidad no está entre las cargadas").

**Decisiones de criterio:**
- La distancia mínima **informa, no dictamina**: ya no hay ubicación contra la cual verificarla, así que no genera OBSERVADA ni bloquea APTA. Si la localidad no tiene regla para esa combinación de aplicación y banda, se advierte en vez de inventar un valor.
- Una **banda de producto desconocida sí deja el dictamen NO EVALUABLE**: sin ella, la banda de la aplicación (y por lo tanto la distancia) podría ser más restrictiva de lo informado. Ausencia de evidencia no es aprobación.
- La localidad la aporta el usuario o la receta en curso (el LLM la pasa como texto); `leer_receta` todavía no la extrae de la foto. Pendiente si se quiere leerla de la receta.

**Sin tocar a propósito (código que quedó sin uso, no borrado):** `servicios/geo.py` (punto en polígono y distancias), `localidades_candidatas_por_punto` / `zonas_protegidas_en_radio` en `datos/retrievers/territorio.py`, `evaluar_distancia_zona` en `servicios/reglas.py`, la carga de `zona_protegida` y `radio_busqueda_zonas_m`, `Receta.ubicacion_lat/lon`, y el botón de ubicación del canal web y el mensaje `location` de WhatsApp. Se dejan por si se retoma una capa SIG (ver evaluación de viabilidad de capas y mapa); limpiarlos es una tarea aparte.

**Verificación.** Los tests puros (localidad, condiciones, dictamen, formateador) corren. Los de integración de `evaluar_riesgo`, `evaluar_viabilidad_legal` y ruteo se reescribieron pero **no se pudieron correr** en esta sesión (Docker/Postgres no disponible: se saltan).

### Seguimiento del dictamen: respuesta concreta, "más info" y agendar la aplicación

**Cambio (19/09/2026).** La respuesta del dictamen se acorta: resultado, observaciones (si hay), y las *Condiciones de aplicación* con la **distancia mínima y la norma que la fija** en la misma línea ("- Distancia mínima a zona urbana: 3000 m (Ordenanza 841/2010, art. 7)"). Entre las reglas que aplican, la que fija el mínimo es la más restrictiva (`DistanciaMinima.norma_limitante`); las otras siguen citadas en *Fuentes*. Las citas de normativa se muestran legibles ("Ordenanza 841/2010") en vez del nombre del PDF. Cierra con una pregunta: "¿Querés más info (la banda de cada producto) o que agende la aplicación?". Un dictamen OBSERVADO solo ofrece la info, no agendar.

**Más info.** Si el usuario la pide, el LLM vuelve a llamar `evaluar_riesgo` con los mismos argumentos y responde `detalle_bandas`: banda de cada producto (con registro SENASA) y la de la aplicación (la más peligrosa). Se re-ejecuta la tool en vez de guardar el resultado anterior porque el formateador solo renderiza artifacts del turno actual (así el LLM no puede alterar números).

**Agendar (`agendar_aplicacion`, tipo `agendar_aplicacion`).** El flujo lo decide el código:
- "sí, agendala" (sin día) -> pregunta la fecha;
- "agendala para el martes" -> muestra la agenda de ese día y pregunta el horario;
- con fecha y hora -> agenda y confirma; si ya había algo a esa hora avisa, pero agenda igual.

Las fechas y horas las resuelve `servicios/fechas.py`, no el LLM (que no conoce la fecha actual con confiabilidad): el LLM pasa el texto tal cual ("martes", "mañana", "25/09", "8:30"). Un día de la semana es siempre el **próximo** (si hoy es martes, "el martes" es dentro de 7 días); no se agenda en el pasado. El resumen que ve el LLM incluye `fecha=AAAA-MM-DD` para que el turno del horario reutilice la fecha ya resuelta. `consultar_agenda` acepta el mismo texto y ahora muestra la hora de cada tarea.

**Persistencia.** La agenda reutiliza `operacion.receta` (`fecha_prevista` + nueva columna `hora_prevista TIME`): cada agendado inserta una receta en estado `evaluada` con los datos que el LLM copia de la conversación (cultivo, lote, número, superficie, tipo). **Hay que correr `003_operacion.sql` en las bases existentes** (agrega la columna con `ADD COLUMN IF NOT EXISTS`).

**Límites conocidos:** no hay cancelar ni reprogramar; no se valida horario laboral ni zona horaria (usa la del servidor); la receta agendada no sale de `guardar_receta_en_curso` (sigue sin conectarse al flujo del orquestador, como ya estaba documentado). El prompt ganó ~13 líneas (~1000 tokens en total, dentro del presupuesto de ~3k).

**Verificación.** Corren sin base: parseo de fechas/horas, flujo de la tool con dobles, plantillas del formateador. **No corrieron** los tests contra Postgres (`test_agendar_aplicacion_db`, ruteo) ni una conversación real con Gemini: falta probar que el LLM encadena bien "sí, agendala" -> fecha -> hora.

### Estructura de `data/insumos/`: municipios dentro de la carpeta de su provincia

**Cambio (19/09/2026).** La legislación de cada municipio pasa a vivir dentro de la carpeta de la provincia a la que pertenece, y la normativa provincial en esa misma carpeta:

```
data/insumos/
├── santa-fe/
│   ├── ley-11273-1995.pdf         normativa provincial (+ reglas.csv opcional)
│   └── el-trebol/                 municipio: localidad.geojson, ordenanza-*.pdf, reglas.csv
└── normativa-general/nacional/    sin cambios
```

Antes: `localidades/<localidad>/` y `normativa-general/provincial/<provincia>/`. La provincia de una localidad ahora es la carpeta que la contiene, así que se sacó el aviso A1 ("la provincia del límite no tiene carpeta en `provincial/`") y se agregó el error **F7**: la propiedad `provincia` del `limite` tiene que coincidir con esa carpeta. Una carpeta de provincia sin PDF de normativa provincial sigue siendo error F1, como antes.

**Qué cambió en el código.** Nuevo `insumos/estructura.py` (único lugar que sabe recorrer las carpetas), usado por el validador y los tres loaders. Las claves de `validar_insumos` pasan a `<provincia>/<localidad>`, `<provincia>` y `normativa-general/nacional`; `loader_geo` decide con `es_clave_de_localidad`. Las fixtures (`tests/fixtures/insumos/`) y los datos reales de El Trébol se movieron con la nueva estructura; el modelo de datos (`territorio.*`) no cambia.

**Decisión abierta:** la normativa nacional quedó en `normativa-general/nacional/` porque no se pidió moverla. Si se quiere, va a `data/insumos/nacional/` con un cambio de una línea en `estructura.py`.

**Verificación.** Corren sin base: validador (fixtures y casos F1–F7), chunking. Los tests de carga contra Postgres (`test_loaders_integracion`) se reescribieron pero no corrieron (sin Docker en esta sesión).

### Sin normativa municipal: respaldo en la provincial, aclarándolo

**Cambio (19/09/2026).** Si la localidad no tiene normativa municipal, `evaluar_riesgo`, `evaluar_viabilidad_legal` y `responder_consulta_normativa` se basan en la provincial (y nacional) y **lo aclaran en la respuesta** ("No se cuenta con la normativa municipal de X: la distancia se basa en la normativa provincial"). Dos casos:
- **Localidad cargada sin ordenanzas** (existe en `territorio.localidad` pero no tiene normas municipales): se detecta con `localidad_tiene_normativa_municipal` (existencia de normas municipales, no de reglas: una ordenanza que no fija distancia para terrestre no es "sin normativa"; en ese caso solo se avisa que no hay distancia cargada).
- **Localidad no cargada:** antes daba `JURISDICCION_NO_CUBIERTA`. Ahora, si se conoce la provincia (argumento nuevo `provincia`, o mencionada en el mismo texto, "Rosario, Santa Fe"), se usa su normativa provincial. **Nunca se supone la provincia**: si falta, la tool devuelve `faltan_datos` con la lista de provincias cargadas. `JURISDICCION_NO_CUBIERTA` queda para una provincia sin normativa cargada.

Implementación: `servicios/localidad.py::Ubicacion` y `tools/_localidad.py::resolver_ubicacion_o_cortar` (paso común de las tres tools); `CondicionesAplicacion.sin_normativa_municipal`; la plantilla de consulta normativa muestra la aclaración. Sin cambios en el modelo de datos.

**Límite conocido:** con las leyes provinciales reales de Santa Fe cargadas hoy (sin `reglas.csv`), la distancia para una localidad sin ordenanza sale "no hay una distancia mínima cargada" (además de la aclaración); las distancias provinciales solo se informan si hay reglas provinciales cargadas.

### Otros cambios de la misma sesión (19/09/2026)

- **Canal web:** se quitó el botón 📍 y los campos `lat`/`lon` (la ubicación del lote ya no se usa). El mensaje `location` del webhook de WhatsApp no se tocó.
- **Confirmación de receta:** vuelve a marcar "Tipo de aplicación: no figura ⚠️", porque ahora define la banda y la distancia que se informan.
- **`001_catalogo.sql`:** `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` para `matricula`, `caracteristicas` y `embedding` de `catalogo.vehiculo` (las bases existentes no los tenían); después correr `scripts/cargar_vehiculos.py`.
- Recetas de ejemplo de El Trébol renombradas (`01_apta_terrestre`, `02_apta_aerea_banda_ii`, `03_observada_dosis_fuera_de_rango`) con notas nuevas; `docs/testing-manual.md` y `docs/guion-demo.md` actualizados al flujo por localidad.

### Sin `reglas.csv`, las distancias se leen del PDF de la norma (de forma determinista)

**Cambio (19/09/2026).** `reglas.csv` pasa a ser opcional en cualquier carpeta (municipal, provincial, nacional). Si falta, `loader_reglas` lee las distancias del texto de los artículos de esa carpeta y las guarda en `territorio.regla_distancia` con `fuente='pdf_extraido'` (columna nueva; el CSV es `fuente='csv'`). Con CSV presente, el CSV es la única fuente de esa carpeta. Antes las leyes provinciales reales de Santa Fe (sin CSV) no aportaban ninguna distancia.

**Determinista, sin LLM.** Primero se hizo con un LLM (Gemini) y salió una regla dudosa (el art. 53 del decreto, que solo describe un trámite) y excepciones como reglas; además el resultado variaba entre corridas. Se reemplazó por un parser en código (`servicios/extraccion_reglas.py`): el mismo texto da siempre las mismas reglas, no necesita API key, corre en cualquier entorno (también con `USE_FIXTURES=true`) y se testea sin red.

**Qué acepta: solo prohibiciones firmes.** Una oración que prohíbe aplicar ("Prohíbese...", "queda prohibida...", "no se podrá aplicar...") y que tiene una única distancia (en metros o km; "quinientos ( 500 ) metros" cuenta una vez), una única zona (`zona_urbana`, `escuela`, `curso_agua`), un tipo de aplicación (terrestre, aérea, o todas si no lo dice) y clases toxicológicas explícitas (o ninguna, que vale para todas las bandas). Las clases se traducen con una tabla fija: A=Ia/Ib (roja), B=II (amarilla), C=III (azul), D=IV (verde), o por color.

**Qué descarta** (ante la duda, no se extrae): excepciones y permisos ("excepcionalmente podrán aplicarse...", "salvo", "cuando exista ordenanza que lo autorice", "previa...", "conforme a la reglamentación"), trámites y requisitos, oraciones sin prohibición, rangos ("entre 500 y 3.000 m"), más de una distancia o de un número en la oración, más de una zona, y clases que el parser no reconoce.

**En la respuesta:** la distancia lleva "⚠️ La distancia a zona urbana se leyó del texto de <norma, art. N> (la norma no tiene reglas.csv): verificala con la norma".

**Corrida real (122 artículos provinciales y nacionales cargados):** 2 reglas, y ningún falso positivo: Ley 11.273 art. 33 (aérea: clases A y B a 3.000 m de plantas urbanas) y art. 34 (terrestre: A y B a 500 m). Quedan afuera a propósito las excepciones de los mismos artículos (clases C y D a 500 m con ordenanza; la de la clase B entre 500 y 3.000 m) y el art. 53 del decreto reglamentario.

**Límites conocidos:** al descartar las excepciones no se extrae la prohibición *implícita* para las clases C y D en aérea (el artículo solo dice que "excepcionalmente" se puede dentro de 500 m con ordenanza): esa distancia solo aparece si se carga a mano en un `reglas.csv`. Solo entiende prosa: una distancia dada en una tabla o imagen no se lee. Un texto redactado de otra forma puede no reconocerse (se pierde la regla, nunca se inventa).

**Migración:** `002_territorio.sql` agrega `fuente` con `ADD COLUMN IF NOT EXISTS` (aplicar en bases existentes; ya aplicada en la del contenedor).

## Localidades de Santa Fe y estructura fija de respuestas (20/09/2026)

**Municipios y comunas.** El servicio opera solo en Santa Fe, así que ya no se pregunta la provincia. `territorio.municipio` (migración `004_municipios.sql`) guarda los 362 municipios y comunas (fuente: Georef, datos.gob.ar; `data/referencia/municipios-santa-fe.csv`, cargados con `insumos/loader_municipios.py`). Sin FK a `territorio.provincia`, que la carga de insumos borra y recrea. `resolver_ubicacion_o_cortar`: localidad con ordenanzas cargadas -> su normativa; municipio o comuna conocido sin ordenanzas -> normativa provincial, aclarándolo; nombre desconocido -> se vuelve a pedir ("No encontré 'X' entre las localidades de Santa Fe"), nunca se adivina; varios coincidentes -> se pregunta cuál. Una provincia distinta de las cargadas sigue siendo `JURISDICCION_NO_CUBIERTA`.

**Estructura fija de la repregunta.** Sin encabezado ni nombre de campo: una pregunta (o varias numeradas, hasta 3) que se entienda sola, seguida de sus opciones. Cada tool arma su pregunta con el dato concreto ("Hay varios productos parecidos a 'X'. ¿Cuál es?"), y el prompt pide preguntas de una oración y no repreguntar la adversidad. Los botones/lista interactivos de WhatsApp salen de esas mismas líneas (`cliente_graph.partir_opciones`).

## Un solo `reglas.csv` con prohibiciones (N) y reglas condicionales (S) (21/09/2026)

**Un archivo para todo.** `data/insumos/reglas.csv` reemplaza a los `reglas.csv` por carpeta. Columnas: `provincia, jurisdiccion, tipo_zona, tipo_aplicacion, banda_toxicologica, distancia_min_m, permitido, condiciones, norma, articulo, observaciones`. La jurisdicción de una fila sale de sus dos primeras columnas: municipal (`provincia` = carpeta de la provincia, `jurisdiccion` = carpeta de la localidad), provincial (`provincia` vacía, `jurisdiccion` = provincia) o nacional (`jurisdiccion` = `ARGENTINA` o `NACIONAL`). `norma` sigue siendo el nombre de un PDF, pero ahora se busca solo en la carpeta de esa jurisdicción (antes `_normas_de_carpeta` buscaba por nombre en toda la base, y dos localidades con un PDF del mismo nombre se pisaban). Código: `insumos/reglas_csv.py` (lectura y normalización, compartida por loader, validador y borrador), `estructura.alcance_de_carpeta`.

**`permitido`.** `N` es una prohibición: dentro de `distancia_min_m` no se puede, y es lo único que usan el dictamen y el agendado. `S` es una regla condicional: a partir de `distancia_min_m` se puede si se cumplen las `condiciones`; solo sirve para consultas y nunca bloquea ni ablanda una `N`. Así la excepción del art. 33 de la Ley 11.273 (clase B entre 500 y 3.000 m, con ordenanza y las condiciones del art. 51 del decreto) queda como una `N` de 3.000 m más una `S` de 500 m, en vez de un texto en `observaciones`. La migración `002_territorio.sql` agrega `permitido BOOLEAN NOT NULL DEFAULT false` y `condiciones TEXT` (con `ADD COLUMN IF NOT EXISTS`; **hay que aplicarla en las bases existentes**). `ReglaCandidata` trae ambos campos; `reglas_aplicables` descarta las `S` y `reglas_candidatas(..., permitido=True)` trae solo las `S`. `servicios/reglas.py::excepciones_aplicables` devuelve las `S` que habilitan aplicar a una distancia dada (para responder "¿puedo aplicar a 1.000 m bajo alguna condición?"). **Falta** la tool y la plantilla de respuesta que la usen: hoy el dato está cargado y el motor lo resuelve, pero el orquestador no lo consulta.

**Respaldo desde el PDF.** Una provincia o localidad sin filas en el CSV sigue leyendo sus distancias del PDF (siempre como `N`, `fuente='pdf_extraido'`). La normativa nacional **nunca** se lee del PDF: está para consultas, no para el dictamen, así que sin filas nacionales no aporta reglas (se evita además que una distancia mal leída de una ley nacional gane por ser la más restrictiva).

**Validación.** F5 ahora compara contra los PDF de la carpeta de la jurisdicción. Nuevos: F8 (fila con formato inválido o columna faltante) y F9 (jurisdicción sin carpeta). A4 (se leerá del PDF) pasa a ser por jurisdicción y no aplica a la nacional. `loader_reglas` valida todo el archivo y que cada jurisdicción tenga carpeta **antes** de tocar la base. Los valores se aceptan en mayúsculas o minúsculas y con `_` por `-`.

**Datos.** El CSV de Santa Fe y El Trébol se armó con las filas que ya estaban, más `S` para las excepciones del art. 33 (aérea, clases B y C/D) y para el art. 34 (terrestre C/D, "conforme a la reglamentación"). Dos decisiones de contenido a revisar: las `S` de C/D llevan `distancia_min_m = 0` porque la ley no fija un mínimo dentro de los 500 m (lo aclara `observaciones`); y la `S` terrestre de C/D cita el art. 34 de la Ley 11.273 con las condiciones de los arts. 40 y 53 del decreto (el art. 40 prohíbe C y D con equipos de arrastre o autopropulsados si hay centros de enseñanza, salud o recreativos en las inmediaciones). Un archivo suelto `data/insumos/argentina/reglas.csv` (otro esquema, con distancias que no salen de las leyes cargadas) no se usa y hay que sacarlo de `data/insumos/`.

## Consultas de normativa: `consultar_articulo` y `listar_limitaciones` (21/09/2026)

**Por qué dos tools nuevas.** `responder_consulta_normativa` (búsqueda por similitud + respuesta redactada por el LLM) no sirve para tres preguntas que el operario hace: "¿qué dice el artículo 33?" (el embedding de "artículo 33" no recupera ese artículo), "¿qué limitaciones hay en X?" (8 fragmentos por similitud dejan la lista incompleta) y "¿qué artículo dispone el límite?" (el formato Sí/No/Depende no cuadra). Las dos tools nuevas no usan embeddings ni redactan con el LLM: el LLM solo interpreta la pregunta (informal, con errores) y elige la tool y sus argumentos; el contenido sale de la base y lo arma el formateador. Tipos de respuesta nuevos: `consulta_articulo` y `limitaciones`. `responder_consulta_normativa` queda para dudas de contenido sin número.

**`consultar_articulo(numero_articulo, norma?, localidad?, provincia?)`.** Búsqueda exacta por número (`articulos_por_numero`), texto literal. `servicios/normas.py` entiende cómo lo escribe la gente ("art. 33", "33°", "5 bis") y a qué norma se refiere ("ley 11.273", "ordenanza 841/2010", "Ley 11273/1995 (santa-fe)": compara el número sin puntos ni ceros y, si se lo nombra, el tipo y el año). Sin localidad busca en la normativa provincial y nacional y lo avisa (si no se encuentra, "si es de una ordenanza, decime la localidad"). Si el número está en varias normas pregunta cuál (lista), no elige. **Los números de artículo se repiten dentro de una misma norma** (los PDF traen anexos con numeración propia: en la Ley 11.273 el 13 y el 28, en el decreto el 1, 2, 3… varias veces), así que devuelve todos los textos con ese número ("texto 1 de 2") en lugar de elegir uno. El texto se limpia (líneas cortadas del PDF, símbolo suelto al principio, un renglón por inciso). `partir_por_seccion` ahora también parte un bloque que solo supera los 4096 caracteres (hay artículos de 5000): por oraciones, y por palabras en último caso.

**`listar_limitaciones(localidad, tipo_aplicacion?, banda?, tipo_zona?, distancia_m?)`.** Lee las reglas de `reglas.csv` (`reglas_candidatas`, `N` y `S`), no busca por similitud: la lista es completa y cada línea cita norma y artículo. Filtros tolerantes ("con avión", "roja", "un arroyo"); un filtro que no se entiende se ignora y se avisa. Con `distancia_m` responde qué prohibición alcanza a esa distancia y qué excepciones (`S`) permitirían aplicar (`servicios/limitaciones.py::restricciones_a_distancia`, sobre `excepciones_aplicables`). **Una excepción no levanta la prohibición de una norma más local:** la excepción de la ley provincial ("por ordenanza") no aplica contra la Ordenanza 841/2010 de El Trébol, que prohíbe; en cambio una ordenanza sí puede autorizar lo que prohíbe la ley provincial. Es una regla de precedencia que salió de leer las normas, no del CSV: si más adelante hay excepciones municipales, esa regla decide cuáles se ofrecen.

**Nombres de norma.** La ley 055297/2017 se muestra como "Ley 055297/2017" porque así se llama el PDF (`ley-055297-2017.pdf`, aunque es el decreto reglamentario 552/97); un usuario que escriba "decreto 552/97" no la encuentra por nombre (sí por "ley 55297" o por número de artículo). Conviene renombrar el PDF con su tipo real cuando se cargue la normativa nacional.

**Pendiente.** Las tools están probadas con dobles de los accesos a datos y con un agente simulado (`tests/orquestador/test_ruteo_consultas_normativa.py`), no contra Postgres ni con Gemini: falta probar con frases mal escritas de verdad (la interpretación es del LLM) y contra la base cargada. La respuesta de limitaciones lista todas las reglas de la jurisdicción sin colapsar las que se pisan (una ordenanza más estricta y la ley provincial figuran las dos, cada una con su cita).

## Estructura de `tools/`: una carpeta por tool (21/09/2026)

**Convención.** Cada tool es una carpeta de `src/fitosanitarios/tools/`:

```
tools/<tool>/
    __init__.py   exporta la tool, sus argumentos y su lógica
    tool.py       el script base: argumentos, lógica y la tool de LangChain
    prompts.py    lo que lee un LLM: la descripción de la tool (`DESCRIPCION`) y, si los tiene, sus prompts
    mensajes.py   lo que lee el operario: preguntas, avisos y la plantilla de la respuesta
    utils.py      los auxiliares que solo usa esta tool (si los tiene)
```

Lo que usan varias tools sale de `tools/` y va a `servicios/`; **una tool no importa de otra**. `tests/tools/test_estructura.py` verifica la convención (archivos, que la descripción que ve el LLM sea la de `prompts.py`, que no haya scripts sueltos en `tools/` ni imports entre tools). Los tests siguen la misma forma: `tests/tools/<tool>/test_tool.py` y `test_utils.py`.

**Qué se movió y de dónde.**

| Antes | Ahora |
|---|---|
| `tools/_recursos.py` | `servicios/recursos.py` |
| `tools/_localidad.py` | `servicios/ubicacion.py` |
| `thread_id_de_config` (estaba en `tools/registrar_evento.py`, la usaban 3 tools) | `servicios/conversacion.py` |
| helpers de formato privados de `orquestador/formateador.py` (`_num`, `_cita_norma`, `_seccion_fuentes`, `_bloque_condiciones`, `_lineas_agenda`…) | `servicios/formato.py` (los usan las plantillas de varias tools) |
| vehículo no identificado (lo armaban `resolver_vehiculo` y `registrar_evento`) | `servicios/resolucion_vehiculo.py::faltante_vehiculo_no_identificado` |
| `servicios/extraccion_receta.py` | `tools/leer_receta/utils.py` (el prompt de extracción, a `prompts.py`) |
| `servicios/rag_normativa.py` | `tools/responder_consulta_normativa/utils.py` (los prompts, a `prompts.py`) |
| `servicios/agendamiento.py` | `tools/agendar_aplicacion/utils.py` |
| `servicios/limitaciones.py` | `tools/listar_limitaciones/utils.py` |
| `servicios/normas.py` | `tools/consultar_articulo/utils.py` (`norma_legible`, que también usan las plantillas, a `servicios/formato.py`) |
| `_BANDAS_HASTA` de `tools/consultar_productos.py` | `tools/consultar_productos/utils.py` |

Se quedan en `servicios/` porque los usan varias tools: `eventos`, `fechas`, `resolucion_vehiculo`, `validacion_producto`, `condiciones_aplicacion`, `dictamen`, `dosis`, `matching`, `reglas`, `localidad`.

**Prompts y mensajes aparte.** La descripción de cada tool (lo que el orquestador lee para decidir cuándo usarla y cómo completar sus argumentos) era el docstring de la función; ahora es `DESCRIPCION` en `prompts.py` y el decorador la recibe con `description=`. Se comprobó, contra el commit anterior, que las 13 tools (incluida la variante de `leer_receta` con la imagen ligada) mantienen **la misma descripción y el mismo esquema de argumentos**. Los textos que la tool le dice al operario (preguntas de repregunta, motivos, avisos) están en `mensajes.py` como constantes o funciones; también su **plantilla de respuesta**, cuando el tipo de respuesta es de una sola tool (`plantilla_<tipo>`).

**Plantillas de tipos con más de una tool.** `orquestador/formateador.py` quedó como registro (`_PLANTILLAS`): reúne las plantillas de cada tool y conserva las comunes (repregunta, fuera de dominio, no resuelto, ayuda, error) y el corte de mensajes largos. `dictamen` lo arma `evaluar_viabilidad_legal` cuando hay veredicto y `evaluar_riesgo` cuando no (un riesgo suelto); `consulta_producto` lo arma `consultar_productos` (listado) o `validar_producto_registro` (producto puntual), según la forma del resultado. Los seguimientos ("¿querés más info…?") y el bloque de condiciones de aplicación, que comparten `dictamen` y `detalle_bandas`, están en `servicios/formato.py`.

**Rutas viejas en este archivo.** Las entradas anteriores de `DECISIONES.md` citan las rutas de entonces (`tools/leer_receta.py`, `servicios/rag_normativa.py`…); se dejaron tal cual como registro histórico y esta tabla dice dónde está cada cosa hoy.

**Sin cambio de comportamiento.** Es un movimiento de código: los tests de plantillas (`test_formateador.py`) y de las tools pasan sin cambiar sus expectativas, y la suite completa corre en verde contra Postgres.


## Evaluación conversacional: simulador, invariantes y analista (21/09/2026)

**Qué es.** Una extensión (Fase 12 en `plandefases.md`, ver `evals/README.md`) que conversa con el bot como lo haría un usuario y analiza el resultado. Vive en `evals/` y no en `tests/` porque usa Gemini real (red y cuota).

**Decisiones.** (1) El simulador es un **subagente de Claude Code** y el orquestador del bot sigue siendo Gemini real: la prueba es realista y el simulador no comparte modelo ni contexto con el sistema. Consume la cuota de Claude además de la de Gemini. (2) El harness entra por el mismo camino que el canal de WhatsApp (`ejecutar_turno` con el agente real, el checkpointer de Postgres, `conn_log` y el mismo criterio de botones y listas de `cliente_graph`), sin firma ni Meta; un turno por proceso, así que el contador de repreguntas se persiste en un archivo por conversación (en producción vive en la memoria del servidor). (3) Las corridas usan un **clon de la base** (`<base>_eval`) y el harness se niega a correr contra otra: agendar y registrar eventos escriben. (4) Los artefactos de las tools (`ResultadoTool`) no sobreviven al checkpoint de Postgres: se toman de lo que devuelve `invoke`, como hace producción. (5) Un turno que falla por cuota o red se registra como `infra` y no cuenta como error del bot. (6) Único cambio en código de producción: `crear_modelo_chat_gemini(settings, temperature=None, indice_key=0)`, con el comportamiento por defecto intacto.

**Límites conocidos.** `gemini-3.5-flash-lite` ignora la temperatura pedida (aviso de `langchain-google-genai`): las repeticiones varían. La independencia del simulador (no leer el repositorio) es una regla de su definición, no una restricción técnica. Los agentes de `.claude/agents/` se registran al iniciar Claude Code. "Objetivo logrado" es lo que declara el simulador y no verifica el contenido: en el piloto declaró logrado en las 6 conversaciones y el analista encontró dos hallazgos críticos, así que **esa métrica no alcanza sola**.

**Lo que el piloto encontró que las pruebas anteriores no veían** (`evals/runs/20260921-192037/informe.md`): la consulta de un producto muestra la dosis del primer uso registrado aunque sea de otro cultivo; una receta de foto se evaluó sin que el usuario la confirmara; un mensaje con dos pedidos se contestó a medias; y las tools de producto y riesgo tardan 30 a 60 s por turno.

### Menos tokens por turno: qué se le saca a Gemini (21/09/2026)

**Medición** (piloto de Fase 12, 30 turnos). Cada llamada a Gemini reenvía ~5.300 tokens fijos: esquemas de las 12 tools (~3.500), prompt (~1.300) y `RespuestaAgente` (~300); lo que suma cada turno (historial, resultados de tools de una línea) es marginal. Un turno con una tool hacía **dos** llamadas (invocar la tool y elegir el `tipo` de la respuesta), unos 11.000 a 12.000 tokens; uno de 5 llamadas en bucle llegó a 32.500. En 20 de 20 turnos con tools el `tipo` que eligió Gemini coincidía con lo que determinaba la tool, y `intro` se escribía en 28 de 30 turnos pero solo se mostraba en 7.

**Aplicado, en este orden:**
1. **Descripciones de las tools y prompt más cortos** (`tools/*/prompts.py`, `prompt_sistema.py`, sin `intro`): una llamada sin tools pasó de 5.296 a 4.408 tokens de entrada (−17%, medido contra la API). Se sacaron los ejemplos de frases que repetían el prompt y se dejó lo que separa una tool de otra. Se verificó con `evals/consultas_normativa.jsonl` (Gemini real): el primer recorte rompió `art_05` porque se había sacado el ejemplo "¿qué artículo dispone el límite?" de `listar_limitaciones`; restituido, pasan los 27 casos.
2. **Tope de 4 llamadas a tools por turno** (`ToolCallLimitMiddleware`, `agente.py::LIMITE_TOOLS_POR_TURNO`). Pasado el tope, las llamadas reciben un aviso y no se ejecutan.
3. **Turnos que terminan en la tool** (`return_direct=True`, `orquestador/respuesta_directa.py`): 10 de las 12 tools cortan el turno y el `tipo` se infiere de la tool y su resultado (pide un dato: `repregunta`; no se resolvió: `no_resuelto`; `agendar_aplicacion` conserva el suyo porque su plantilla muestra la agenda). Un turno con tool pasa de dos llamadas a una: de ~10.600 a ~4.400 tokens (−58%) y una petición menos contra el límite de la API gratuita. `evaluar_riesgo` (dictamen o detalle de bandas según lo que se venga hablando) y `resolver_vehiculo` (alimenta a otra tool) siguen pasando por el modelo. Si una tool rechaza los argumentos (validación) antes de devolver algo, `ejecutar_turno` vuelve a invocar al agente una vez para que el modelo vea el error y decida, como antes. Un test exige que `return_direct` de cada tool y `TIPO_POR_TOOL` coincidan.
4. **Se quitó `intro` de `RespuestaAgente`**: el formateador ya la ignoraba en la mayoría de los tipos y ahora no hay segunda llamada en la que escribirla. Prompt y tests ajustados. La skill y el plan de fases conservan el campo porque son la especificación original.

**Efecto sobre el historial:** como el turno termina en la tool, el historial que ve Gemini en el turno siguiente no tiene una respuesta suya después del resultado de la tool; solo queda la llamada y su resumen de una línea (`resumen_para_llm`), que hoy lleva lo que hace falta (datos de la receta, fecha resuelta, veredicto).

**No se hizo:** filtrar las tools por mensaje (un enrutador extra ahorraría menos que lo anterior) y podar el historial (solo importa pasados ~15 turnos).

**Al medir con `evals.chat --replay`** los tokens de entrada de un replay incluyen el historial que ya dejaron replays anteriores del mismo escenario (reutilizan el thread): para comparar costos usar una sola llamada, no un replay repetido.


## Localidades y normas sin fuente oficial: Sastre y San Jorge (22/09/2026)

**Motivación.** El usuario investigó y cargó en `reglas.csv` las limitaciones de Sastre y Ortiz (Fallo judicial 2020, confirmado por la Corte Suprema de Santa Fe en 2023, más la Ordenanza municipal 1174/19) y de San Jorge (Fallo judicial 2009), ninguna con PDF oficial disponible: son fallos judiciales (sin repositorio público) y, para Sastre, una ordenanza conocida solo por una nota de prensa (Infosastre), sin número de artículo ni texto verificado. El pipeline existente exigía `localidad.geojson` (`territorio.localidad.limite` era `NOT NULL`) y una norma respaldada por un PDF con `tipo ∈ {ordenanza, decreto, resolucion, ley}`: ninguna de las dos cosas existía para estas dos localidades.

**Decisión (confirmada explícitamente por el usuario, dos preguntas separadas):**
1. `localidad.geojson` pasa a ser **opcional**: se relajó el schema (`territorio.localidad.limite` y el bbox, `NULL` permitido) en vez de fabricar una geometría de relleno. El dictamen ya no compara la ubicación del lote contra geometría (Fase 12), así que lo único que se pierde es la resolución de jurisdicción por punto-en-polígono (`servicios/geo.py::resolver_jurisdiccion`), que ya no está en uso por ninguna tool (código muerto, no se tocó).
2. Se agregó `fallo` como `tipo` de norma reconocido, **y se generalizó a cualquier tipo**: una norma sin PDF oficial se carga desde un `.md` con el mismo nombre (`<tipo>-<numero>-<anio>.md`), tal cual, sin OCR ni chunking en artículos (no tiene encabezados "Artículo N" reales, y no se los inventa). Esto también cubre la Ordenanza 1174/19 de Sastre (`tipo=ordenanza`, sin PDF), no solo los fallos judiciales -- la pregunta al usuario solo mencionaba `fallo`, pero limitar la excepción a ese tipo habría dejado sin cargar la ordenanza, que es la otra mitad de los datos de Sastre.

**Qué cambió en código:**
- `datos/migraciones/005_normas_sin_fuente_oficial.sql`: `territorio.localidad.limite`/bbox nullable; `territorio.norma.tipo` admite `fallo`.
- `insumos/loader_geo.py`: `cargar_localidad_sin_geometria` (nueva) inserta la localidad con `limite=NULL`; el nombre sale de `territorio.municipio` si coincide con la carpeta, si no del nombre de la carpeta capitalizado.
- `insumos/loader_normativa.py`: `_PATRON_NOMBRE_NORMA` acepta `.md` y el tipo `numero` con guiones (`san-jorge`, no solo dígitos); un `.md` se lee tal cual (`_texto_de_norma`) y **no se chunkea** -- por eso estas normas no aparecen en `consultar_articulo` ni en `responder_consulta_normativa` (RAG), solo en `listar_limitaciones`/el dictamen vía `reglas.csv`.
- `insumos/validador.py`: `localidad.geojson` ausente pasa de error (F1) a aviso (A5); F1 ahora pide "al menos un PDF o `.md`"; `NOMBRE_NORMA_VALIDO` (ex `NOMBRE_PDF_VALIDO`) acepta `fallo` y guiones en el identificador.
- `servicios/formato.py::norma_legible` y `tools/consultar_articulo/utils.py` reconocen `fallo` y nombres con guiones (`fallo-san-jorge-2009` → "Fallo San Jorge/2009").
- `servicios/reglas.py::DISTANCIA_SIN_LIMITE_M` (99999): convención para "prohibido en toda la jurisdicción, sin distancia máxima" (banda roja en Sastre, ordenanza 1174/19) -- el modelo no tenía un valor "infinito". `listar_limitaciones/mensajes.py` lo muestra como "no se puede aplicar en toda la jurisdicción", no como "a menos de 99999 m".
- `data/insumos/santa-fe/{sastre,san-jorge}/`: carpetas nuevas (antes los `.md` estaban sueltos en `santa-fe/`), con los `.md` de fuente y las filas correspondientes en `reglas.csv`.

**Riesgos y límites conocidos, sin resolver:**
- **Todo sale de fuente secundaria** (notas de prensa, no el texto oficial de sentencias ni de la ordenanza): número de artículo, fechas exactas y el mapeo "ligeramente/moderadamente peligroso" → banda III/II son inferencias del usuario, marcadas como tales en los `.md` y en `observaciones` de `reglas.csv`, pero **el dictamen las trata igual que a la Ley 11.273** (no hay un nivel de confianza en el modelo de datos).
- **El fallo de San Jorge (2009) resolvió un caso puntual** (barrio Urquiza contra campos linderos), no hay ordenanza municipal que lo generalice; el propio `.md` dice que no es automático asumir que rige para cualquier aplicación en cualquier punto de San Jorge. Se cargó igual como prohibición `N` de alcance municipal porque es "el único criterio disponible a falta de otra norma" (decisión del usuario), pero el sistema no distingue "alcance general" de "alcance de un caso": queda como deuda conocida.
- **Sin RAG:** `consultar_articulo` y `responder_consulta_normativa` no citan estos `.md` (no se chunkean/embeben); solo `listar_limitaciones` y el dictamen los usan, vía `reglas.csv`.
- **Migración 005 sin aplicar en la base de desarrollo al escribir esto** (ver nota de todas las migraciones de este archivo: no hay Alembic, se aplica a mano con `psql`).

**Verificación.** Suite completa (651 tests, sin los de integración contra Postgres) en verde. Tests nuevos: `tests/insumos/test_validador.py` (A5, F1 sin PDF ni `.md`, F6 con localidad de varias palabras), `tests/insumos/test_loaders_integracion.py::test_localidad_sin_geojson_se_carga_con_norma_sin_pdf` (localidad sintética propia, no toca las fixtures compartidas), `tests/servicios/test_formato.py`, `tests/tools/listar_limitaciones/test_mensajes.py`.
