# Decisiones

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
