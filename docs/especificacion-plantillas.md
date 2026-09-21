# Especificación de plantillas

Una entrada por cada valor de `RespuestaAgente.tipo` (`src/fitosanitarios/dominio/modelos.py`). El formateador determinista (Fase 7, `src/fitosanitarios/orquestador/formateador.py`) arma el texto de cada plantilla a partir de los **artifacts de las tools ejecutadas en el turno**, nunca del texto libre del LLM (ver skill, "Contratos": `RespuestaAgente.tipo` + artifacts → formateador). Formato WhatsApp general: `*negrita*`, listas con `-`/`1.`, sin tablas ni encabezados markdown, ≤ 4096 caracteres por mensaje, coma decimal con unidad separada, fechas `dd/mm/aaaa`, sección `*Fuentes*` al final si hay citas.

> **Nota sobre el conteo de plantillas:** el contrato `RespuestaAgente` (skill, sección "Contratos") define **9** valores posibles de `tipo`, incluido `ayuda`. La sección 3.4 del prompt de planificación y la Fase 7 de `plandefases.md` mencionan "8 plantillas" enumerando los mismos 8 casos que abajo tienen ejemplo en la skill, sin `ayuda`. Se toma esto como una omisión menor de esas dos enumeraciones (probablemente porque `ayuda` es el caso trivial), no como una exclusión deliberada: acá se especifican las 9. Si en la Fase 7 se decide que `ayuda` no hace falta como tipo aparte (podría fusionarse con `fuera_de_dominio` o resolverse sin pasar por el formateador), es una decisión a tomar y documentar en esa fase, no en esta.

## `confirmacion_receta`

**Cuándo:** después de `leer_receta`, antes de evaluar. Siempre pide Confirmar/Corregir.

**Campos que usa:** artifact de `leer_receta` (`Receta` con `confianza_por_campo`); campos con confianza baja se marcan con ⚠️ en vez de mostrarse como dato firme.

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

## `dictamen`

**Cuándo:** resultado de `evaluar_viabilidad_legal`.

**Campos que usa:** artifact `Dictamen` (`resultado`, `observaciones[].descripcion`+`citas`, productos con su estado, `citas` generales).

```
*Dictamen* — Lote 4 · San Carlos Centro
*Resultado:* ❌ OBSERVADA

*Observaciones*
1. Distancia a escuela insuficiente: el lote está a 80 m y el mínimo es 100 m.
2. Dosis de Glifosato Full 48 SL: 5 L/ha, por encima del rango registrado para soja (2–3 L/ha).

*Productos*
- Glifosato Full 48 SL · Reg. SENASA 12345 · Banda IV (verde) · autorizado para soja ✅

*Fuentes*
- Ordenanza 914/2018, art. 8 (San Carlos Centro)
- SENASA, Reg. 12345 (marbete)
```

## `consulta_producto`

**Cuándo:** resultado de `validar_producto_registro` (consulta puntual) o `consultar_productos` (listado).

**Campos que usa:** artifact `ResultadoTool.datos` (lista de candidatos/productos con registro, banda, dosis).

```
*Productos registrados para yuyo colorado en soja* (3 de 23)
1. Marca A · Reg. SENASA 12345 · Banda III (azul) · 1,5–2 L/ha
2. Marca B · Reg. SENASA 23456 · Banda IV (verde) · 2–3 L/ha
3. Marca C · Reg. SENASA 34567 · Banda IV (verde) · 0,8–1 L/ha
Es lo que figura en el registro; qué aplicar lo define la receta del ingeniero agrónomo.

*Fuentes*
- SENASA, vademécum (datos al 11/09/2026)
```

## `consulta_normativa`

**Cuándo:** resultado de `responder_consulta_normativa`.

**Campos que usa:** artifact `ResultadoTool.datos` (veredicto corto generado por el LLM **solo** con los fragmentos recuperados) + `citas` verificadas en código.

```
*No.* En San Carlos Centro la distancia mínima para aplicación terrestre a establecimientos educativos es de 100 m.

*Fuentes*
- Ordenanza 914/2018, art. 8 (San Carlos Centro)
```

## `consulta_articulo`

**Cuándo:** resultado de `consultar_articulo` ("¿qué dice el artículo 33?").

**Campos que usa:** artifact `ResultadoTool.datos` (`norma_legible`, `numero`, `jurisdiccion_id`, `partes`). El texto del artículo va **literal** (sin pasar por el LLM), con las líneas cortadas del PDF ya unidas y un renglón por inciso. No lleva la intro del LLM ni sección *Fuentes*: el encabezado ya cita norma, artículo y jurisdicción. Si el PDF trae más de un texto con el mismo número, se muestran todos ("texto 1 de 2"). Una norma con un artículo de más de 4096 caracteres se parte por oraciones en varios mensajes. Con el número en varias normas la tool repregunta cuál (lista); sin el número o sin encontrarlo, `repregunta` / `no_resuelto`.

```
*Ley 055297/2017, art. 51 (santa-fe)*
Las excepciones a que refiere el Artículo 33 de la Ley Nº 11.273 podrán establecerse por ordenanza únicamente en los siguientes casos:
a) La aplicación aérea de productos fitosanitarios de clases toxicológicas C y D podrá realizarse dentro del radio de los quinientos ( 500 ) metros cuando resulte imposible.
b) La aplicación aérea de clase B solo podrá efectuarse dentro del sector comprendido entre los 500 y los 3.000 metros.

⚠️ Busqué en la normativa provincial y nacional. Si es de una ordenanza, decime la localidad
```

## `limitaciones`

**Cuándo:** resultado de `listar_limitaciones` ("¿qué limitaciones hay en El Trébol?", "¿puedo aplicar a 1000 m bajo alguna condición?").

**Campos que usa:** artifact `ResultadoTool.datos`, armado con las reglas de `reglas.csv` (no por similitud): `prohibiciones` (`N`), `condicionales` (`S`) y, si se dio una distancia, `restricciones` (cada prohibición que alcanza esa distancia con las excepciones que permitirían aplicar). Una excepción de una norma más general no se ofrece contra la prohibición de una norma más local (la excepción de la ley provincial "por ordenanza" no levanta la prohibición de la ordenanza). Las reglas leídas del PDF llevan un aviso de verificación.

Sin distancia:

```
*Limitaciones en Rosario*

⚠️ No se cuenta con la normativa municipal de Rosario: las limitaciones son las de la normativa provincial

*Aplicación aérea*
- Zona urbana · banda II: a menos de 3000 m no se puede aplicar (Ley 11273/1995, art. 33)

*Aplicación terrestre*
- Zona urbana · bandas Ia, Ib, II: a menos de 500 m no se puede aplicar (Ley 11273/1995, art. 34)

*Excepciones*
- Zona urbana · aérea · banda II: se puede aplicar desde 500 m, si: <condiciones> (Ley 055297/2017, art. 51)

*Fuentes*
- Ley 11273/1995, art. 33 (santa-fe)
...
```

Con distancia (`distancia_m`):

```
*A 1000 m en Rosario*

- Zona urbana · aérea · banda II: a menos de 3000 m no se puede aplicar (Ley 11273/1995, art. 33)
  *Excepciones posibles:*
  - Zona urbana · aérea · banda II: se puede aplicar desde 500 m, si: <condiciones> (Ley 055297/2017, art. 51)
```

## `repregunta`

**Cuándo:** faltan parámetros requeridos (con o sin tool ejecutada — si no se ejecutó ninguna tool, `RespuestaAgente.faltantes` viene poblado directamente).

**Campos que usa:** `RespuestaAgente.faltantes` o `ResultadoTool.faltantes` de la última tool ejecutada (hasta 3 `CampoFaltante`, priorizados).

```
Para evaluar la receta me faltan 2 datos:
1. *Localidad*: ¿En qué localidad o municipio se va a realizar la aplicación?
2. *Tipo de aplicación*: elegí una opción.
[Terrestre] [Aérea]
```

## `fuera_de_dominio`

**Cuándo:** el orquestador clasifica el mensaje como fuera de dominio, **antes** de llamar cualquier tool.

**Campos que usa:** ninguno de tool (no hay artifacts); texto fijo, `RespuestaAgente.intro` puede variar levemente pero el cuerpo es la plantilla.

```
Solo puedo ayudarte con recetas de fitosanitarios: leer y validar recetas, verificar productos registrados en SENASA y responder dudas sobre la normativa de aplicación de las localidades cargadas. ¿Me mandás una receta o una consulta sobre eso?
```

## `no_resuelto`

**Cuándo:** una tool devuelve `estado="no_resuelto"` con un `MotivoNoResuelto`.

**Campos que usa:** `ResultadoTool.motivo` (vía `DESCRIPCION_MOTIVO`), `ResultadoTool.chequeos_no_realizados` / lo que sí se evaluó (de otras tools del mismo turno si las hubo).

```
⚠️ *No pude completar la evaluación*
*Qué no pude determinar:* la distancia mínima a zonas protegidas.
*Por qué:* el lote está fuera de las localidades cargadas en el sistema.
*Qué sí evalué:* el producto está registrado y autorizado para soja ✅
*Qué podés hacer:* consultar la ordenanza de esa localidad o al área de ambiente del municipio.
```

## `ayuda`

**Cuándo:** el usuario saluda o pide ayuda genérica ("qué podés hacer", "hola"), sin que sea ni una consulta de dominio ni claramente fuera de dominio.

**Campos que usa:** ninguno de tool; texto fijo que resume las capacidades del bot (mismo espíritu que `fuera_de_dominio` pero en tono de bienvenida, no de rechazo).

```
Hola 👋 Soy el asistente de recetas fitosanitarias. Puedo:
- Leer una foto de tu receta y decirte si es apta para aplicar.
- Buscar si un producto está registrado en SENASA.
- Responder dudas sobre la normativa de aplicación de tu localidad, mostrarte el texto de un artículo o decirte qué limitaciones tiene.
Mandame una foto de receta o contame qué necesitás.
```

**Pendiente de decidir en Fase 7:** si este tipo se mantiene separado o se resuelve como un caso particular de `fuera_de_dominio` con `intro` distinta (ver nota al principio de este documento).

## `error`

**Cuándo:** una tool devuelve `estado="error"` (falla técnica real, no un estado esperable) o el propio orquestador captura una excepción no manejada.

**Campos que usa:** ninguno del dominio (nunca se exponen detalles internos/stacktraces al usuario); el detalle real va al log estructurado por turno, no al mensaje.

```
⚠️ Tuve un problema técnico y no pude procesar tu mensaje. Probá de nuevo en unos minutos; si sigue fallando, contactá a soporte.
```
