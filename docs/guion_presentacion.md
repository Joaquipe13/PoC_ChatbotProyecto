# Guion de la presentación en video (15 a 20 minutos)

Guía para grabar el video del TP: el caso de negocio por arriba, los problemas que resuelve
el chatbot alternados con chats reales, las herramientas y los problemas que surgieron. Los
tiempos son orientativos (total ~18 min); si hay que recortar, las secciones marcadas como
*opcional* son las primeras en salir.

Las salidas de los chats son las que dio el bot con Gemini real el 27/09/2026. Gemini varía
entre corridas: **ensayar cada chat antes de grabar** (con `USE_FIXTURES=false`, una
conversación nueva por caso). El guion técnico caso por caso está en `docs/guion-demo.md`.

**Antes de grabar:** `docker compose up -d db`, `notebooks/chat.ipynb` abierto con la celda
de preparación corrida (`uv run jupyter notebook notebooks/chat.ipynb`),
"Nueva conversación" antes de empezar la parte 1 y antes de cada chat de la parte 2 (en una
conversación muy larga Gemini se equivoca más), y los datos del proyecto final completados donde
dice *[completar]*.

---

## 1. Apertura (0:00 – 0:45)

**En pantalla:** título y el chat del notebook abierto.

**Qué decir:**
- Quiénes somos y qué vamos a mostrar: el módulo de chatbot de nuestro proyecto final, un
  asistente por WhatsApp para aplicaciones de fitosanitarios.
- Lo que va a ver el video: el problema, cómo lo resuelve el bot (con chats reales), cómo
  está hecho y qué aprendimos en el camino.

---

## 2. El caso de negocio (0:45 – 3:00)

**En pantalla:** una o dos diapositivas simples (un mapa de Santa Fe, una receta agronómica,
un envase con su banda de color).

**Qué decir:**
- **El proyecto final.** *[completar: nombre del proyecto, a quién apunta (empresa aplicadora,
  cooperativa, productor), qué módulos tiene además del chatbot.]*
- **La actividad.** Cada aplicación de un fitosanitario (herbicida, insecticida, fungicida)
  la prescribe un ingeniero agrónomo en una **receta agronómica**: cultivo, lote, plaga,
  productos, dosis, superficie y tipo de aplicación (terrestre o aérea). La ejecuta un
  **operario** en el campo.
- **Lo que tiene que cumplir.** Que el producto esté **registrado en SENASA** y autorizado
  para ese cultivo, con una dosis dentro del rango registrado. Y las **distancias mínimas**
  a la zona urbana, escuelas y cursos de agua, que dependen del **tipo de aplicación** y de
  la **banda toxicológica** del producto (roja, amarilla, azul, verde).
- **Dónde está esa información.** Dispersa: el registro de SENASA (más de 7.000 productos),
  la ley provincial de Santa Fe y su decreto, las ordenanzas de cada municipio y hasta fallos
  judiciales que fijan distancias. El operario no tiene cómo consultarla en el lote.
- **La propuesta del módulo.** Un asistente por WhatsApp, la herramienta que el operario ya
  usa: le manda la foto de la receta o una pregunta y recibe una respuesta **con la fuente**
  (registro de SENASA, norma y artículo).
- **Alcance de la prueba de concepto:** Santa Fe, con normativa real de **El Trébol, Sastre y
  San Jorge**; el resto de las localidades de la provincia se responde con la ley provincial,
  aclarándolo.

---

## 3. Lo que hace el bot, con un recorrido completo (3:00 – 12:00)

Un recorrido por las 14 herramientas (tools) del bot en dos partes: **un día de trabajo** con
una receta (de la foto al registro de la aplicación, en una sola conversación) y **las dudas
del día**, cada una en una conversación nueva. Para cada chat: una frase del problema, el chat
en pantalla y una frase de qué hay que notar. No leer la respuesta entera: señalar lo
importante.

| Chat | Tools que se ven |
|---|---|
| 3.1 La receta, de la foto al dictamen | `leer_receta`, `completar_receta`, `evaluar_viabilidad_legal` |
| 3.2 Agendar, con el pronóstico | `agendar_aplicacion` |
| 3.3 En el campo | `registrar_evento` (con `resolver_vehiculo` adentro), `consultar_agenda` |
| 3.4 "¿Puedo aplicar esto?" | `evaluar_riesgo`, `validar_producto_registro`, `consultar_productos` |
| 3.5 "¿A qué distancia del pueblo?" | `listar_limitaciones` |
| 3.6 "¿Qué dice la etiqueta?" | `consultar_marbete` |
| 3.7 "¿Qué dice la norma?" | `responder_consulta_normativa`, `consultar_articulo` |

Las salidas son las que dio el bot con Gemini real el 27/09/2026. La fecha del agendado y el
pronóstico van a ser otros el día que se grabe.

### Parte 1: un día de trabajo (una sola conversación, 3.1 a 3.3)

#### 3.1 La receta, de la foto al dictamen (3:00 – 4:45)

**Problema:** la receta viene en papel o en foto; transcribirla es lento, y verificar a mano el
registro, el cultivo, la dosis y la normativa lleva tiempo y se cometen errores.

**Chat:** adjuntar `data/recetas_ejemplo/02_apta_aerea_banda_ii.jpg` con "te paso la receta".

```
*Leí la receta N.° 1002*. Falta la siguiente información obligatoria:

1. *Localidad:* ¿En qué localidad se aplica?

*Lo que pude leer:*
- *Cultivo:* Soja
- *Lote:* 3
- *Superficie:* 25 ha
- *Adversidad:* Chinche de la alfalfa
- *Producto:* Flyer 10 Ec — 170 cm3/ha
- *Tipo de aplicación:* aérea
```

> El Trébol

```
*Leí la receta N.° 1002*. Confirmá los datos:
- *Cultivo:* Soja
- *Lote:* 3
- *Localidad:* El Trébol
...
[Confirmar] [Corregir]
```

> *(botón)* Confirmar

```
*Dictamen* — El Trébol
*Resultado:* ✅ APTA

*Condiciones de aplicación* — El Trébol · aérea · banda II (amarilla)
- *Distancia mínima a zona urbana:* 3000 m (Ley 11273/1995, art. 33)

*Fuentes*
- SENASA, Reg. 41881 (detalle API)
- Ordenanza 841/2010, art. 6 (el-trebol)
- Ordenanza 841/2010, art. 7 (el-trebol)

¿Agendamos la aplicación?
[Agendar] [No, gracias]
```

**Qué notar:** el bot lee la foto con un modelo multimodal, y lo que falta (la localidad) **lo
pregunta en vez de adivinarlo**; con la respuesta completa la receta que ya leyó, sin volver a
leerla. Siempre se confirma antes de evaluar. El dictamen **no lo decide el LLM**: lo calcula
código contra el registro de SENASA y las reglas cargadas, y cada dato trae su fuente.

#### 3.2 Agendar, con el pronóstico (4:45 – 5:30)

**Problema:** coordinar cuándo aplicar, y el viento y la lluvia cambian lo que conviene.

> *(botón)* Agendar

```
¿Para qué fecha querés agendar la aplicación? Podés decirme un día (por ejemplo "martes" o "mañana") o una fecha (por ejemplo 25/09).
```

> el lunes a las 9

```
✅ *Aplicación agendada* — lunes 28/09/2026, 09:00 hs
- *Cultivo:* Soja
- *Lote:* 3

*Pronóstico en El Trébol, de 07:00 a 11:00* (Open-Meteo, consultado el 27/09 22:00)
- Viento del sureste (empuja hacia el noroeste), 13 a 17 km/h, ráfagas de hasta 32 km/h
- Lluvia: 2,2 mm (probabilidad de hasta 67 %)
- Temperatura: 15 a 16 °C · humedad desde 89 %
📋 Ordenanza 841/2010, art. 4: prohíbe pulverizar con vientos de más de 8 km/h que puedan producir derivas hacia la planta urbana.
Es un pronóstico: verificá el viento en el lote antes de empezar.
```

**Qué notar:** "el lunes" lo resuelve código, no el LLM. El pronóstico es **información**, no
un control: dice hacia dónde va la deriva y trae la norma de viento de la localidad.

#### 3.3 En el campo (5:30 – 6:15)

> Arranco a aplicar con la mosquito en el lote 8

```
✅ *Aplicación iniciada*
- *Vehículo:* pulverizador autopropulsado
- *Lote:* 8
- *Inicio:* domingo 27/09/2026, 22:07
```

> Listo, terminé

```
✅ *Aplicación finalizada*
- *Lote:* 8
- *Inicio:* domingo 27/09/2026, 22:07
- *Fin:* domingo 27/09/2026, 22:08
```

> ¿Qué tengo agendado para esta semana?

```
*Agenda del lunes 28/09/2026 al sábado 03/10/2026* (1)
*Lunes 28/09/2026:*
1. ⏳ 09:00 — Soja — lote 3 (pendiente)
*Martes 29/09/2026:* sin tareas
...
```

**Qué notar:** "la mosquito" es como le dicen en el campo al pulverizador autopropulsado: el bot
lo reconoce contra un catálogo de equipos. La agenda muestra la aplicación que se agendó en 3.2.

### Parte 2: las dudas del día (una conversación nueva para cada una)

#### 3.4 "¿Puedo aplicar esto?" (6:15 – 7:45)

**Problema:** antes de comprar o aplicar, saber si un producto sirve y a qué dosis.

> ¿Puedo usar Flyer 10 Ec en soja a 500 cm3/ha por tierra en El Trébol?

```
⚠️ *Observaciones*
1. Flyer 10 Ec: Dosis 500 cm3/ha: por encima del rango registrado (25-180 cm3/ha), 178% de desvío.

*Condiciones de aplicación* — El Trébol · terrestre · banda II (amarilla)
- *Distancia mínima a zona urbana:* 500 m (Ley 11273/1995, art. 34)
```

> ¿Y cuál sería la dosis correcta?

```
*Flyer 10 Ec* · Reg. SENASA 41881 · Banda II · ✅ autorizado para Soja
Dosis registrada para Soja:
- 25 a 35 cm3/ha (Oruga De Las Leguminosas)
- 150 cm3/ha (Trips Del Poroto)
- 160-180 cm3/ha (Chinche De La Alfalfa)
- 160-180 cm3/ha (Chinche Verde)
```

> ¿Qué productos banda verde hay registrados para soja?

```
*Productos para soja, banda IV*

(10 de 151)
1. *Aceite Quimeco Plus* · Reg. SENASA 37227 · Banda IV · 250 cm3 por ha
2. *Agrolufen 5 Ec* · Reg. SENASA 38947 · Banda IV · 200-300 cm3/ha
...
⚠️ Solo aparecen los productos que tienen cultivos y plagas cargados en SENASA; puede haber otros registrados sin esos datos

Es lo que figura en el registro; qué aplicar lo define la receta del ingeniero agrónomo.
```

Y una pregunta con varias condiciones a la vez (*opcional*):

> ¿Qué fungicidas para trigo puedo aplicar a 1500 metros de El Trébol?

```
*Fungicidas para trigo* a 1500 m de la zona urbana de El Trébol

*Aérea:* ✅ III y IV · ❌ Ia, Ib y II
(10 de 84)
1. *Abril 50 Curasemilla* · Reg. SENASA 38052 · Banda III
...
*Terrestre:* ✅ todas las bandas
(10 de 115)
...
*Fuentes*
- Ley 11273/1995, art. 33
- Ordenanza 841/2010, art. 7 (el-trebol)
```

**Qué notar:** la dosis está fuera de **todos** los rangos registrados para soja, así que es
una observación sea cual sea la plaga; con una dosis dentro de alguno, el bot pide la plaga
antes de dar por buena la receta. Con la dosis mal, **no ofrece agendar**. El listado informa lo
registrado, no recomienda; la distancia al pueblo se traduce en las bandas que se pueden
aplicar ahí (con la norma que lo fija), y sin tipo de aplicación responde para los dos.

#### 3.5 "¿A qué distancia del pueblo puedo tirar?" (7:45 – 9:00)

**Problema:** la distancia depende de la localidad, del tipo de aplicación y de la banda, y la
fijan varias normas a la vez.

> voy a tirar Tordon D 30 con avion en Sastre, a cuanto del pueblo tengo que estar?

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
...
```

**Qué notar:** el operario no dijo la banda: el bot la toma del registro. La ley provincial dice
500 m y la ordenanza de Sastre 3000 m: el bot dice **cuál manda** (la más restrictiva). Con
"drone" o "mochila", que las normas no nombran, avisa que es una suposición.

*Opcional:* "¿es lo mismo aplicar por avión que por tierra en Sastre?" (compara los dos en una
sola respuesta).

#### 3.6 "¿Qué dice la etiqueta?" — el marbete (9:00 – 10:15)

**Problema:** la etiqueta del producto (el marbete) tiene carencias, precauciones, mezclas, qué
hacer ante un derrame… en un PDF de 10 páginas.

> ¿Qué hago si se me vuelca Banvel en el galpón?

```
*Banvel* · Reg. SENASA 30596
Hay que cubrir el derrame con material absorbente como tierra o arena, barrerlo para recolectarlo en recipientes identificados y lavar la superficie con agua carbonatada o jabonosa.

*Fuentes*
- SENASA, Reg. 30596 (marbete, pág. 8)
```

**Qué notar:** es **RAG**: el bot busca en los 3.217 marbetes cargados y responde **solo** con
lo que encontró, citando la página. El operario dijo "se me vuelca en el galpón" y el marbete
dice "derrame": ver 5.2.

#### 3.7 "¿Qué dice la norma?" — y cuándo no sabe (10:15 – 12:00)

> ¿Se puede fumigar con viento en El Trébol?

```
*Depende.* Se prohiben las pulverizaciones si el viento supera los 8 km/hora y puede producir deriva hacia la planta urbana.

*Fuentes*
- Ordenanza 841/2010, art. 4 (el-trebol)
```

> Pasame el artículo 33 de la ley 11273

```
*Ley 11273/1995, art. 33 (santa-fe)*
Prohíbese la aplicación aérea de productos fitosanitarios de clase toxicológica A y B dentro del radio de 3.000 metros de las plantas urbanas. Excepcionalmente podrán aplicarse productos de clase toxicológica C o D dentro del radio de 500 metros, cuando en la jurisdicción exista ordenanza municipal o comunal que lo autorice, [...]
```

Y una que la normativa cargada no responde:
> ¿Hay que avisar antes de aplicar en El Trébol?

```
ℹ️ *No cuento con esa información*
No encontré en la normativa cargada nada que responda tu pregunta, así que no te doy una respuesta sin una norma que la respalde.
*Qué podés hacer:* consultalo al área de ambiente del municipio o a tu ingeniero agrónomo.
```

**Qué notar:** la pregunta libre es RAG sobre la normativa, y la cita se **verifica en código**
contra lo recuperado. El artículo por número no pasa por el LLM: es el **texto literal** de la
ley. Sin una norma que la respalde, el bot prefiere decir que no sabe. *[Ensayar la última:
según la corrida puede encontrar o no un artículo relacionado.]*

---

## 4. Cómo está hecho (12:00 – 14:30)

**En pantalla:** el diagrama de arquitectura (`plandefases.md`) y el ER
(`docs/modelo-datos.md`).

**Qué decir:**
- **Principio central: el LLM orquesta, el núcleo decide.** El modelo de lenguaje entiende el
  mensaje, elige la herramienta y sus argumentos, y repregunta lo que falta. Todo lo que es un
  número, una norma, una dosis o un registro sale de **código determinista** y de la base.
  Motivo: un dictamen tiene que ser reproducible y auditable, y un LLM puede inventar.
- **Agente con herramientas (tools):** LangChain / LangGraph (`create_agent`) con 14 tools
  (leer receta, validar producto, dictamen, limitaciones, marbete, normativa, agenda…). La
  respuesta final la arma un **formateador con plantillas** a partir de los resultados de las
  tools, nunca del texto libre del modelo.
- **Modelo:** Gemini 3.5 Flash-Lite (texto e imagen). Las llamadas internas de las tools
  rotan entre varias API keys cuando se agota la cuota.
- **Base de datos:** un solo PostgreSQL con tablas relacionales, **JSONB** para lo
  semiestructurado y **pgvector** para los embeddings (y `pg_trgm` para parecidos de texto).
  Sin tablas planas: cada cosa que se busca por significado tiene su tabla.
- **RAG:** embeddings multilingües (`paraphrase-multilingual-mpnet-base-v2`) sobre 76.000
  fragmentos de marbetes y la normativa; búsqueda híbrida (similitud + BM25) y reformulación de
  la pregunta; verificación de citas.
- **Datos:** crawl del registro de SENASA (7.370 productos, 4.000 marbetes en PDF); normativa
  en PDF y reglas de distancia en un CSV revisado a mano; pronóstico de Open-Meteo.
- **Canales:** WhatsApp Cloud API (webhook FastAPI) y un notebook de chat para probar sin Meta.
- **Calidad:** ~960 tests automáticos (sin red, con modelos falsos), una base de test aislada,
  y una **evaluación conversacional** en la que otro agente simula un operario y un analista
  revisa las conversaciones.

---

## 5. Problemas que surgieron y cómo los resolvimos (14:30 – 17:00)

Elegir 4 o 5; cada uno en dos frases (problema → solución).

1. **El LLM puede inventar datos legales.** → Separación LLM/núcleo, citas verificadas en
   código, y "ausencia de evidencia no es aprobación": si un chequeo no corrió, no hay APTA.
2. **El operario pregunta con otras palabras que el documento** ("volver a entrar al lote" /
   "reingresar al área tratada"). → Búsqueda híbrida (similitud + BM25) y el LLM reformula la
   pregunta con los términos técnicos antes de buscar. En la evaluación con 40 marbetes, la
   recuperación pasó de 68 % a 81 % y a 95 %.
3. **La foto no entra como argumento de una tool** (una imagen son ~100.000 tokens). → La
   tool recibe la imagen "ligada" desde el canal; el LLM solo decide llamarla.
4. **Costo y cuota gratuita de Gemini** (~11.000 tokens por turno). → Descripciones más
   cortas y turnos que terminan en la tool: −58 % de tokens por turno.
5. **Validar por la ubicación exacta del lote no funcionaba** (el único polígono disponible era
   la mancha urbana, no el campo). → Cambio de diseño: se informa la distancia mínima según la
   localidad, el tipo de aplicación y la banda.
6. **Normas sin texto oficial** (fallos judiciales, una ordenanza conocida por la prensa). →
   Se cargan desde un resumen con su fuente, y las distancias en un CSV revisado a mano.
7. **Las pruebas con usuarios revelaron errores que los tests no veían** (el filtro por banda
   estaba invertido; "¿qué banda tiene X?" iba a buscar al marbete). → Evaluación
   conversacional con un simulador y pruebas con Gemini real antes de cada cambio.
8. *Opcional:* los tests borraban la base de desarrollo → base de test aislada; "cm3" sin el
   "³" no se reconocía → normalización de unidades (el parser de dosis pasó de 67 % a 83 % de
   los usos del registro).

---

## 6. Cierre (17:00 – 18:00)

**Qué decir:**
- **Qué logra:** respuestas al instante, en lenguaje de campo, siempre con la fuente, y que
  dice "no sé" antes que inventar.
- **Límites conocidos:** normativa cargada de 3 localidades (el resto, solo la provincial);
  algunas normas desde fuentes secundarias; 461 marbetes escaneados sin texto; la consulta
  libre de normativa falla con preguntas muy generales; el pronóstico es informativo.
- **Próximos pasos:** cargar más municipios; OCR de marbetes escaneados; avisos automáticos
  antes de aplicar; integrarlo con el resto del proyecto final *[completar]*.
- Agradecimiento y cierre.

---

## Recorte a 15 minutos

Sacar: el listado de productos de 3.4, el opcional de 3.5, el caso "no cuento con esa
información" de 3.7 (se puede nombrar sin mostrar), mostrar 3.3 solo con la agenda, y dejar 4
problemas en la sección 5 (1, 2, 5 y 7).
