# Dificultades

Registro de qué falló y cómo se resolvió. Una entrada por dificultad relevante, en orden cronológico (más reciente arriba).

## RAG de equipos y test end-to-end con avión (post-Fase 11)

### Armar el test de agenda mostró que ninguna receta puede llegar a tener `fecha_prevista` fuera de un test

Al escribir `scripts/demo_avion_agenda.py` para probar `consultar_agenda` con una receta real cargada por `leer_receta`, se encontró que no hay ningún camino de producción para que `operacion.receta.fecha_prevista` quede seteada: `orquestador/estado.py::guardar_receta_en_curso` (la única función que persiste una receta en curso) no incluía esa columna en su `INSERT`/`UPDATE` -- ni siquiera estaba en la lista de parámetros. Los únicos lugares del repo que la setean son tests de `tools/test_consultar_agenda.py` y `servicios/test_eventos.py`, insertando la fila directo por SQL. Como además `guardar_receta_en_curso` no está conectada al flujo real del orquestador (limitación ya documentada desde la Fase 0), esto significa que `consultar_agenda` nunca podía mostrar nada fuera de un test, ni siquiera si se le hubiera dado un avión o cualquier otro vehículo. Corregido agregando `fecha_prevista` a `guardar_receta_en_curso` (cambio mínimo, retrocompatible, ver DECISIONES.md); el script de demo la llama directo para simular ese paso, ya que conectarla al flujo conversacional completo es una tarea más grande, fuera del pedido puntual de esta sesión.

## Prueba end-to-end con El Trébol (post-Fase 11, cambio de app de Meta): hallazgos encadenados

### 1. Insumos de El Trébol no coincidían con el contrato: hubiera fallado con un `StopIteration` sin mensaje claro

Antes de cargar nada se corrió `validador.py` contra `data/insumos` (nunca se había corrido contra estos archivos reales) y confirmó 2 errores explícitos (`localidad.geojson` faltante -- el archivo se llamaba `el-trebol.geojson` -- y `reglas.csv` faltante) más un problema que el validador no detecta: el feature `limite` no tenía la propiedad `tipo`, que es justo lo que busca `loader_geo.py::cargar_localidad` con `next(f for f in ... if tipo == "limite")` -- sin chequear antes, correr el loader directo hubiera fallado con un `StopIteration` sin mensaje útil. Se corrigieron los tres problemas de formato (renombrar el archivo, completar propiedades, reorganizar la carpeta provincial) antes de cargar, ver DECISIONES.md.

### 2. La consulta normativa devolvía "no resuelto" para todo: `RAG_UMBRAL_SIMILITUD` real (0,75) nunca se superaba

Al probar `responder_consulta_normativa_logica` contra El Trébol con Gemini real, el resultado fue `no_resuelto` para una pregunta cuya respuesta sí estaba en la normativa cargada. Se aisló consultando `articulos_por_similitud` directo: el artículo correcto (art. 7, distancia aérea) scoreaba 0,51 -- muy por debajo del `RAG_UMBRAL_SIMILITUD=0,75` que tenía el `.env` real de esta máquina. Se confirmó que no era específico de El Trébol repitiendo la prueba contra `san-carlos-centro` (datos de fixtures, se suponía que "andan"): el mejor score ahí fue 0,63, también por debajo de 0,75. La consulta normativa nunca funcionó contra datos reales con ese umbral, para ninguna localidad -- simplemente nunca se había ejercitado con Gemini + embeddings reales después de la Fase 6 (que ya había documentado 0,35 como valor correcto, pero el `.env` real había drifteado a 0,75 sin que quedara registrado cuándo ni por qué). Bajado a 0,5, ver DECISIONES.md.

### 3. Con el umbral corregido, seguía devolviendo "no resuelto" pese a que Gemini contestaba bien: bug de formato en la cita

Con el umbral en 0,5 la pregunta sobre distancia aérea seguía devolviendo `no_resuelto`. Se aisló llamando directo a `responder_con_fragmentos` (sin pasar por la tool completa) para ver la respuesta cruda del LLM: Gemini había respondido correctamente, citando `{"norma": "ordenanza-841-2010", "articulo": "art. 7"}` -- con el prefijo "art." incluido, que es justo el formato con el que `_armar_contexto` le muestra cada fragmento (`"[archivo, art. {numero}, ...]"`). El matching de citas es una comparación exacta `(norma, numero)`, así que `"art. 7"` nunca calzaba contra `"7"` -- la cita se descartaba siempre y la tool devolvía `no_resuelto` como si el LLM no hubiera encontrado nada, aunque internamente sí lo había hecho. No apareció en los tests existentes porque usan un LLM fake que no reproduce el estilo de respuesta de Gemini real. Corregido normalizando el número de artículo (solo dígitos) antes de comparar en ambos lados, ver DECISIONES.md.

### 4. Al generar recetas de ejemplo lejos del pueblo, `evaluar_viabilidad_legal` dio `JURISDICCION_NO_CUBIERTA` para los 3 casos -- el polígono cargado es la mancha urbana, no el partido

Para armar las 3 recetas de ejemplo se probaron contra `evaluar_viabilidad_legal_logica` con puntos a ~300 m y ~6 km del límite urbano de El Trébol (ver DECISIONES.md) -- exactamente donde estaría un lote real, ya que dentro de la mancha urbana no se hacen aplicaciones fitosanitarias. Los 3 casos devolvieron `no_resuelto` / `JURISDICCION_NO_CUBIERTA`, incluido el punto a 6 km. Causa: el único polígono cargado como `limite` de la jurisdicción `el-trebol` es la delimitación urbana de INDEC (capa "Localidad", pensada para censo -- la mancha edificada del pueblo, de unos pocos km de diámetro), no el partido/municipio (la unidad administrativa real, que abarca el campo circundante donde efectivamente están los lotes). `resolver_jurisdiccion` exige que el punto caiga dentro de algún `limite` cargado -- y ningún punto en zona rural cae dentro de la mancha urbana por definición.

**No resuelto en esta sesión.** No se generó un polígono de partido a ojo (sería geometría inventada, contra el principio de no fabricar datos geográficos/normativos). Con los datos actuales, `evaluar_riesgo`/`evaluar_viabilidad_legal` para El Trébol solo puede evaluarse para lotes que, por algún motivo, cayeran dentro de la mancha urbana misma -- que es precisamente donde la Ordenanza 841/2010 prohíbe aplicar (arts. 2/3). En la práctica, ningún caso de uso real de "aplicación fitosanitaria en El Trébol" pasa hoy el chequeo de jurisdicción. Las 3 recetas de ejemplo (`data/recetas_ejemplo/`) quedan generadas con la explicación de este bloqueo en `notas.txt`, pensadas para probarse en cuanto se cargue el polígono correcto (capa de partido/municipio de INDEC o Santa Fe, no la de "Localidad"). `responder_consulta_normativa` no tiene este problema porque no depende de punto-en-polígono, solo de `jurisdiccion_id` explícito.

**Resuelto el 19/09/2026 por cambio de diseño:** el sistema dejó de usar la ubicación (lat/lon) del lote. La localidad se indica por nombre y la respuesta informa la banda y la distancia mínima según la normativa de esa localidad, así que el polígono urbano de INDEC ya no es un problema (ver DECISIONES.md, "Se quita la validación por ubicación del lote"). Si la localidad no tiene normativa municipal, se usa la provincial y se aclara.

### 5. Correr la suite completa borra El Trébol entero de la base: `tests/insumos/test_loaders_integracion.py` hace un `DELETE` total de `territorio.*`

Al correr `pytest -q` completo (345 tests) después de cargar los insumos de El Trébol, fallaron 2 tests (`tests/datos/test_retrievers_normativa.py::test_articulos_incluye_normativa_provincial` y `tests/datos/test_retrievers_territorio.py::test_reglas_candidatas_de_san_carlos_incluye_la_ordenanza`, ambos esperando `ley-13740-2017`). Investigado a fondo: la causa no es solo que la carpeta provincial `santa-fe` sea compartida entre `data/insumos/` (real) y `tests/fixtures/insumos/` (sintética) -- es que la fixture `conexion` de `tests/insumos/test_loaders_integracion.py` hace, en su setup, un `DELETE` **sin condición** de `territorio.regla_distancia`, `articulo`, `norma`, `zona_protegida`, `localidad` y `provincia` completos (no solo de la localidad que va a recargar), documentado tal cual en el docstring del archivo ("hace un DELETE completo de `territorio.*` y recarga desde las fixtures"). Confirmado con una consulta directa después de la corrida: `territorio.localidad` quedó con solo `colonia-vecina` y `san-carlos-centro` -- **El Trébol desapareció por completo** (localidad, zona `zona_urbana`, las 2 reglas de distancia y la Ordenanza 841/2010), no solo la ley provincial.

Es la misma causa de fondo que ya documenta la Fase 6 (los tests de integración de insumos comparten `DATABASE_URL` con la base de desarrollo manual, sin aislamiento) pero con un impacto mucho mayor del que parecía al principio: **cualquier corrida de la suite completa borra los datos reales de El Trébol**, no solo la normativa provincial. Se restauró recargando los 3 loaders contra `data/insumos` después de la corrida (ver más abajo el estado final verificado). **No resuelto de fondo**: mientras `tests/insumos/test_loaders_integracion.py` siga apuntando a `DATABASE_URL` con un `DELETE` total de `territorio.*`, cada `pytest -q` completo va a requerir recargar El Trébol a mano después. La solución de fondo sigue pendiente desde la Fase 6: una base de datos de test aislada (`TEST_DATABASE_URL` o un schema/DB separado).

## Prueba manual de WhatsApp real con token temporal (post-Fase 11): túnel HTTPS y warning pendiente de LangGraph

### DNS local no resolvía `trycloudflare.com` (bloqueo del router, no de la app)

Al levantar `cloudflared tunnel --url http://localhost:8000` para probar el canal WhatsApp real, falló con `dial tcp: lookup api.trycloudflare.com: no such host`. No era un problema de la app ni de Meta: el DNS del router (`192.168.100.1`, usado por la interfaz Wi-Fi) devolvía `NXDOMAIN` para `trycloudflare.com` mientras que Google DNS (8.8.8.8) lo resolvía sin problema -- consistente con un filtro de seguridad del router/ISP que bloquea dominios de túneles dinámicos conocidos. Se resolvió cambiando el DNS de la interfaz Wi-Fi a 8.8.8.8/1.1.1.1 (IPv4) y 2001:4860:4860::8888/2606:4700:4700::1111 (IPv6) -- Windows seguía usando el DNS IPv6 del router (`fe80::1`) aunque el IPv4 ya estaba cambiado, así que hubo que corregir los dos. El cambio requiere permisos de administrador (`Set-DnsClientServerAddress` falla con "El cliente no tenía acceso disponible a un recurso CIM" sin elevar), así que lo hizo el usuario manualmente por la GUI de Windows, no la sesión de Claude Code.

### Webhook verificado pero sin mensajes: falta suscribir el campo `messages`

Después de verificar la URL del webhook (Meta respondió `200 OK` al handshake `GET`, confirmado en el log del servidor), mandar "Hola" desde el número de prueba no generaba ningún `POST /webhook` -- el mensaje nunca llegaba. Causa: faltaba suscribir el campo `messages` de la cuenta de WhatsApp Business, que en el dashboard de Meta está en una sección separada ("Webhooks" a nivel de toda la app, seleccionando el objeto "Cuenta de WhatsApp Business"), no en la pantalla "WhatsApp > Configuración" donde se carga la URL y el verify token -- y en algunos casos esa sección de suscripción de campos solo aparece habilitada después de que la verificación de la URL fue exitosa. Una vez suscripto, el flujo completo funcionó de punta a punta (confirmado con filas reales en `operacion.turno`).

### Pendiente: warning de LangGraph por tipo no registrado en el checkpoint

Con el flujo ya funcionando, el log mostró:

```
Deserializing unregistered type fitosanitarios.dominio.modelos.RespuestaAgente from checkpoint. This will be blocked in a future version. Set LANGGRAPH_STRICT_MSGPACK=true to block now, or add to allowed_msgpack_modules to allow explicitly: [('fitosanitarios.dominio.modelos', 'RespuestaAgente')]
```

No rompe nada hoy (es solo un warning), pero `langgraph` avisa que una versión futura va a bloquear la deserialización automática de tipos custom desde el checkpointer de Postgres si no están explícitamente permitidos. Si se actualiza `langgraph` más adelante y el checkpointer deja de recuperar el historial de conversación (o tira un error de deserialización), es por esto. **Pendiente:** registrar `('fitosanitarios.dominio.modelos', 'RespuestaAgente')` en `allowed_msgpack_modules` al crear el `PostgresSaver` (`orquestador/agente.py::checkpointer_postgres`), o setear `LANGGRAPH_STRICT_MSGPACK=true` y confirmar que sigue andando -- no se aplicó todavía, solo queda anotado para no perderlo de vista antes de la entrega.

## Orquestador: a veces repregunta por la foto en vez de confirmar la receta parcial

Probando el canal web, en algún turno la respuesta fue "Por favor, enviá la foto de la receta fitosanitaria para que pueda leerla" seguido de un mensaje genérico de repregunta sin datos ("no pude identificar cuál"), en vez de la confirmación con lo que sí se pudo leer. La regla ya estaba en `orquestador/prompt_sistema.py` ("después de leer_receta, respondé tipo=confirmacion_receta"), pero el LLM no la siguió en ese turno puntual -- variabilidad real del modelo, no un bug determinista reproducible (no se pudo repetir con la misma imagen en otro intento). Se reforzó el texto del prompt para dejar más explícito que no hay que repreguntar ni pedir la foto de nuevo si `leer_receta` ya corrió en el turno (ver DECISIONES.md), pero al depender de que el LLM siga una instrucción en lenguaje natural, no hay garantía determinista de que no vuelva a pasar -- queda como limitación conocida, igual que la exactitud de ruteo del 79 % reportada en la Fase 10.

### Confirmado con el log de `operacion.turno`: el patrón es "conversación con historial previo"

Se repitió el caso reportado arriba y esta vez se pudo diagnosticar con datos reales, consultando `operacion.turno` (columna `tool_calls`) para los últimos turnos del canal web:

- Threads **nuevos** (primer mensaje de la conversación): mandar la foto dispara `[{"nombre": "leer_receta", "args": {}}]` correctamente, en todos los casos observados.
- Un thread que ya venía de otro intercambio (p. ej. una consulta de producto) y después recibe una foto: `tool_calls: []` -- el LLM no llamó a `leer_receta` en absoluto y respondió directamente pidiendo la foto, como si no hubiera ninguna.

O sea que el problema no es "a veces el modelo lee mal la receta": es que con historial de conversación previo en el mismo hilo, el modelo a veces ni siquiera decide llamar a la tool, aunque esté disponible y la imagen sí haya llegado (confirmado por el usuario: se veía la miniatura de la foto antes de enviar). **Workaround verificado por el usuario:** iniciar "Nueva conversación" antes de mandar una foto de receta evita el problema en el 100 % de los intentos hechos hasta ahora.

Se reforzó además el docstring de `tools/leer_receta.py::crear_tool_leer_receta_ligada` (la tool que ve el LLM) para dejar explícito, en el lugar que más peso tiene para el modelo al decidir qué tool usar, que su sola presencia en la lista de tools ya implica que hay una foto nueva en este mensaje, sin importar de qué haya sido el resto de la conversación. Sigue siendo una mitigación de prompt, no una garantía -- si vuelve a pasar, el workaround (nueva conversación) sigue siendo válido mientras no se investigue más a fondo (candidato a revisar: la extensión del historial de mensajes que ve el LLM en threads largos, o acotar el historial que se le pasa cuando llega una imagen).

## Canal web (Fase 11): `leer_receta` fallaba siempre con USE_FIXTURES=true, y `respuesta.text` vacío de Gemini para imágenes

### Dos causas superpuestas, encontradas probando una foto de receta real por el canal web

Después de arreglar el bug de texto vacío (más abajo), una foto de receta real seguía devolviendo "no pude leer la imagen" el 100 % de las veces. Dos causas independientes, ambas preexistentes (afectan igual al canal WhatsApp, no son del canal web):

**1. `USE_FIXTURES=true` en `.env` hace que `leer_receta` use un LLM fake.** El modelo del agente orquestador (`orquestador/agente.py::crear_modelo_chat_gemini`) siempre es Gemini real, sin mirar el flag. Pero `leer_receta` y `responder_consulta_normativa` resuelven su LLM interno con `llm/client.py::crear_cliente_llm(get_settings())`, que sí devuelve el fake si `USE_FIXTURES=true` -- que es justamente el valor que tenía `.env` (pensado como default seguro para tests, documentado así en el propio README para `evals/run_evals.py`). Resultado: la extracción de la receta corría contra el fake determinista, que no reconoce la imagen y devuelve `legible=False`. Se agregó un warning al arrancar `crear_app_produccion` (en los dos canales) cuando detecta el flag en `true`, y se documentó en el README que hace falta `USE_FIXTURES=false` para un canal real.

**2. Con `USE_FIXTURES=false`, `respuesta.text` de `google-genai` viene vacío para `gemini-3.5-flash-lite` en llamadas multimodales.** Reproducido llamando directo al SDK: `candidates[0].content.parts[0].text` traía el JSON pedido completo y correcto (confianza 1.0 en todos los campos), pero el accessor de conveniencia `respuesta.text` devolvía `""` -- la parte venía con un `thought_signature` (token de continuidad de "thinking" de la API nueva) que rompe la heurística de esa propiedad en esta versión del SDK. Se corrigió `llm/client.py::ClienteGemini._generar_con_key` con un fallback (`_texto_de_respuesta`) que arma el texto directamente desde `candidates[0].content.parts` cuando `.text` viene vacío, con test de regresión en `tests/llm/test_client.py`.

Con ambas correcciones, `leer_receta_logica` sobre una imagen real de `tests/fixtures/recetas/01_completa.jpg` da `estado="ok"` con los 6 campos extraídos correctamente.

## Canal web (Fase 11): foto de receta sin texto caía en la respuesta genérica de ayuda

### `HumanMessage` con contenido vacío no dispara ninguna tool

Al probar el canal web adjuntando una foto de receta sin escribir nada en el campo de texto, el agente respondía con la plantilla fija de `ayuda` ("Hola 👋 Soy el asistente...") en vez de leer la receta. Causa: `canal.py::texto_final` pasaba `mensaje.texto` tal cual al orquestador -- vacío (`""`) cuando el usuario solo adjunta imagen -- y `ejecutar_turno` arma el turno con `HumanMessage(content="")`; el agente nunca llega a decidir llamar `leer_receta` con un mensaje sin contenido.

El canal WhatsApp nunca tuvo este problema porque `webhook.py::texto_e_imagen` ya arma un texto por defecto para las fotos sin caption (`"Te mando la foto de mi receta."`); el canal web no replicaba ese fallback. Se corrigió agregando el mismo default en `texto_final` cuando hay `imagen_base64` y el texto está vacío, con un test de regresión (`tests/canales/test_web.py::test_mensaje_con_imagen_sin_texto_usa_texto_generico`).

## Prueba manual de WhatsApp real (post-Fase 10)

### El log de error de envío mostraba el `thread_id` interno, no el número realmente enviado a la Graph API

Al diagnosticar un `131030` en la prueba manual real, `app_produccion.py::_responder` logueaba `thread_id` (la forma canónica sin el "9") en el mensaje de error, no `numero_envio` (el valor que efectivamente se manda como `to` a la Graph API tras aplicar `numero_para_envio`). Esto ocultó durante varios intentos si el problema era la normalización o la lista de destinatarios de Meta -- había que deducir el valor real leyendo el código en vez de verlo en el log. Se corrigió logueando `numero_envio` (y se dejó `thread_id` también, entre paréntesis, para poder correlacionar con `operacion.turno`).

### `WHATSAPP_AR_QUITAR_9` necesitaba estar en `true`, no `false`, para el número de prueba real

`.env` tenía `WHATSAPP_AR_QUITAR_9=false` desde que se cargaron las credenciales (antes de esta sesión). Con ese valor, `numero_para_envio` reinsertaba el "9" antes de enviar (`549...`), y la Graph API rechazaba el envío con `131030` ("Recipient phone number not in allowed list") aunque el número fuera exactamente el mismo que había escrito el operario. La pista definitiva fue el propio botón "Enviar mensajes con la API" del panel de Meta, que arma un `curl` de ejemplo con `"to"` **sin** el 9 -- confirmando que el número autorizado en la cuenta de prueba está en formato `54XXXXXXXXXX`. Se corrigió el valor en `.env` (no es un bug de código: la variable existe justo para este caso, documentado desde la Fase 8, pero el valor cargado no correspondía al comportamiento real de esta cuenta de WhatsApp Business).

**Resultado:** con `WHATSAPP_AR_QUITAR_9=true` y un token de acceso vigente, el flujo completo funcionó de punta a punta contra el número de prueba real: `POST /webhook` (firma válida) → orquestador → Gemini real → respuesta enviada y recibida en el teléfono. Cierra el único pendiente que quedaba abierto de la Fase 8 (ver `docs/setup-whatsapp.md`).

## Fase 10 — Demo, documentación y defensa

### Repetir una demo con el mismo thread_id contra el checkpointer real degrada la respuesta

Al correr `notebooks/demo_e2e.ipynb` una segunda vez (para verificar el ajuste del caso 6) con los mismos `thread_id` fijos (`"demo-e2e-1"`, etc.), el caso 1 (que en la primera corrida dio un `APTA` completo con observaciones y fuentes) esta vez devolvió un `*Dictamen* *Resultado:* ⚠️ NO_EVALUABLE` vacío, sin citas ni observaciones. Causa: `checkpointer_postgres` persiste de verdad en Postgres entre corridas de la notebook (no es un checkpointer en memoria); al reusar el mismo `thread_id`, el LLM ve la conversación anterior ya completa en su historial y a veces responde desde su "recuerdo" de esa conversación en vez de volver a llamar la tool -- como el formateador arma el dictamen a partir de los artifacts de las tools ejecutadas *en el turno actual* (ver skill, "Contratos"), si no se llamó ninguna tool ese turno el dictamen sale vacío aunque el `tipo` declarado siga siendo "dictamen". No es un bug del núcleo (el contrato "nunca fabricar un dictamen sin evidencia" se sostiene: sale vacío, no inventado), pero sí hace que repetir un ensayo de la demo antes de la defensa dé resultados degradados si no se limpia el estado. Se corrigió generando un `SESION = uuid.uuid4().hex[:8]` al principio de `demo_e2e.ipynb` y `demo_sin_whatsapp.ipynb`, y sufijando todos los `thread_id` con esa sesión -- cada corrida arranca conversaciones nuevas.

### El caso APTA del propio plan venía fallando desde la Fase 7 por una unidad no reconocida, mal catalogado como "limitación aceptada"

Al armar `docs/guion-demo.md` con el caso exacto del plan (Flyer 10 Ec, soja, 170 cm³/ha, lejos de zonas protegidas) usando lenguaje natural, el dictamen daba `NO_EVALUABLE` con "Dosis 170.0 cm3/ha: unidad no reconocida" -- el mismo resultado que ya había aparecido en los evals de la Fase 7 y en las dos corridas de la demo de las Fases 8 y 9, sin que se investigara la causa raíz (se documentó como limitación general del parser de dosis). Al revisar `servicios/dosis.py::_FAMILIAS_UNIDAD` se encontró que solo tenía la clave `"cm³"` (con el superíndice unicode), nunca `"cm3"` (como lo escribe cualquiera desde el teclado de un celular, sin ese carácter). El caso de prueba directo (`tests/tools/test_evaluar_viabilidad_legal.py`) nunca lo detectó porque pasa `dosis_unidad="cm³/ha"` como argumento estructurado ya "correcto", sin pasar por lo que un LLM realmente extrae de una frase en español. Se corrigió agregando `"cm3"` como alias -- ver DECISIONES.md.

### Evals: la exactitud de ruteo bajó de 89 % a 79 % entre la Fase 7 y la Fase 10 sin que hubiera una regresión real

Al recorrer `evals/run_evals.py` como parte del checklist final de esta fase, el número reportado (79 %, 23/29) es más bajo que el 89 % (24/27) documentado en la Fase 7. Investigado caso por caso (ver DECISIONES.md, Fase 10): no es una regresión de comportamiento -- es que la corrección de la Fase 7 (capturar la excepción no controlada de una tool) hace que casos que antes rompían y quedaban afuera del denominador de la métrica ahora se cuenten, y algunos de esos casos ya eran ruteos imperfectos preexistentes que simplemente no se habían visto reflejados en el número hasta ahora. Documentado tal cual, no se ocultó ni se buscó una corrida que diera mejor número.

## Fase 9 — Extensiones

### Un test de guardia de la Fase 1 asumía que `MotivoNoResuelto` nunca crecería

`tests/dominio/test_motivos.py::test_son_nueve_motivos_segun_la_skill` afirmaba `len(list(MotivoNoResuelto)) == 9` a secas, para asegurar que el enum coincidiera exactamente con el catálogo fijo de la skill. Al agregar `VEHICULO_NO_ENCONTRADO` y `SIN_EVENTO_EN_CURSO` (Fase 9, fuera del alcance de la skill) falló con `11 == 9`, detectado en la corrida de regresión completa. No es un bug de producción: el test codificaba una invariante que dejó de ser cierta a propósito (la skill no cubre RF6-9, así que "coincidir con la skill" ya no es "tener exactamente 9"). Se reescribió el test para separar explícitamente los 9 motivos del núcleo (los de la skill) de los agregados por extensiones, en vez de simplemente subir el número a 11 -- así, si en el futuro se agrega un motivo de núcleo por error sin pasar por la skill, el test lo sigue detectando.

## Fase 8 — Canal WhatsApp

### Tests de dedup con `message_id` fijo: pasaban solos, fallaban en la segunda corrida de la suite completa

`tests/canales/test_dedup.py` y dos tests de `tests/canales/test_webhook.py` usaban strings fijos (`"wamid.test-dedup-nuevo-001"`, etc.) como `message_id`. Corridos solos (`pytest tests/canales -q`) pasaban los 31; corridos como parte de la suite completa (`pytest -q`, dos veces seguidas para verificar cero regresiones) fallaron 4: `operacion.mensaje_whatsapp` es una tabla real sin rollback entre tests (a propósito, ver DECISIONES.md: la deduplicación tiene que sobrevivir un reinicio del proceso), así que la fila que insertó la primera corrida seguía ahí en la segunda, y `ya_procesado` devolvía `True` para un mensaje que el test esperaba que fuera nuevo. Se corrigió generando un `message_id` único por invocación (`uuid.uuid4()`) en los tres tests afectados -- los que fallan por firma inválida antes de llegar al chequeo de dedup no necesitaron el cambio, nunca insertan una fila. Mismo tipo de hallazgo que las Fases 6/7 (un efecto persistente de un test contra la base compartida de desarrollo), esta vez detectado corriendo la suite completa dos veces en la misma sesión en vez de examinar datos ya cargados.

### Mismo patrón de drift de migraciones que en la Fase 7: la tabla de dedup nueva no existía en la base real

Al agregar `operacion.mensaje_whatsapp` a `003_operacion.sql` para la deduplicación de mensajes, hubo que aplicar el `CREATE TABLE IF NOT EXISTS` a mano contra la base de Docker en desarrollo (`docker compose exec db psql ...`) antes de poder correr `tests/canales/test_dedup.py` -- editar el archivo de migración no alcanza, igual que se documentó en la Fase 7 con la columna `adversidad` de `operacion.receta`. Sigue pendiente como deuda técnica una herramienta de migraciones real (Alembic u otra) que aplique diffs de esquema automáticamente.

### `config.py` tenía `WHATSAPP_GRAPH_VERSION` desactualizado respecto de `.env.example`

`.env.example` ya documentaba `v26.0` como la versión de Graph API verificada en vivo, pero el default en `config.py` seguía en `v23.0` (quedó así desde que se agregaron las variables de WhatsApp, antes de esa verificación). Se detectó al revisar la configuración completa del canal para esta fase, no por un test que fallara -- ningún test cubre que el default de `config.py` coincida con lo documentado en `.env.example`. Se corrigió el default; queda como recordatorio de revisar ambos archivos juntos cuando se actualice una versión de API externa.

## Fase 7 — Orquestador

### `operacion.receta` en la base real no tenía la columna `adversidad`

Al testear `orquestador/estado.py::obtener_receta_en_curso` contra Postgres real, falló con `psycopg.errors.UndefinedColumn: column "adversidad" does not exist`. Causa: en la Fase 4 se agregó `adversidad TEXT` a `003_operacion.sql` (el archivo de migración), pero nunca se re-ejecutó esa migración contra la base de desarrollo -- `CREATE TABLE IF NOT EXISTS` no altera una tabla que ya existe, aunque el `CREATE TABLE` del archivo ya incluya la columna nueva. Se corrigió con un `ALTER TABLE operacion.receta ADD COLUMN IF NOT EXISTS adversidad TEXT;` manual. Mismo patrón de fondo que el hallazgo de la Fase 6 (embeddings fake pisando datos reales): cambiar un archivo de migración no alcanza, hay que aplicarlo. Para un entorno real haría falta una herramienta de migraciones que detecte y aplique diffs de esquema (Alembic u otra, marcado `(verificar)` desde la Fase 1) en vez de SQL plano idempotente solo para tablas nuevas.

## Fase 6 — `responder_consulta_normativa`

### Scores de similitud casi nulos: embeddings fake pisando embeddings reales en la base de desarrollo

Al probar `articulos_por_similitud` con una pregunta real contra la normativa real de San Carlos Centro, todos los scores salían casi en cero (el máximo 0,029), y el artículo más relevante (distancia a escuela, aplicación terrestre) scoreaba peor que uno completamente irrelevante. Se armó un script de diagnóstico que comparó el embedding guardado en la base contra uno recién calculado para el mismo texto: los primeros 5 valores guardados eran `[0.72, 0.73, 0.74, 0.75, 0.76]` -- una secuencia incrementando de a 0,01, imposible como salida real de un modelo de embeddings, pero exactamente el patrón de la clase `_ModeloEmbeddingsFake` que usan los tests de integración de la Fase 3 (`(semilla + i) % 100 / 100.0`).

Causa raíz: `tests/insumos/test_loaders_integracion.py` conecta contra `DATABASE_URL` (la misma base de desarrollo que uso para cargar y verificar datos reales, no una base de test aislada) y hace un `DELETE` + recarga completa de `territorio.*` en cada corrida, usando ese modelo fake para no pagar el costo de cargar `sentence-transformers` en el test. Cada vez que corrí la suite completa (`pytest -q`) desde que existe ese test (Fase 3 en adelante), quedaban pisados con valores dummy los embeddings reales de `territorio.articulo` que había cargado a mano. `tests/senasa/test_loader.py` tenía el mismo patrón contra `catalogo.producto` (parcialmente enmascarado ahí porque el score de matching combina trigram + embedding, y trigram por sí solo ya acierta en nombres casi exactos).

Se corrigió reemplazando el modelo fake por el modelo real (`modelo_embeddings`, fixture compartida de `tests/conftest.py`) en ambos archivos, y recargando `territorio.articulo` con `loader_normativa.py` real para dejar la base en estado correcto. Con embeddings reales, el artículo 8 (el más relevante) pasó a scorear 0,498 -- razonable, y consistente con lo que daba un script de comparación en Python puro fuera de la base. Esto también llevó a bajar `RAG_UMBRAL_SIMILITUD` de 0,75 a 0,35 (ver DECISIONES.md), porque el valor viejo estaba calibrado sin haber visto un score real todavía.

No se resolvió la causa de fondo (tests de integración compartiendo la base de desarrollo en vez de una base de test aislada) -- ver DECISIONES.md, queda como deuda técnica documentada.

### Al recargar solo `loader_normativa.py` para arreglar lo anterior, se perdieron las reglas por el `ON DELETE CASCADE`

Al corregir el hallazgo de arriba, recargué manualmente `territorio.articulo` corriendo `loader_normativa.py` (con el modelo real) para restaurar los embeddings -- pero no corrí `loader_reglas.py` a continuación. `cargar_normas_de_carpeta` borra (`DELETE FROM territorio.norma WHERE ...`) antes de reinsertar, y `regla_distancia.norma_id` tiene `ON DELETE CASCADE`, así que ese `DELETE` se llevó puestas las 5 filas de `regla_distancia` sin que el loader de normativa supiera nada de eso. Se detectó porque `pytest -q` completo (corrida de regresión después del fix) hizo fallar `test_reglas_candidatas_de_san_carlos_incluye_la_ordenanza` con un conjunto vacío. Se corrigió corriendo también `loader_reglas.py`. Lección concreta: los tres loaders de insumos (`loader_geo`, `loader_normativa`, `loader_reglas`) son interdependientes por FK con cascada; recargar uno solo a mano puede dejar huérfanas las tablas que dependen de él -- conviene correr los tres en secuencia siempre, no uno suelto, salvo que se sepa explícitamente que no hay reglas afectadas.

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
