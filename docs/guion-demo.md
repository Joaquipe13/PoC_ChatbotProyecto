# Guion de demo (defensa del TP2)

Orden de presentación sugerido, con el mensaje exacto a mandar, el resultado
esperado y qué señalar en cada caso. Todos los casos corren contra datos
reales: catálogo SENASA real (Fase 2) y la normativa real cargada de El Trébol,
Sastre y San Jorge, más la Ley 11.273 de Santa Fe y su decreto — no hay
fixtures ni LLM fake en la demo.

**Plan B si el túnel de WhatsApp no está disponible**: mandar los mensajes
desde `notebooks/chat.ipynb` (chat con el mismo orquestador), o correr
`notebooks/demo_e2e.ipynb` con kernel limpio. El mismo guion sirve para los
dos casos; solo cambia el canal por el que se manda el mensaje.

Requisitos antes de arrancar: `docker compose up -d db`, al menos una
`GEMINI_API_KEY_*` real en `.env` (con varias, el agente pasa a la siguiente
si una se queda sin cuota).

**Cambio (26/09/2026):** los casos usaban San Carlos Centro y Colonia Vecina,
localidades y normas inventadas para los tests que no estaban en la base de
desarrollo. Se sacaron y los casos pasaron a El Trébol y Sastre; las salidas de
abajo son las que dio el bot con Gemini real ese día.

## Los 6 casos obligatorios

### 1. Dictamen APTA

> "Quiero validar la receta completa: Flyer 10 Ec en soja, 170 cm3/ha, terrestre, en El Trébol, contra chinche de la alfalfa"

**Esperado** (Gemini real, 26/09/2026):

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

Si se sigue con "sí, agendala para el lunes a las 9", la confirmación trae el
pronóstico del tiempo de esa franja y, si el viento pronosticado supera los
8 km/h, menciona la Ordenanza 841/2010, art. 4 (ver `DECISIONES.md`, "Pronóstico
del tiempo al agendar").

**Qué señalar:** el producto, el cultivo, la dosis y la localidad se sacaron de
un solo mensaje en lenguaje natural; el núcleo (no el LLM) resolvió el producto
contra SENASA, comparó la dosis (170 cm³/ha) contra el rango registrado
(160-180 cm³/ha) para soja + chinche de la alfalfa, y eligió las reglas de la
localidad. La distancia **informa** qué exige la norma: ya no se compara contra
la ubicación exacta del lote.

**Nota (Fase 10):** el "cm3" sin el superíndice "³" (como lo escribe
cualquier operario desde el celular) recién se reconoce a partir de esta
fase — antes daba `NO_EVALUABLE` por "unidad no reconocida" (ver
`DECISIONES.md`). Si por algún motivo el LLM extrae `dosis_unidad` con otra
grafía no cubierta, el respaldo verificado y determinístico está en
`tests/tools/evaluar_viabilidad_legal/test_tool.py::test_dictamen_apta_producto_registrado_dosis_ok`.

### 2. Dictamen OBSERVADA (dosis fuera de rango)

> "Quiero validar la receta completa: Flyer 10 Ec en soja, 500 cm3/ha, terrestre, en El Trébol, contra chinche de la alfalfa"

**Esperado:** `tipo=dictamen`, resultado `❌ OBSERVADA` por la dosis (500 cm³/ha,
muy por encima del rango registrado de 160-180). Muestra igual las condiciones
de aplicación, pero **no** ofrece agendar una receta observada.

**Qué señalar:** el dictamen sigue citando el registro del producto aunque el
resultado sea negativo, y lista *todas* las observaciones si hay más de una
(p. ej. un cultivo no autorizado para el producto).

**Respaldo determinístico:**
`tests/tools/evaluar_viabilidad_legal/test_tool.py::test_dictamen_observada_por_dosis_fuera_de_rango`.

### 3. Consulta de productos (listado)

> "¿Qué productos hay registrados para yuyo colorado en soja?"

**Esperado** (Gemini real, 28/09/2026: una llamada con `cultivo="soja"` y
`adversidad="yuyo colorado"`):

```
*Productos para soja contra yuyo colorado*

(10 de 167)
1. *2,4db 100 Aca* · Reg. SENASA 30005 · Banda III · 1 a 1,25 l/hm2
2. *2,4-db 93.1 Brilliance* · Reg. SENASA 41974 · Banda III · 5 dosis distintas según la plaga
3. *Aceite Quimeco Plus* · Reg. SENASA 37227 · Banda IV · 250 cm3 por ha
...

⚠️ Solo aparecen los productos que tienen cultivos y plagas cargados en SENASA; puede haber otros registrados sin esos datos

Es lo que figura en el registro; qué aplicar lo define la receta del ingeniero agrónomo.
```

Una fila por producto con el total real; cierra con la aclaración de que
nunca recomienda.

**Qué señalar:** distinto de `validar_producto_registro` (caso 1): acá el
operario no nombra un producto puntual, pide un listado por adversidad y
cultivo. Los filtros se combinan libremente (aptitud, banda, firma, marca,
principio activo) y una distancia al pueblo se traduce en las bandas que se
pueden aplicar ahí: "¿qué fungicidas para trigo puedo aplicar con avión a 1500
m de El Trébol?" lista solo los de banda III y IV, con la ordenanza que lo fija.

### 4. Repregunta agrupada

> "Quiero evaluar si puedo aplicar en mi lote"

**Esperado:** `tipo=repregunta`, pide hasta 3 datos agrupados (típicamente
cultivo, productos y localidad/tipo de aplicación) en un solo mensaje, cada
uno con su pregunta sugerida. Ninguna tool se llama todavía.

**Qué señalar:** la repregunta es agrupada (no una pregunta por turno) y
prioriza los datos que más desbloquean, según la skill.

### 5. Fuera de dominio

> "¿Va a llover mañana en Rosario?"

**Esperado:** `tipo=fuera_de_dominio`, respuesta fija explicando el alcance
del bot (recetas, SENASA, normativa, y desde la Fase 9 también
vehículos/eventos/agenda), sin llamar ninguna tool.

**Qué señalar:** es requisito de la plataforma (Meta no admite bots de
propósito general desde el 15/01/2026), no solo una limitación de producto.

### 6. Localidad sin normativa municipal: respaldo en la provincial

> "Quiero evaluar riesgo para una aplicación en Rosario, Santa Fe, Flyer 10 Ec, soja, terrestre, 2 L/ha, contra chinche de la alfalfa"

**Esperado:** condiciones de aplicación con la distancia mínima a zona urbana
de la **normativa provincial** (500 m, Ley 11273/1995 art. 34) y una aclaración
explícita: "⚠️ No se cuenta con la normativa municipal de Rosario: la distancia
se basa en la normativa provincial".

**Nota:** usar una unidad de dosis inequívoca (`L/ha`) acá a propósito -- con
"cm3/ha" en este mensaje puntual se observó que el LLM a veces repregunta
primero por la unidad en vez de evaluar directamente; no es un bug del núcleo
(la unidad se normaliza igual en el código, ver caso 1), es una elección del
LLM en ese momento -- variabilidad inherente, no determinística.

**Qué señalar:** el sistema nunca inventa una respuesta cuando no tiene la
normativa local: se apoya en la provincial y **lo dice**. Si no se menciona la
provincia, la pide (nunca la supone). Con una provincia no cargada ("en
Córdoba capital, Córdoba") responde `no_resuelto` / `JURISDICCION_NO_CUBIERTA`.

## Casos adicionales (si el jurado pide más o sobra tiempo)

### 7. Ambigüedad de producto

Si se pregunta por un nombre parcial o genérico de producto que matchea
varios candidatos, la tool devuelve una lista de opciones (`faltan_datos`,
`tipo_entrada="lista"`) en vez de elegir uno — nunca adivina. **Caso
límite conocido:** con un nombre genérico de principio activo en vez de
una marca puntual (p. ej. "¿el glifosato está habilitado para soja?"), el
LLM a veces rutea a `consultar_productos` en vez de a
`validar_producto_registro`, y como ese principio activo puede no
coincidir textualmente con ningún registro, el resultado real observado
es "no encontré productos con esos filtros" en vez de una lista de
candidatos — documentado como patrón conocido en `DECISIONES.md` (Fase 10),
no es exclusivo de este caso puntual. Para mostrar la ambigüedad de forma
confiable en vivo, usar un nombre de marca parcial real del catálogo en
vez de un principio activo genérico.

### 8. Consulta normativa con cita verificada

> "¿Se puede fumigar con viento en El Trébol?"

**Esperado** (Gemini real, 26/09/2026, igual en 3 de 3 corridas):
`tipo=consulta_normativa`, "*Depende.* Se prohíben las pulverizaciones cuando los
vientos superen los 8 km/hora y puedan producir derivas hacia la planta urbana",
citando la Ordenanza 841/2010, art. 4.

No usar "¿hay que avisar antes de aplicar en El Trébol?": contestó bien una vez
(art. 5) y después 0 de 4. La búsqueda trae primero artículos genéricos del
decreto y el art. 5 queda afuera, según cómo reformule Gemini.

Una pregunta de distancia ("¿a qué distancia de una escuela puedo aplicar en
Sastre?") no va por acá: la responde `listar_limitaciones` con la lista de
límites (200 m, Ordenanza 1174/2019).

**Advertencia conocida:** la recuperación por similitud (`RAG_UMBRAL_SIMILITUD`)
es sensible a la redacción exacta con la que el LLM orquestador arma el
argumento `pregunta` de la tool — no siempre es idéntica a como lo escribió
el operario (ver `DECISIONES.md`, Fase 8). Si no devuelve cita en el primer
intento, repetir la pregunta casi textual a la de arriba, o mostrar
`tests/tools/responder_consulta_normativa/test_tool.py::test_pregunta_con_respaldo_devuelve_cita_verificada`
como respaldo determinístico (la misma pregunta del viento, art. 4).

### 9. Extensiones (Fase 9)

> "Empecé a aplicar con la mosquito en el lote 4" → "Terminé de aplicar" → "¿qué tengo para hoy?"

Muestra `resolver_vehiculo` (interpreta "la mosquito" como "pulverizador
autopropulsado"), `registrar_evento` (inicio y fin) y `consultar_agenda`.
Verificado de punta a punta en `notebooks/demo_sin_whatsapp.ipynb`.

### 10. Seguimiento del dictamen: más info y agendar

Después del caso 1: "más info" → banda de cada producto y de la aplicación;
"sí, agendala" → pregunta la fecha; "agendala para el martes" → muestra la
agenda de ese día y pregunta el horario; "a las 8:30" → confirma. Las fechas
y horas las resuelve el código (`servicios/fechas.py`), no el LLM.

### 11. Consulta al marbete de un producto (RAG de marbetes)

> "¿Qué hago con los bidones vacíos de Vertimec?"

**Esperado:** `tipo=consulta_marbete`. Con Gemini real (26/09/2026): "*Vertimec* ·
Reg. SENASA 30116 — Los envases vacíos deben someterse a triple lavado o lavado
a presión, inutilizarlos perforándolos sin dañar la etiqueta y enviarse a
centros de acopio transitorio habilitados según la ley 27.279, estando
prohibido reutilizarlos, enterrarlos o quemarlos", con la fuente *SENASA, Reg.
30116 (marbete, pág. 10)*. Otras que contestaron bien el mismo día: "¿lo puedo
tirar junto con otro producto?" sobre Tordon D 30 (pág. 8) y "¿me puede quemar
el cultivo?" sobre Tordon D 30 (pág. 8).

**Qué señalar:** esto no está en el registro estructurado de SENASA (registro,
banda, cultivos y dosis): sale del texto del marbete en PDF, partido en
fragmentos por página. La búsqueda es solo dentro del marbete de ese producto, y
la página que cita el LLM se verifica en código contra lo recuperado; si no
está, no se muestra. Hay marbete para buscar en 3.217 de los 7.370 productos: el
resto no tiene marbete descargado o es un escaneo sin texto (no hay OCR).

### 12. Reformulación de la pregunta (modo prueba)

Requiere `MODO_DEMO_REFORMULACION=true` en `.env` y reiniciar el bot. Con eso,
las consultas al marbete y a la normativa se contestan dos veces en el mismo
mensaje: con la pregunta tal cual y con la reformulada.

> "¿Qué hago si se me vuelca Banvel en el galpón?"

**Esperado** (Gemini real, 26/09/2026): con la pregunta original, "⚠️ No pude
completar la consulta"; la pregunta reformulada agrega "derrame, contención,
absorción, limpieza de derrames, almacenamiento", y con esa contesta "Cubra el
derrame con tierra o arena, barra el material absorbente y colóquelo en
recipientes identificados para su destrucción. Luego, lave las superficies
contaminadas con agua jabonosa o carbonatada", con la fuente *SENASA, Reg.
30596 (marbete, pág. 8)*.

**Qué señalar:** el operario pregunta con sus palabras ("se me vuelca en el
galpón") y el marbete usa otras ("derrame"). Ni la similitud ni la búsqueda por
palabras encuentran la página con la pregunta tal cual; el LLM escribe los
términos que usaría el marbete y con eso aparece. En la evaluación con 40
marbetes, la recuperación pasó de 76 % a 95 % (ver `DECISIONES.md`,
"Reformulación de la pregunta").

**Advertencias (probado el 26/09/2026 con Gemini real, 8 preguntas):**

- Es el único de los 8 casos probados con un contraste claro. En la mayoría
  las dos respuestas son equivalentes: la pregunta tal cual ya encontraba la
  página.
- En normativa no mostró mejora. "¿Necesito una receta del ingeniero para
  aplicar?" en El Trébol contestó bien sin reformular (Ley 11.273, art. 28) y
  peor con la reformulación ("Depende… no hay información suficiente").
  "¿Qué me pasa si aplico sin receta?" en Sastre contestó a medias sin
  reformular y nada con la reformulación. No usar normativa para mostrar
  este caso.
- "¿Cuándo puedo volver a entrar al lote?" sobre Banvel no contesta en
  ninguno de los dos casos, aunque la pág. 5 dice "no reingresar al área
  tratada": ese fragmento tiene similitud 0,22-0,26, debajo del piso de 0,30
  que exige la búsqueda híbrida.
- Las respuestas de Gemini varían entre corridas: ensayar la pregunta antes
  de la defensa.
- Los casos 11 y 12 se probaron llamando a la tool directamente, con el
  producto y la pregunta ya separados. Por el chat, el orquestador arma el
  argumento `pregunta` y puede escribirlo distinto: ensayarlos por el canal
  que se vaya a usar en la defensa.

## Modelo de datos (para la parte de arquitectura de la defensa)

Mostrar `docs/modelo-datos.md`:

1. **Diagrama ER** (sección "Diagrama ER"): los tres schemas
   (`catalogo`, `territorio`, `operacion`) más `VEHICULO`/`EVENTO_APLICACION`
   de la Fase 9 — remarcar que no hay ninguna tabla genérica
   "documento + embedding", cada entidad tiene sus propias columnas
   relacionales, JSONB y `vector` según corresponda (ver skill, "Base de
   datos: relacional + JSONB + vectores").
2. **Dos consultas SQL de tools RAG explicadas** (sección "Consultas SQL de
   cada tool RAG"):
   - `validar_producto_registro`: filtro relacional (join a principios
     activos y usos registrados) + ranking combinado trigram/embedding
     sobre `catalogo.producto.marca` — mostrar cómo el umbral de
     `similarity()` decide `PRODUCTO_NO_ENCONTRADO`.
   - `evaluar_riesgo`: localidad resuelta por nombre (o provincia, si la
     localidad no tiene normativa propia) → reglas candidatas por
     localidad/provincia/nación con norma y artículo; la banda de la
     aplicación (la más peligrosa de la mezcla) y la distancia más
     restrictiva se calculan en Python — remarcar que el LLM nunca escribe
     ni ve este SQL, solo elige la tool y sus argumentos tipados.
   - `consultar_marbete` (si preguntan por los RAG): filtro por producto
     primero y similitud después, sobre `catalogo.fragmento_marbete`; el
     ranking híbrido (similitud + BM25) se arma en Python. Mostrar que los
     fragmentos cuelgan de su documento y su producto: no es una tabla
     genérica de "texto + embedding".

## Checklist final antes de la entrega

- [x] `uv run pytest -q` corre en verde (ver `README.md` para el comando exacto) — verificado dos corridas consecutivas al cerrar esta fase.
- [x] `USE_FIXTURES=false uv run python evals/run_evals.py` corrido y el resultado transcripto acá abajo (no se oculta si no llega al 90 %, ver `DIFICULTADES.md`).
- [x] `notebooks/demo_e2e.ipynb` corrido de punta a punta con kernel limpio (dos veces, con `SESION` única por corrida).
- [ ] `docker compose up -d db` y `.env` con `GEMINI_API_KEY_*` reales listos **el día de la defensa** (repetir esta verificación esa mañana, no asumir que sigue igual).

### Resultado de evals (última corrida antes de la entrega)

**79 % de exactitud de ruteo (23/29), reproducible en dos corridas
consecutivas.** Por debajo del objetivo de la skill (≥ 90 %) -- reportado
tal cual, sin inflar el número. Detalle de por qué en `DECISIONES.md`
(Fase 10): 3 de los 6 casos "incorrectos" en realidad terminan en una
`repregunta` sensata (la métrica solo mira qué tool se llamó primero, no el
resultado final de la conversación); los otros 3 son un patrón conocido
desde antes de esta fase (preguntar por un producto puntual sin mencionar
el cultivo, a veces mal ruteado a `consultar_productos` pese a que su
descripción ya dice explícitamente que no es para eso). 0 citas inventadas
y 100 % de dictámenes por plantilla siguen garantizados por construcción
(ver `evals/run_evals.py`, docstring), no dependen de esta corrida.
