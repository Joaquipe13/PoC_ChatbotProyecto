# Matriz de parámetros de las tools

Los argumentos de las 14 tools tal como están en el código (`src/fitosanitarios/tools/<tool>/tool.py`, clase `...Args`), qué hace cada una cuando falta algo y en qué tipo de respuesta termina. Lo que lee el LLM para elegir la tool y completar los argumentos está en `tools/<tool>/prompts.py` (`DESCRIPCION`); lo que lee el operario, en `tools/<tool>/mensajes.py`. Actualizado al 27/09/2026.

Fuentes para completar un parámetro, en este orden: **mensaje actual → receta en curso → turnos previos**. Nunca por suposición (ver skill, "Matriz de parámetros"). Los textos del operario (fechas, horas, tipo de aplicación, banda, equipo) se pasan **tal como los dijo**: los interpreta el código, no el LLM.

## Resumen

| Tool | Requeridos | Opcionales | Si falta | `tipo` de respuesta |
|---|---|---|---|---|
| `leer_receta` | la foto (va ligada al turno, sin argumentos para el LLM) | — | no aplica: con foto, se llama siempre primero | `confirmacion_receta` |
| `completar_receta` | al menos un dato de la receta | cultivo, lote, localidad, tipo de aplicación, adversidad, superficie, dosis por producto | sin receta leída en la conversación: pide la foto | `confirmacion_receta` |
| `validar_producto_registro` | producto | cultivo, adversidad, dosis + unidad | producto ambiguo: lista de candidatos | `consulta_producto` |
| `consultar_productos` | al menos un filtro: cultivo, adversidad, principio activo, aptitud, banda, firma, marca, o localidad + distancia | cualquier combinación de esos; tipo de aplicación, provincia | distancia sin localidad: lista de las cargadas. Filtro que no está en el registro: se omite y se avisa | `consulta_producto` |
| `consultar_marbete` | producto, pregunta | — | producto ambiguo: lista de candidatos | `consulta_marbete` |
| `evaluar_riesgo` | tipo de aplicación, productos, cultivo, dosis + unidad | localidad, provincia, adversidad | localidad: lista de las cargadas | la elige el modelo: `dictamen` o `detalle_bandas` |
| `evaluar_viabilidad_legal` | tipo de aplicación, productos con dosis, cultivo | localidad, provincia, adversidad, superficie | localidad: lista de las cargadas | `dictamen` |
| `responder_consulta_normativa` | pregunta | localidad (`jurisdiccion_id`), provincia, tipo de aplicación, tipo de zona | localidad: lista de las cargadas | `consulta_normativa` |
| `consultar_articulo` | número de artículo | norma, localidad, provincia | número en varias normas: lista para elegir | `consulta_articulo` |
| `listar_limitaciones` | — | localidad, provincia, tipo de aplicación, banda, tipo de zona, distancia, producto | localidad: lista de las cargadas | `limitaciones` |
| `resolver_vehiculo` | descripción | — | no repregunta: `VEHICULO_NO_ENCONTRADO` | la elige el modelo (`consulta_vehiculo`) |
| `registrar_evento` | acción | vehículo y lote (para iniciar), id de receta | iniciar sin vehículo o lote: los pide | `evento_registrado` |
| `consultar_agenda` | — | fecha o días (default: hoy) | no aplica | `agenda` |
| `agendar_aplicacion` | fecha y hora (las pregunta la tool) | localidad, datos de la receta | sin fecha: pregunta el día. Sin hora: muestra la agenda de ese día y pregunta el horario | `agendar_aplicacion` |

**Localidad** (todas las que la reciben, `servicios/ubicacion.py`): sin localidad, o con un nombre que coincide con varias, se pregunta con la lista de las cargadas. Un municipio o comuna de Santa Fe sin normativa propia cargada se resuelve con la normativa provincial (y la respuesta lo aclara); un nombre que no figura se vuelve a pedir.

Doce tools terminan el turno apenas corren (`return_direct=True`) y su `tipo` sale de la tabla `orquestador/respuesta_directa.py::TIPO_POR_TOOL`: si la tool devolvió `no_resuelto` va a `no_resuelto`, y si devolvió `faltan_datos` va a `repregunta` (salvo `agendar_aplicacion`, cuya plantilla muestra lo que falta junto con la agenda del día). Las dos que pasan por el modelo son `evaluar_riesgo` (su resultado puede mostrarse como condiciones de aplicación o como la banda de cada producto, según de qué se venía hablando) y `resolver_vehiculo` (alimenta a otra tool).

## `leer_receta`

```python
class LeerRecetaArgs(BaseModel):
    imagen_base64: str  # imagen ya descargada del media de WhatsApp, en base64
```

En el agente se usa la versión **ligada** (`crear_tool_leer_receta_ligada`): la foto del turno queda en una clausura y la tool no tiene argumentos, porque el LLM no puede devolver una imagen como argumento (límite de tokens de salida; ver DECISIONES.md). Solo está en la lista de tools cuando el mensaje trae una foto, y el middleware `LeerLaFotoPrimero` (`orquestador/agente.py`) obliga a que sea la primera llamada del turno.

- Si a la receta le falta un dato obligatorio (cultivo, localidad, tipo de aplicación, producto, dosis, lote o superficie; `servicios/receta.py`), no ofrece confirmar: pregunta lo que falta y muestra lo que pudo leer.
- Una foto que no es una receta, o que no se lee: `IMAGEN_ILEGIBLE` ("📷 No pude leer una receta en esa foto").

## `completar_receta`

```python
class DosisDeProducto(BaseModel):
    producto: str | None = None  # el nombre, si lo dijo; sin él, el producto sin dosis
    dosis: str

class CompletarRecetaArgs(BaseModel):
    cultivo: str | None = None
    lote: str | None = None
    localidad: str | None = None
    tipo_aplicacion: str | None = None
    adversidad: str | None = None
    superficie_ha: float | None = None
    dosis: list[DosisDeProducto] = []
```

Para los datos que faltaban o una corrección ("soja, en Sastre", "la dosis es 200 cc"). Aplica lo que dijo el operario sobre la **última receta de la conversación tomada del artifact de la tool anterior**, no de lo que recuerde el LLM, y vuelve a mostrarla: con lo que todavía falte preguntado, o completa para confirmar.

## `validar_producto_registro`

```python
class ValidarProductoRegistroArgs(BaseModel):
    producto_nombre: str
    cultivo: str | None = None  # sin cultivo: solo registro y banda
    adversidad: str | None = None
    dosis_valor: float | None = None
    dosis_unidad: str | None = None
```

Un producto puntual: si está registrado, su banda y su registro ("¿qué banda tiene el Tordon D 30?", sin cultivo), si está autorizado para un cultivo y su dosis registrada para ese cultivo. "¿Cuál es la dosis correcta?" después de un aviso de dosis viene acá, con el producto y el cultivo de la conversación. Si el nombre coincide con varios productos, devuelve la lista para elegir.

Si SENASA no publica los usos del producto (6 de cada 7 productos), no es un "no resuelto": muestra el registro y la banda, dice que la dosis no se puede verificar y, si el producto tiene marbete con texto, busca ahí la dosis para ese cultivo (el RAG de `consultar_marbete`, `servicios/marbete.py`) y cita la página.

## `consultar_productos`

```python
class ConsultarProductosArgs(BaseModel):
    cultivo: str | None = None
    adversidad: str | None = None
    principio_activo: str | None = None
    aptitud: str | None = None       # "fungicidas", "herbicidas o insecticidas", "curasemillas"
    banda: str | None = None         # una o varias, o su color
    banda_maxima: str | None = None  # "III" o "azul" incluye III y IV
    firma: str | None = None         # empresa registrante
    marca: str | None = None         # parte del nombre comercial
    localidad: str | None = None     # con distancia_m: filtra por las bandas permitidas
    provincia: str | None = None     # solo si la tool la pidió
    tipo_aplicacion: str | None = None  # sin él, una respuesta por tipo
    distancia_m: float | None = None    # siempre a la zona urbana
```

Listado de lo registrado, con cualquier combinación de filtros ("¿qué hay para yuyo colorado en soja?", "fungicidas de Syngenta banda verde"). Informa, no recomienda. Una fila por producto, con el total real.

Una localidad y una distancia equivalen a filtrar por banda: las que se pueden aplicar a esa distancia de la zona urbana, con el mismo criterio que `listar_limitaciones` (`servicios/limitaciones.py::bandas_a_distancia`). "¿Qué fungicidas para trigo puedo aplicar con avión a 1500 m de El Trébol?" es una sola llamada. Sin tipo de aplicación, responde para aérea y terrestre; si las dos permiten las mismas bandas, es una sola lista que lo aclara. Las normas que deciden van en *Fuentes*.

Un filtro que no está en el registro (una firma o una aptitud que no existen, un cultivo que no se reconoce) se omite en la búsqueda y se avisa. Con cultivo o plaga, avisa que solo aparecen los productos con usos cargados en SENASA.

## `consultar_marbete`

```python
class ConsultarMarbeteArgs(BaseModel):
    producto: str
    pregunta: str
```

RAG sobre el marbete del producto: carencia, precauciones, mezclas, reingreso, primeros auxilios, envases vacíos. También para seguir hablando de un producto ya nombrado ("¿y los bidones vacíos?" después de preguntar por el Vertimec): el LLM pasa ese producto, y si la pregunta depende de algo dicho antes (el cultivo, la plaga) lo agrega a `pregunta`. No es para el registro, la dosis registrada ni la banda (`validar_producto_registro`). Antes de buscar, el LLM reformula la pregunta con los términos del marbete; la búsqueda es híbrida (similitud + BM25). Sin fragmentos que respalden la respuesta: `MARBETE_SIN_RESPALDO` ("No cuento con esa información").

## `evaluar_riesgo`

```python
class EvaluarRiesgoArgs(BaseModel):
    localidad: str | None = None
    provincia: str | None = None  # solo si la localidad no está cargada
    tipo_aplicacion: str  # "terrestre" | "aerea"
    productos: list[str]
    cultivo: str
    dosis_valor: float
    dosis_unidad: str
    adversidad: str | None = None
```

Para consultas sueltas con producto y dosis ("¿puedo aplicar Flyer a 170 cm3/ha por tierra en El Trébol?"): banda de la aplicación (la más peligrosa de los productos, tomada del registro), distancia mínima a cada zona según la normativa de la localidad, y dosis contra el rango registrado. **Si la dosis está fuera del rango, lo muestra primero como observación y no ofrece agendar** (igual que un dictamen OBSERVADA). No compara contra la ubicación del lote (ver DECISIONES.md).

## `evaluar_viabilidad_legal`

```python
class ProductoDeclarado(BaseModel):
    nombre: str
    dosis_valor: float
    dosis_unidad: str

class EvaluarViabilidadLegalArgs(BaseModel):
    localidad: str | None = None
    provincia: str | None = None  # solo si la localidad no está cargada
    tipo_aplicacion: str  # "terrestre" | "aerea"
    productos: list[ProductoDeclarado]
    cultivo: str
    adversidad: str | None = None
    superficie_ha: float | None = None
```

Dictamen (APTA / OBSERVADA / NO EVALUABLE) de la receta confirmada. Ejecuta adentro los chequeos de producto y de riesgo, sin depender de que el LLM encadene tools. No evalúa una receta incompleta ni un cultivo o tipo de aplicación que diga "NO FIGURA".

## `responder_consulta_normativa`

```python
class ResponderConsultaNormativaArgs(BaseModel):
    pregunta: str
    jurisdiccion_id: str | None = None  # localidad de la consulta o de la receta en curso
    provincia: str | None = None        # solo si la localidad no está cargada
    tipo_aplicacion: str | None = None
    tipo_zona: str | None = None
```

Preguntas de contenido sobre la normativa ("¿hay que avisar antes de aplicar?", "¿se puede fumigar con viento?"). RAG sobre fragmentos de las normas (incluidos fallos y normas sin PDF) y las reglas de `reglas.csv`, con la pregunta reformulada antes de buscar. El LLM responde solo con lo recuperado y cada cita se verifica en código. Sin respaldo: `NORMATIVA_SIN_RESPALDO` ("No cuento con esa información"). No es para la lista de distancias (`listar_limitaciones`) ni para el texto de un artículo por número (`consultar_articulo`).

## `consultar_articulo`

```python
class ConsultarArticuloArgs(BaseModel):
    numero_articulo: str        # "33", "5 bis"
    norma: str | None = None    # "ley 11273", "ordenanza 841/2010", como la nombró
    localidad: str | None = None
    provincia: str | None = None  # solo si la localidad no está cargada
```

Texto literal de un artículo por su número, sin pasar por el LLM. Sin localidad busca en la normativa provincial y nacional; si además no se nombró la norma, avisa que para una ordenanza hace falta la localidad (con la norma nombrada no avisa). Si el número está en varias normas y no se nombró ninguna, pregunta cuál. Una norma que no está cargada: lista las que sí.

## `listar_limitaciones`

```python
class ListarLimitacionesArgs(BaseModel):
    localidad: str | None = None
    provincia: str | None = None        # solo si la localidad no está cargada
    tipo_aplicacion: str | None = None  # como lo dijo: "aérea", "avión", "mosquito", "drone", "mochila"
    banda: str | None = None            # Ia/Ib/II/III/IV o su color; una o varias ("amarilla y verde")
    tipo_zona: str | None = None        # "zona urbana", "escuela", "curso de agua"
    distancia_m: float | None = None    # qué se puede a esa distancia
    producto: str | None = None         # su banda del registro manda sobre `banda`
```

Las limitaciones de la normativa de una localidad, de las reglas cargadas (no por similitud: la lista es completa y cada línea cita norma y artículo).

- Arriba de la lista, *Distancia mínima que rige*: por zona, tipo de aplicación y banda, la prohibición más restrictiva (el mismo criterio que el dictamen).
- **Con un producto**, la banda sale del registro de SENASA y **manda sobre una banda que venga junto** (el modelo llegó a suponerla); si no coincide, lo avisa. La banda dicha solo se usa si el producto no está en el registro, no tiene banda o es ambiguo. Un producto con variantes de distinta banda ("Roundup") y sin banda dicha: pregunta cuál.
- **Comparaciones en una sola llamada:** si nombra dos tipos o equipos ("avión o mosquito") no se filtra por tipo y la respuesta separa aérea y terrestre; con dos bandas ("amarilla y verde") se muestran las dos.
- **Equipos que las normas no nombran:** drone se muestra como aérea y mochila como terrestre, con un aviso.
- **Con `distancia_m`:** qué tipos de aplicación y bandas se pueden a esa distancia, cuáles solo con una excepción y cuáles no.
- Una localidad sin ordenanza cargada muestra la normativa provincial y lo aclara. Un filtro que no se entiende se ignora y se avisa.

## `resolver_vehiculo`

```python
class ResolverVehiculoArgs(BaseModel):
    descripcion: str  # "la mosquito", "el dron"
```

Identifica el equipo contra `catalogo.vehiculo`. No hace falta llamarla antes de `registrar_evento`, que la resuelve adentro. No repregunta: si no lo reconoce, `VEHICULO_NO_ENCONTRADO`.

## `registrar_evento`

```python
class RegistrarEventoArgs(BaseModel):
    accion: Literal["iniciar", "finalizar"]
    vehiculo: str | None = None  # solo para iniciar
    lote: str | None = None      # solo para iniciar
    receta_id: int | None = None
```

Inicio o fin de una aplicación real. `thread_id` sale del `config` del turno, no del LLM. Finalizar sin un inicio previo: `SIN_EVENTO_EN_CURSO`. Las horas se muestran en la hora local del operario ("domingo 27/09/2026, 10:14").

## `consultar_agenda`

```python
class ConsultarAgendaArgs(BaseModel):
    fecha: str | None = None  # "martes", "jueves y viernes", "semanal", "del 24/09 al 26/09"; None = hoy
```

Tareas de uno o varios días, con su estado. El texto se pasa entero y sin convertir: el código resuelve los días (`servicios/fechas.py`).

## `agendar_aplicacion`

```python
class AgendarAplicacionArgs(BaseModel):
    fecha: str | None = None      # "martes", "25/09"; o la fecha=AAAA-MM-DD que informó la tool antes
    hora: str | None = None       # "8", "8:30", "3 de la tarde"
    localidad: str | None = None  # para el pronóstico del tiempo
    numero: str | None = None
    cultivo: str | None = None
    lote: str | None = None
    superficie_ha: float | None = None
    tipo_aplicacion: str | None = None
```

El flujo lo decide el código: sin fecha pregunta el día; con fecha y sin hora muestra la agenda de ese día y pregunta el horario; con las dos, agenda. Si ya hay tareas a esa hora avisa, sin bloquear, con un solo aviso por cultivo y lote ("Ya tenías 6 aplicaciones de soja (sin lote) agendadas a las 09:00"). Con la localidad y una fecha dentro del horizonte suma el pronóstico de esa franja (Open-Meteo) y la regla de viento de la ordenanza si la hay; si el pronóstico no se puede obtener, agenda igual. `thread_id` sale del `config`.
