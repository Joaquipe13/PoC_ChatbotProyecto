# Guion de demo (defensa del TP2)

Orden de presentación sugerido, con el mensaje exacto a mandar, el resultado
esperado y qué señalar en cada caso. Todos los casos corren contra datos
reales: catálogo SENASA real (Fase 2) y la normativa sintética de San Carlos
Centro/Colonia Vecina (Fase 3, ver `docs/validacion-insumos.md`) — no hay
fixtures ni LLM fake en la demo.

**Plan B si el túnel de WhatsApp no está disponible**: correr
`notebooks/demo_e2e.ipynb` con kernel limpio en vez del canal real. El
mismo guion sirve para los dos casos; solo cambia el canal por el que se
manda el mensaje (WhatsApp real vs. celda de la notebook).

Requisitos antes de arrancar: `docker compose up -d db`, al menos una
`GEMINI_API_KEY_*` real en `.env`.

## Los 6 casos obligatorios

### 1. Dictamen APTA

> "Quiero validar la receta completa: Flyer 10 Ec en soja, 170 cm3/ha, terrestre, en San Carlos Centro, contra chinche de la alfalfa"

**Esperado:** `tipo=dictamen`, resultado `✅ APTA`, sin observaciones, más las
*Condiciones de aplicación* de San Carlos Centro: banda II (amarilla) y la
distancia mínima a cada tipo de zona con la norma que la fija (zona urbana
300 m, Ley 13740/2017 art. 2; escuela 100 m, Ordenanza 914/2018 art. 8; curso
de agua 50 m, art. 10). Cita el registro SENASA de Flyer 10 Ec (reg. 41881)
y cierra ofreciendo más info (banda de cada producto) o agendar.

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
`tests/tools/test_evaluar_viabilidad_legal.py::test_dictamen_apta_producto_registrado_dosis_ok`.

### 2. Dictamen OBSERVADA (dosis fuera de rango)

> "Quiero validar la receta completa: Flyer 10 Ec en soja, 500 cm3/ha, terrestre, en San Carlos Centro, contra chinche de la alfalfa"

**Esperado:** `tipo=dictamen`, resultado `❌ OBSERVADA` por la dosis (500 cm³/ha,
muy por encima del rango registrado de 160-180). Muestra igual las condiciones
de aplicación, pero **no** ofrece agendar una receta observada.

**Qué señalar:** el dictamen sigue citando el registro del producto aunque el
resultado sea negativo, y lista *todas* las observaciones si hay más de una
(p. ej. un cultivo no autorizado para el producto).

**Respaldo determinístico:**
`tests/tools/test_evaluar_viabilidad_legal.py::test_dictamen_observada_por_dosis_fuera_de_rango`.

### 3. Consulta de productos (listado)

> "¿Qué productos hay registrados para yuyo colorado en soja?"

**Esperado:** `tipo=consulta_producto`, lista de 3 productos (Imazamox 70 Wg
Brilliance, Jafar 48 ×2 usos) con registro SENASA, banda y dosis. Cierra con
la aclaración "es lo que figura en el registro; qué aplicar lo define la
receta del ingeniero agrónomo" — nunca recomienda.

**Qué señalar:** distinto de `validar_producto_registro` (caso 1): acá el
operario no nombra un producto puntual, pide un listado por adversidad y
cultivo.

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
de la **normativa provincial** (300 m, Ley 13740/2017 art. 2) y una aclaración
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

> "¿A qué distancia de una escuela puedo aplicar por tierra en San Carlos Centro?"

**Esperado:** `tipo=consulta_normativa`, veredicto corto + regla (100 m para
aplicación terrestre) citando Ordenanza 914/2018, art. 8.

**Advertencia conocida:** la recuperación por similitud (`RAG_UMBRAL_SIMILITUD`)
es sensible a la redacción exacta con la que el LLM orquestador arma el
argumento `pregunta` de la tool — no siempre es idéntica a como lo escribió
el operario (ver `DECISIONES.md`, Fase 8). Si no devuelve cita en el primer
intento, repetir la pregunta casi textual a la de arriba, o mostrar
`tests/tools/test_responder_consulta_normativa.py::test_pregunta_con_respaldo_devuelve_cita_verificada`
como respaldo determinístico (misma pregunta, `jurisdiccion_id` explícito).

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
