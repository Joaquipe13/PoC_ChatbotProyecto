# Especificación de plantillas

Una entrada por cada valor de `RespuestaAgente.tipo` (`src/fitosanitarios/dominio/modelos.py`, 17 en total). El formateador determinista (`src/fitosanitarios/orquestador/formateador.py`) arma el texto de cada plantilla a partir de los **artifacts de las tools ejecutadas en el turno**, nunca del texto libre del LLM (ver skill, "Contratos": `RespuestaAgente.tipo` + artifacts → formateador).

**Dónde está cada plantilla:** la de cada tipo de respuesta que produce una sola tool vive en `src/fitosanitarios/tools/<tool>/mensajes.py` (`plantilla_<tipo>`); `formateador.py` las reúne en `_PLANTILLAS` y tiene las comunes (`repregunta`, `fuera_de_dominio`, `no_resuelto`, `ayuda`, `error`); lo que se repite entre plantillas (citas, números, *Fuentes*, seguimientos) está en `servicios/formato.py`. `dictamen` y `consulta_producto` los producen dos tools cada uno y se reparten según la forma del resultado. Ver DECISIONES.md, "Estructura de `tools/`".

**Formato WhatsApp general:** `*negrita*`, listas con `-`/`1.`, sin tablas ni encabezados markdown, ≤ 4096 caracteres por mensaje (si se pasa, se parte por sección), coma decimal con unidad separada ("1,8 mm", "500 cm3/ha", sin ".0"), fechas `dd/mm/aaaa` y horas en la hora local del operario, sección `*Fuentes*` al final si hay citas que no se mostraron en la misma línea. Los botones se escriben `[BOTONES: A | B]` y las listas `[LISTA: A | B]` en los ejemplos: el canal los manda como botones o lista interactiva de WhatsApp.

Los ejemplos son **salidas reales** del bot contra la base de desarrollo (la mayoría, de las conversaciones del plan de pruebas del 26 y 27/09/2026, `evals/agente_prueba.py` con los escenarios `evals/escenarios/plan_*.yaml`; los de productos y "Corregir", del 28/09/2026).

## `confirmacion_receta`

**Cuándo:** después de `leer_receta` o `completar_receta`, antes de evaluar.

**Campos que usa:** artifact de la tool (`Receta` con `confianza_por_campo`); los campos con confianza baja se marcan con ⚠️.

Si falta un dato obligatorio (cultivo, localidad, tipo de aplicación, producto, dosis, lote o superficie; `servicios/receta.py`), no ofrece confirmar: pregunta lo que falta y muestra lo que pudo leer. El operario lo da y `completar_receta` lo aplica sobre la receta leída.

```
*Leí la receta N.° 0042*. Falta la siguiente información obligatoria:

1. *Localidad:* ¿En qué localidad se aplica?
2. *Tipo de aplicación:* ¿Es aplicación terrestre o aérea?
3. *Lote:* ¿Cuál es el número o nombre del lote?
4. *Superficie:* ¿Cuántas hectáreas tiene el lote?

*Lo que pude leer:*
- *Cultivo:* Algodon
- *Producto:* Acefato 75% — 0,5 kg/ha (Acefato)
```

Con todos los datos:

```
*Leí la receta N.° 0042*. Confirmá los datos:
- *Cultivo:* Algodon
- *Lote:* 7
- *Localidad:* Sastre
- *Superficie:* 40 ha
- *Producto:* Acefato 75% — 0,5 kg/ha (Acefato)
- *Tipo de aplicación:* terrestre
[BOTONES: Confirmar | Corregir]
```

"Corregir" sin decir qué dato (`completar_receta` sin argumentos) va como `repregunta`:

```
¿Qué dato querés corregir? Escribilo con el valor correcto, por ejemplo: "la dosis es 200 cc/ha" o "es en Sastre".
```

## `dictamen`

**Cuándo:** resultado de `evaluar_viabilidad_legal` (dictamen con veredicto) o de `evaluar_riesgo` suelto (condiciones de aplicación, sin veredicto).

**Campos que usa:** artifact `Dictamen` (`resultado`, `observaciones`, `condiciones`, citas) o, en el suelto, `condiciones` y `observaciones` de `evaluar_riesgo`. Desde el 19/09 la distancia no se compara contra la ubicación del lote: se informa en *Condiciones de aplicación* (ver `DECISIONES.md`).

Dictamen de una receta confirmada:

```
*Dictamen* — Sastre
*Resultado:* ✅ APTA

*Condiciones de aplicación* — Sastre · terrestre · banda III (azul)
- *Distancia mínima a zona urbana:* 1000 m (Fallo Sastre/2020)
- *Distancia mínima a escuelas:* 200 m (Ordenanza 1174/2019)

*Fuentes*
- SENASA, Reg. 36302 (detalle API)

¿Agendamos la aplicación?
[BOTONES: Agendar | No, gracias]
```

Consulta suelta ("¿puedo usar Flyer 10 Ec en soja a 500 cm3/ha por tierra en El Trébol?"): la dosis fuera de rango va primero y **no se ofrece agendar**, como en un dictamen OBSERVADA. Con un solo producto tampoco se ofrece "la banda de cada producto", que ya está en el encabezado; con varios, sí (`[BOTONES: Sí | No]`).

```
⚠️ *Observaciones*
1. Flyer 10 Ec: Dosis 500 cm3/ha: por encima del rango registrado (160-180 cm3/ha), 178% de desvío.

*Condiciones de aplicación* — El Trébol · terrestre · banda II (amarilla)
- *Distancia mínima a zona urbana:* 500 m (Ley 11273/1995, art. 34)
```

## `detalle_bandas`

**Cuándo:** el operario pide la banda de cada producto después de un dictamen o una evaluación con varios productos. Sale de `evaluar_riesgo` del turno.

```
*Banda de cada producto*
- Flyer 10 Ec · Reg. SENASA 41881: II (amarilla)
- Tordon D 30 · Reg. SENASA 30735: III (azul)
La aplicación se rige por la más peligrosa: II (amarilla).

*Condiciones de aplicación* — Sastre · terrestre · banda II (amarilla)
- *Distancia mínima a zona urbana:* 1000 m (Fallo Sastre/2020)
- *Distancia mínima a escuelas:* 200 m (Ordenanza 1174/2019)

¿Agendamos la aplicación?
[BOTONES: Agendar | No, gracias]
```

## `consulta_producto`

**Cuándo:** resultado de `validar_producto_registro` (un producto) o `consultar_productos` (listado).

Un producto, su banda (sin cultivo):

```
*Tordon D 30* · Reg. SENASA 30735 · Banda III (azul)
```

Un producto para un cultivo ("¿cuál sería la dosis correcta?" después de un aviso de dosis):

```
*Flyer 10 Ec* · Reg. SENASA 41881 · Banda II · ✅ autorizado para soja
Dosis registrada para soja: 160-180 cm3/ha (Chinche De La Alfalfa)
```

Un nombre que coincide con varios productos (va como `repregunta`, con la lista de la tool):

```
Hay varios productos parecidos a 'Roundup'. ¿Cuál es?
[LISTA: Roundup Fg | Roundup Wg | Roundup Max | Roundup Fg W | Roundup Ready]
```

Un producto registrado del que SENASA no publica usos ni dosis (6 de cada 7): lo que se sabe y qué no se puede verificar. Si tiene marbete con texto, suma lo que dice su marbete sobre la dosis para ese cultivo, con la página en *Fuentes*:

```
*Manto* · Reg. SENASA 38008 · Banda III (azul)
⚠️ SENASA no publica para qué cultivos ni en qué dosis está registrado, así que no puedo verificar si 60 cc/ha es correcta para maiz.
*Qué podés hacer:* fijate la dosis en la etiqueta del envase o consultalo con el ingeniero agrónomo que firmó la receta.
```

```
*2,4-db Sigma* · Reg. SENASA 38806 · Banda II (amarilla)
⚠️ SENASA no publica para qué cultivos ni en qué dosis está registrado, así que no puedo decirte la dosis registrada para soja.
*Según su marbete:* El marbete indica que para el cultivo de soja se debe usar en mezcla y no superar los 50 cm3/ha del producto.
*Qué podés hacer:* confirmalo con el ingeniero agrónomo que firmó la receta.

*Fuentes*
- SENASA, Reg. 38806 (marbete, pág. 1)
```

Listado: una fila por producto, con el total real y un título que dice qué se buscó (cualquier combinación de cultivo, plaga, principio activo, aptitud, banda, firma y marca). Con cultivo o plaga avisa que solo aparecen los productos con usos cargados; un filtro que no está en el registro se omite y se avisa:

```
*Herbicidas para soja*

(10 de 246)
1. *2,4db 100 Aca* · Reg. SENASA 30005 · Banda III · 1 a 1,25 l/hm2
2. *2,4-db 93.1 Brilliance* · Reg. SENASA 41974 · Banda III · 5 dosis distintas según la plaga
...

⚠️ Solo aparecen los productos que tienen cultivos y plagas cargados en SENASA; puede haber otros registrados sin esos datos

Es lo que figura en el registro; qué aplicar lo define la receta del ingeniero agrónomo.
```

Con una localidad y una distancia, una sección por tipo de aplicación con las bandas que se pueden a esa distancia de la zona urbana (una sola, "Aérea y terrestre (lo mismo para las dos)", si coinciden) y las normas en *Fuentes*:

```
*Fungicidas para trigo* a 1500 m de la zona urbana de El Trébol

*Aérea:* ✅ III y IV · ❌ Ia, Ib y II
(10 de 84)
1. *Abril 50 Curasemilla* · Reg. SENASA 38052 · Banda III
2. *Adama Almagor* · Reg. SENASA 36471 · Banda III · 1250 cc/ha
...

*Terrestre:* ✅ todas las bandas
(10 de 115)
1. *Abril 50 Curasemilla* · Reg. SENASA 38052 · Banda III
2. *Acento Induxor* · Reg. SENASA 40082 · Banda II · 700 cc/ha
...

⚠️ Solo aparecen los productos que tienen cultivos y plagas cargados en SENASA; puede haber otros registrados sin esos datos

Es lo que figura en el registro; qué aplicar lo define la receta del ingeniero agrónomo.

*Fuentes*
- Ley 11273/1995, art. 33
- Ordenanza 841/2010, art. 7 (el-trebol)
```

## `consulta_marbete`

**Cuándo:** resultado de `consultar_marbete`. El LLM responde solo con los fragmentos recuperados del marbete; cada página citada se verifica en código.

```
*Vertimec* · Reg. SENASA 30116
Los bidones vacíos deben someterse a triple lavado o lavado a presión, inutilizarse perforándolos sin dañar la etiqueta y enviarse a centros de acopio habilitados según la ley 27.279, estando prohibido reutilizarlos, enterrarlos o quemarlos.

*Fuentes*
- SENASA, Reg. 30116 (marbete, pág. 10)
```

Sin respaldo en el marbete: ver `no_resuelto`, "No cuento con esa información".

## `consulta_normativa`

**Cuándo:** resultado de `responder_consulta_normativa`.

**Campos que usa:** veredicto corto (Sí / No / Depende) y la regla en una oración, redactados por el LLM **solo** con los fragmentos recuperados, más las citas verificadas en código.

```
*No.* Se prohiben las pulverizaciones de cualquier tipo cuando los vientos superen los 8 km/hora y puedan producir derivas hacia la planta urbana.

*Fuentes*
- Ordenanza 841/2010, art. 4 (el-trebol)
```

## `consulta_articulo`

**Cuándo:** resultado de `consultar_articulo` ("¿me pasás el artículo 33 de la ley 11273?").

**Campos que usa:** `norma_legible`, `numero`, `jurisdiccion_id`, `partes`. El texto va **literal**, sin pasar por el LLM, con las líneas cortadas del PDF ya unidas y un renglón por inciso. No lleva *Fuentes*: el encabezado ya cita norma, artículo y jurisdicción. Si el PDF trae más de un texto con el mismo número se muestran todos; un artículo de más de 4096 caracteres se parte en varios mensajes. Sin localidad y sin norma nombrada, avisa que buscó en la normativa provincial y nacional; con el número en varias normas, pregunta cuál (lista).

```
*Ley 11273/1995, art. 33 (santa-fe)*
Prohíbese la aplicación aérea de productos fitosanitarios de clase toxicológica A y B dentro del radio de 3.000 metros de las plantas urbanas. Excepcionalmente podrán aplicarse productos de clase toxicológica C o D dentro del radio de 500 metros, cuando en la jurisdicción exista ordenanza municipal o comunal que lo autorice, y en los casos que taxativamente establecerá la reglamentación de la presente. Idéntica excepción y con iguales requisitos podrán establecerse con los productos de clase toxicológica B para ser aplicados en el sector comprendido entre los 500 y 3.000 metros.
```

## `limitaciones`

**Cuándo:** resultado de `listar_limitaciones` ("¿a qué distancia del pueblo puedo tirar Tordon D 30 con avión en Sastre?", "¿qué limitaciones hay en El Trébol?", "¿qué puedo aplicar a 1000 m?").

**Campos que usa:** las reglas de `reglas.csv` (no por similitud): `prohibiciones` (`N`), `condicionales` (`S`), las distancias que rigen y, con una distancia, qué se puede a esa distancia. Arriba va *Distancia mínima que rige*: por zona, tipo de aplicación y banda, la prohibición más restrictiva (el mismo criterio que el dictamen), con "salvo excepciones" si una condicional habilita más cerca. Una excepción de una norma más general no levanta la prohibición de una más local. Las reglas leídas del PDF llevan un aviso de verificación.

Con un producto (la banda sale del registro; si vino otra banda, se avisa que se usa la del registro):

```
*Limitaciones en Sastre*

Para *Tordon D 30*: banda III (azul)

*Distancia mínima que rige*
- Zona urbana · aérea: banda III: 3000 m (Ordenanza 1174/2019)
- Escuelas · aérea: banda III: 200 m (Ordenanza 1174/2019)

*Aplicación aérea*
- Zona urbana · bandas III, IV: a menos de 500 m no se puede aplicar (Ley 11273/1995, art. 33)
- Escuelas · todas las bandas: a menos de 200 m no se puede aplicar (Ordenanza 1174/2019)
- Zona urbana · todas las bandas: a menos de 3000 m no se puede aplicar (Ordenanza 1174/2019)

*Excepciones*
- Zona urbana · aérea · bandas III, IV: se puede con condiciones (Ley 055297/2017, art. 51)

*Fuentes*
- SENASA, Reg. 30735 (detalle API)
- Ley 11273/1995, art. 33
- Ordenanza 1174/2019 (sastre)
- Ley 055297/2017, art. 51
```

Localidad sin ordenanza cargada:

```
*Limitaciones en Rosario*

⚠️ No se cuenta con la normativa municipal de Rosario: las limitaciones son las de la normativa provincial

*Distancia mínima que rige*
- Zona urbana · terrestre: banda II: 500 m (Ley 11273/1995, art. 34)

*Aplicación terrestre*
- Zona urbana · bandas Ia, Ib, II: a menos de 500 m no se puede aplicar (Ley 11273/1995, art. 34)

*Fuentes*
- Ley 11273/1995, art. 34
```

Un equipo que las normas no nombran (drone como aérea, mochila como terrestre) lleva un aviso arriba: "⚠️ Las normas cargadas no mencionan los drones: muestro las reglas de aplicación aérea, que es como se los suele encuadrar. Confirmalo con la autoridad de aplicación antes de aplicar". Una comparación ("¿es lo mismo por avión que por tierra?") muestra las secciones *Aplicación aérea* y *Aplicación terrestre* en la misma respuesta.

Con una distancia (`distancia_m`):

```
*A 1000 m de la zona urbana en Rosario*
- *Terrestre:* ✅ Ia, Ib, II, III y IV
- *Aérea:* ✅ III y IV · ⚠️ II solo con excepción (Ley 055297/2017, art. 51) · ❌ Ia y Ib

⚠️ No se cuenta con la normativa municipal de Rosario: las limitaciones son las de la normativa provincial

*Fuentes*
- Ley 11273/1995, art. 33
- Ley 055297/2017, art. 51
```

## `consulta_vehiculo`

**Cuándo:** resultado de `resolver_vehiculo`, si el operario pregunta por un equipo.

```
*Vehículo:* pulverizador autopropulsado (terrestre)
```

## `evento_registrado`

**Cuándo:** resultado de `registrar_evento`. Las horas van en la hora local del operario.

```
✅ *Aplicación iniciada*
- *Vehículo:* pulverizador autopropulsado
- *Lote:* 4
- *Inicio:* domingo 27/09/2026, 10:14
```

```
✅ *Aplicación finalizada*
- *Lote:* 4
- *Inicio:* domingo 27/09/2026, 10:14
- *Fin:* domingo 27/09/2026, 10:14
```

## `agenda`

**Cuándo:** resultado de `consultar_agenda`, de uno o varios días.

```
*Agenda del lunes 28/09/2026 al sábado 03/10/2026*
*Lunes 28/09/2026:* sin tareas
*Martes 29/09/2026:* sin tareas
...
*Sábado 03/10/2026:* sin tareas
```

## `agendar_aplicacion`

**Cuándo:** resultado de `agendar_aplicacion`. Sin fecha pregunta el día; sin hora muestra la agenda de ese día y pregunta el horario (esta plantilla muestra lo que falta, no pasa por `repregunta`).

```
¿Para qué fecha querés agendar la aplicación? Podés decirme un día (por ejemplo "martes" o "mañana") o una fecha (por ejemplo 25/09).
```

Agendada, con el pronóstico de la franja y la regla de viento de la localidad. Si ya había tareas a esa hora se avisa una vez por cultivo y lote ("⚠️ Ya tenías 6 aplicaciones de soja (sin lote) agendadas a las 09:00"):

```
✅ *Aplicación agendada* — lunes 28/09/2026, 09:00 hs
- *Cultivo:* soja

*Pronóstico en El Trébol, de 07:00 a 11:00* (Open-Meteo, consultado el 27/09 10:10)
- Viento del sureste (empuja hacia el noroeste), 10 a 16 km/h, ráfagas de hasta 32 km/h
- Lluvia: 1,8 mm (probabilidad de hasta 58 %)
- Temperatura: 17 a 19 °C · humedad desde 83 %
📋 Ordenanza 841/2010, art. 4: prohíbe pulverizar con vientos de más de 8 km/h que puedan producir derivas hacia la planta urbana.
Es un pronóstico: verificá el viento en el lote antes de empezar.
```

## `repregunta`

**Cuándo:** falta un dato. Si una tool del turno ya dijo qué falta (y con qué opciones), manda eso; si no, `RespuestaAgente.faltantes`. Hasta 3 datos; cada uno con su pregunta y, si corresponde, botones o lista.

```
¿En qué localidad se aplica?
[LISTA: El Trébol | Sastre | San Jorge | ...]
```

**Respuesta neutra:** si el modelo repregunta sin decir qué falta (pasa con "me equivoqué de foto, después te la mando"), o ante un saludo, un agradecimiento o un "No, gracias", o si eligió un tipo que muestra datos de una tool sin que haya corrido ninguna:

```
Dale. Cuando quieras, mandame la foto de la receta o escribime tu consulta (un producto, una localidad o una norma).
```

## `fuera_de_dominio`

**Cuándo:** el orquestador clasifica el mensaje como fuera de dominio antes de llamar tools (clima, fútbol, pedir las instrucciones internas). Texto fijo.

```
Solo puedo ayudarte con recetas de fitosanitarios: leer y validar recetas, verificar productos registrados en SENASA, responder dudas sobre la normativa de aplicación de las localidades cargadas, y registrar/consultar tus aplicaciones en el campo. ¿Me mandás una receta o una consulta sobre eso?
```

## `no_resuelto`

**Cuándo:** una tool devuelve `estado="no_resuelto"` con un `MotivoNoResuelto`. Tres formas:

Sin respaldo en el RAG (`NORMATIVA_SIN_RESPALDO`, `MARBETE_SIN_RESPALDO`): no es un error ni un dato mal dado, el bot no tiene esa información. Se dice así, sin avisos internos:

```
ℹ️ *No cuento con esa información*
No encontré en la normativa cargada nada que responda tu pregunta, así que no te doy una respuesta sin una norma que la respalde.
*Qué podés hacer:* consultalo al área de ambiente del municipio o a tu ingeniero agrónomo.
```

(Para el marbete: "No encontré en el marbete del producto nada que responda tu pregunta…" y "leé la etiqueta del envase o consultalo con tu ingeniero agrónomo".)

Foto que no es una receta o no se lee (`IMAGEN_ILEGIBLE`):

```
📷 *No pude leer una receta en esa foto*
Puede que no sea una receta, o que esté borrosa o cortada.
*Qué podés hacer:* mandame una foto nítida de la receta completa, con buena luz.
```

El resto de los motivos (descripción de `dominio/motivos.py::DESCRIPCION_MOTIVO`):

```
⚠️ *No pude completar la consulta*
*Por qué:* <descripción del motivo>
*Detalle:* <primera advertencia de la tool, si hay>
*Qué podés hacer:* revisá el dato e intentá de nuevo, o consultá al área de ambiente del municipio / a tu ingeniero agrónomo.
```

Algunos motivos tienen su propio *Qué podés hacer* (`formateador.py::_QUE_HACER`): `SIN_USOS_REGISTRADOS` dice "fijate la dosis en la etiqueta del envase o consultalo con el ingeniero agrónomo que firmó la receta" (en `validar_producto_registro` ese caso ya no llega acá: ver `consulta_producto`).

## `ayuda`

**Cuándo:** el operario pide ayuda genérica ("¿qué podés hacer?"). Texto fijo.

```
Hola 👋 Soy el asistente de recetas fitosanitarias. Puedo:
- Leer una foto de tu receta y decirte si es apta para aplicar.
- Buscar si un producto está registrado en SENASA y qué dice su marbete (carencia, precauciones, mezclas).
- Responder dudas sobre la normativa de aplicación de tu localidad, mostrarte el texto de un artículo o decirte qué limitaciones tiene.
- Registrar cuando empezás y terminás de aplicar.
- Contarte tu agenda del día.
Mandame una foto de receta o contame qué necesitás.
```

## `error`

**Cuándo:** una tool devuelve `estado="error"` o el orquestador captura una excepción. Nunca se muestran detalles internos: van al log del turno (desde el 28/09/2026, el tipo y el mensaje de la excepción quedan en `operacion.turno.salida.error`). Un error de cuota de Gemini primero se reintenta con las otras keys configuradas.

```
⚠️ Tuve un problema técnico y no pude procesar tu mensaje. Probá de nuevo en unos minutos; si sigue fallando, contactá a soporte.
```
