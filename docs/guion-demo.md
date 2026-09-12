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

> "Quiero validar la receta completa: Flyer 10 Ec en soja, 170 cm3/ha, terrestre, lote -32.912,-60.642, contra chinche de la alfalfa"

**Esperado:** `tipo=dictamen`, resultado `✅ APTA`, sin observaciones. Cita
el registro SENASA de Flyer 10 Ec (reg. 41881) aunque cumpla — la skill
exige citar incluso lo que sí pasa.

**Qué señalar:** el producto, el cultivo, la dosis y la ubicación se
sacaron todos de un solo mensaje en lenguaje natural; el núcleo (no el LLM)
resolvió el producto contra SENASA, ubicó el lote en San Carlos Centro por
punto-en-polígono, y comparó la dosis (170 cm³/ha) contra el rango
registrado (160-180 cm³/ha) para soja + chinche de la alfalfa.

**Nota (Fase 10):** el "cm3" sin el superíndice "³" (como lo escribe
cualquier operario desde el celular) recién se reconoce a partir de esta
fase — antes daba `NO_EVALUABLE` por "unidad no reconocida" (ver
`DECISIONES.md`). Si por algún motivo el LLM extrae `dosis_unidad` con otra
grafía no cubierta, el respaldo verificado y determinístico está en
`tests/tools/test_evaluar_viabilidad_legal.py::test_dictamen_apta_producto_registrado_dosis_ok_lejos_de_zonas`.

### 2. Dictamen OBSERVADA (distancia insuficiente + dosis fuera de rango)

> "Quiero validar la receta completa: Flyer 10 Ec en soja, 500 cm3/ha, terrestre, lote -32.92877865019107,-60.6505, contra chinche de la alfalfa"

**Esperado:** `tipo=dictamen`, resultado `❌ OBSERVADA` con **dos**
observaciones (igual que la plantilla de referencia de la skill):
1. Distancia a la Escuela N.° 12 insuficiente (~80 m, mínimo 100 m para
   aplicación terrestre — Ordenanza 914/2018, art. 8).
2. Dosis muy por encima del rango registrado (500 cm³/ha vs. 160-180).

**Qué señalar:** el dictamen lista *todas* las observaciones, no se detiene
en la primera — y sigue citando el registro del producto aunque el
resultado sea negativo.

**Respaldo determinístico:**
`tests/tools/test_evaluar_viabilidad_legal.py::test_dictamen_observada_por_distancia_insuficiente`
y `::test_dictamen_observada_por_dosis_fuera_de_rango` (casos separados,
cada uno con una sola observación, por si conviene mostrarlos por
separado en vez de combinados).

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
cultivo, productos y ubicación/tipo de aplicación) en un solo mensaje, cada
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

### 6. No resuelto (jurisdicción no cubierta)

> "Quiero evaluar riesgo para un lote en -34.6, -58.4 (Buenos Aires), Flyer 10 Ec, soja, terrestre, 2 L/ha, contra chinche de la alfalfa"

**Esperado:** `tipo=no_resuelto`, motivo `JURISDICCION_NO_CUBIERTA` ("el
punto del lote no cae en ningún polígono de localidad cargado").

**Nota:** usar una unidad de dosis inequívoca (`L/ha`) acá a propósito -- el
punto de este caso es la cobertura geográfica, no la dosis. Con "cm3/ha" en
este mensaje puntual se observó que el LLM a veces repregunta primero por
la unidad en vez de evaluar directamente; no es un bug del núcleo (la
unidad se normaliza igual en el código, ver caso 1), es una elección del
LLM en ese momento -- variabilidad inherente, no determinística.

**Qué señalar:** el sistema nunca inventa una respuesta cuando no tiene
cobertura geográfica — dice explícitamente que no puede, en vez de fingir
un dictamen.

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
   - `evaluar_riesgo`: tres consultas encadenadas (localidad por bbox →
     zonas protegidas en el radio, incluidas las de localidades vecinas →
     reglas candidatas por localidad/provincia/nación) con la geometría
     exacta resuelta en Python (`estimate_utm_crs()`), no en SQL — remarcar
     que el LLM nunca escribe ni ve este SQL, solo elige la tool y sus
     argumentos tipados.

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
