# Guion de la presentación en video (15 a 20 minutos)

Guía para grabar el video del TP: el caso de negocio por arriba, los problemas que resuelve
el chatbot alternados con chats reales, las herramientas y los problemas que surgieron. Los
tiempos son orientativos (total ~17 min); si hay que recortar, las secciones marcadas como
*opcional* son las primeras en salir.

Las salidas de los chats son las que dio el bot con Gemini real el 26/09/2026. Gemini varía
entre corridas: **ensayar cada chat antes de grabar** (con `USE_FIXTURES=false`, una
conversación nueva por caso). El guion técnico caso por caso está en `docs/guion-demo.md`.

**Antes de grabar:** `docker compose up -d db`, canal web levantado
(`USE_FIXTURES=false uv run uvicorn fitosanitarios.canales.web.app_produccion:app --port 8001`),
"Nueva conversación" antes de cada caso, y los datos del proyecto final completados donde
dice *[completar]*.

---

## 1. Apertura (0:00 – 0:45)

**En pantalla:** título y el chat del canal web abierto.

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

## 3. Los problemas que resuelve, con ejemplos (3:00 – 11:30)

Para cada problema: una frase del problema, el chat en pantalla y una frase de qué hay que
notar. No leer la respuesta entera: señalar lo importante.

### 3.1 "Tengo que leer y cargar la receta" (3:00 – 4:00)

**Problema:** la receta viene en papel o foto; transcribirla es lento y se cometen errores.

**Chat:** adjuntar la foto de una receta de ejemplo (`data/recetas_ejemplo/01_apta_terrestre.jpg`).
*[Ensayar: no hay una salida verificada del 26/09 para este caso.]*

**Qué notar:** el bot lee la foto con un modelo multimodal y muestra lo que leyó para
**confirmar** antes de evaluar. Si falta un dato obligatorio (cultivo, localidad, dosis…), lo
pregunta en vez de adivinarlo.

### 3.2 "¿Puedo aplicar esto?" — el dictamen (4:00 – 5:30)

**Problema:** verificar el registro, el cultivo, la dosis y la normativa a mano.

**Chat:**
> Quiero validar la receta completa: Flyer 10 Ec en soja, 170 cm3/ha, terrestre, en El Trébol, contra chinche de la alfalfa

```
*Dictamen* — El Trébol
*Resultado:* ✅ APTA

*Condiciones de aplicación* — El Trébol · terrestre · banda II (amarilla)
- *Distancia mínima a zona urbana:* 500 m (Ley 11273/1995, art. 34)

*Fuentes*
- SENASA, Reg. 41881 (detalle API)

¿Agendamos la aplicación?
[BOTONES: Agendar | No, gracias]
```

Y con una dosis equivocada (500 cm3/ha):

```
*Resultado:* ❌ OBSERVADA

*Observaciones*
1. Dosis 500.0 cm3/ha: por encima del rango registrado (160.0-180.0 cm3/ha), 178% de desvío.
```

**Qué notar:** de una frase en lenguaje natural sale el producto, el cultivo, la dosis y la
localidad; pero **el dictamen no lo decide el LLM**: lo calcula código contra el registro de
SENASA y las reglas cargadas, y cada afirmación trae su fuente.

### 3.3 "¿A qué distancia del pueblo puedo tirar?" (5:30 – 7:00)

**Problema:** la distancia depende de la localidad, del tipo de aplicación y de la banda, y
la fijan varias normas a la vez.

**Chat:**
> voy a tirar Tordon D 30 con avion en Sastre, a cuanto del pueblo tengo que estar?

```
*Limitaciones en Sastre*

Para *Tordon D 30*: banda III (azul)

*Distancia mínima que rige*
- Zona urbana · aérea: banda III: 3000 m (Ordenanza 1174/2019)
- Escuelas · aérea: banda III: 200 m (Ordenanza 1174/2019)
```

**Qué notar:** el operario no dijo la banda: el bot la busca en el registro. La ley
provincial dice 500 m y la ordenanza de Sastre 3000 m: el bot dice **cuál manda** (la más
restrictiva). Con "drone" o "mochila", que las normas no nombran, avisa que es una
suposición.

*Opcional:* "¿es lo mismo aplicar por avión que por tierra en Sastre?" (compara los dos) o
"¿qué banda toxicológica tiene el Tordon D 30?" (→ "Banda III (azul)").

### 3.4 "¿Qué dice la etiqueta?" — el marbete (7:00 – 8:30)

**Problema:** la etiqueta del producto (el marbete) tiene carencias, precauciones, mezclas,
qué hacer ante un derrame… en un PDF de 10 páginas.

**Chat:**
> ¿Qué hago si se me vuelca Banvel en el galpón?

```
*Banvel* · Reg. SENASA 30596
Cubra el derrame con tierra o arena, barra el material absorbente y colóquelo en
recipientes identificados para su destrucción. Luego, lave las superficies contaminadas con
agua jabonosa o carbonatada.

*Fuentes*
- SENASA, Reg. 30596 (marbete, pág. 8)
```

**Qué notar:** es **RAG**: el bot busca en los 3.217 marbetes cargados y responde **solo** con
lo que encontró, citando la página. El operario dijo "se me vuelca en el galpón" y el marbete
dice "derrame": ver 5.2.

### 3.5 "¿Qué dice la ordenanza?" — y cuándo no sabe (8:30 – 9:45)

**Chat:**
> ¿Se puede fumigar con viento en El Trébol?

```
*Depende.* Se prohíben las pulverizaciones cuando los vientos superen los 8 km/hora y
puedan producir derivas hacia la planta urbana.

*Fuentes*
- Ordenanza 841/2010, art. 4 (el-trebol)
```

Y una que la normativa cargada no responde:
> ¿Hay que avisar antes de aplicar en El Trébol?

```
ℹ️ *No cuento con esa información*
No encontré en la normativa cargada nada que responda tu pregunta, así que no te doy una
respuesta sin una norma que la respalde.
```

**Qué notar:** la cita se **verifica en código** contra lo recuperado; si el modelo cita algo
que no se recuperó, se descarta. Sin fuente, el bot prefiere decir que no sabe.

### 3.6 Organizar el trabajo: agenda y pronóstico (9:45 – 11:30)

**Problema:** coordinar cuándo aplicar, y el viento y la lluvia cambian lo que conviene.

**Chat** (después del dictamen de 3.2):
> sí, agendala para el lunes a las 9

```
✅ *Aplicación agendada* — lunes 28/09/2026, 09:00 hs
- *Cultivo:* soja

*Pronóstico en El Trébol, de 07:00 a 11:00* (Open-Meteo, consultado el 26/09 19:18)
- Viento del sureste (empuja hacia el noroeste), 13 a 16 km/h, ráfagas de hasta 32 km/h
- Lluvia: 7,4 mm (probabilidad de hasta 50 %)
- Temperatura: 18 a 20 °C · humedad desde 90 %
📋 Ordenanza 841/2010, art. 4: prohíbe pulverizar con vientos de más de 8 km/h que puedan
producir derivas hacia la planta urbana.
Es un pronóstico: verificá el viento en el lote antes de empezar.
```

**Qué notar:** las fechas ("el lunes") las resuelve código, no el LLM. El pronóstico es
**información**, no un control: dice hacia dónde va la deriva y trae la norma de viento de la
localidad como referencia. *Opcional:* "¿qué tengo para esta semana?" (agenda) o "empecé a
aplicar con la mosquito en el lote 4" (registro de eventos).

---

## 4. Cómo está hecho (11:30 – 14:00)

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
- **Canales:** WhatsApp Cloud API (webhook FastAPI) y un canal web para probar sin Meta.
- **Calidad:** ~940 tests automáticos (sin red, con modelos falsos), una base de test aislada,
  y una **evaluación conversacional** en la que otro agente simula un operario y un analista
  revisa las conversaciones.

---

## 5. Problemas que surgieron y cómo los resolvimos (14:00 – 16:30)

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

## 6. Cierre (16:30 – 17:30)

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

Sacar: los opcionales de 3.3 y 3.6, el caso "no cuento con esa información" de 3.5 (se puede
nombrar sin mostrar), y dejar 4 problemas en la sección 5 (1, 2, 5 y 7).
