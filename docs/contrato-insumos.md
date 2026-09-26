# Contrato de insumos manuales

Formato de los datos que carga el equipo a mano (capas SIG y normativa). Transcrito y **congelado** desde la skill `agente-fitosanitarios` al cerrar la Fase 1: cualquier cambio a partir de acá va documentado en `DECISIONES.md`, no se cambia en silencio.

## Estructura de carpetas

```
data/insumos/
├── reglas.csv                        las reglas de distancia de todas las carpetas
├── <provincia>/                      p. ej. santa-fe
│   ├── ley-NNNNN-AAAA.pdf            normativa provincial (una o más)
│   └── <jurisdiccion_id>/            municipio de esa provincia, p. ej. san-carlos-centro
│       ├── localidad.geojson         límite + zonas protegidas, EPSG:4326
│       └── ordenanza-914-2018.pdf    <tipo>-<numero>-<anio>.pdf
└── normativa-general/
    └── nacional/
        └── ley-NNNNN-AAAA.pdf        solo para consultas: no aporta reglas al dictamen
```

**Cambio (19/09/2026, ver `DECISIONES.md`):** antes las localidades estaban en `localidades/` y la normativa provincial en `normativa-general/provincial/<provincia>/`. Ahora cada municipio vive dentro de la carpeta de su provincia, junto a la normativa provincial. `normativa-general/` queda solo para la nacional.

**Cambio (21/09/2026, ver `DECISIONES.md`):** un único `reglas.csv` en la raíz de `data/insumos/` reemplaza a los `reglas.csv` por carpeta.

**Cambio (26/09/2026, ver `DECISIONES.md`, "Pronóstico del tiempo al agendar"):** dos archivos opcionales nuevos en la raíz de `data/insumos/`, que carga `insumos/loader_meteorologia.py` (después de `loader_geo` y `loader_normativa`):
- `localidades.csv` — `provincia, jurisdiccion, centro_lat, centro_lon, fuente`: el centro de cada localidad, para pedir el pronóstico del tiempo. Una localidad que no está cargada es un error.
- `reglas_viento.csv` — `provincia, jurisdiccion, viento_max_kmh, norma, articulo, descripcion`: normas que se refieren al viento, que se mencionan junto al pronóstico si el viento pronosticado supera `viento_max_kmh`. `provincia` vacía para una norma provincial, como en `reglas.csv`. Una norma o un artículo que no están cargados son un error.

**Cambio (22/09/2026, ver `DECISIONES.md`, "Localidades y normas sin fuente oficial: Sastre y San Jorge"):** `localidad.geojson` pasa a ser opcional, y una norma puede citarse desde un `.md` en vez de un PDF cuando no hay texto oficial disponible (un fallo judicial, o una norma citada solo por fuente secundaria).

- `provincia` y `jurisdiccion_id` (nombres de carpeta): minúsculas, sin tildes, palabras separadas por guion. Son la clave que une geometría, normativa y reglas entre sí y con la base (`territorio.localidad.jurisdiccion_id`, `territorio.provincia.nombre`).
- Normas: `<tipo>-<numero>-<anio>.pdf`, con `tipo` ∈ `ordenanza | decreto | resolucion | ley`. De ahí sale la cita ("Ordenanza 914/2018") y el ámbito (municipal/provincial/nacional) sale de la carpeta que lo contiene. Solo normas vigentes; si una fue modificada, va también la modificatoria o el texto ordenado completo.
- **Sin texto oficial disponible:** la misma convención de nombre, pero `.md` en vez de `.pdf`, y `tipo` puede ser también `fallo` (un fallo judicial; `numero` es un identificador, no necesariamente un número de expediente — p. ej. `fallo-sastre-2020.md`). El `.md` es el texto de referencia completo (puede incluir fuentes, salvedades de alcance, mapeos inferidos); se carga tal cual, sin OCR, y **no se chunkea en artículos** (no tiene encabezados "Artículo N" reales): sirve para que `reglas.csv` cite la norma, pero no aparece en `consultar_articulo` ni en `responder_consulta_normativa` (RAG por similitud). Usar `.md` es una salida de emergencia para normas sin fuente oficial, no un reemplazo del PDF cuando este existe.

## `localidad.geojson`

**Opcional** (22/09/2026, ver `DECISIONES.md`): sin él, la localidad igual se carga en `territorio.localidad` (para que le cuelguen normas y reglas de distancia), sin límite ni zonas protegidas -- el dictamen ya no compara la ubicación del lote contra geometría (Fase 12), así que solo se pierde la resolución de jurisdicción por punto-en-polígono, que no está en uso.

`FeatureCollection` en EPSG:4326 (lat/lon). Cada feature lleva la propiedad `tipo`:

- `limite`: **exactamente una**, `Polygon` o `MultiPolygon`, con propiedades `nombre` y `provincia` (igual al nombre de la carpeta de la provincia que la contiene).
- `escuela`, `curso_agua`, `zona_urbana` u `otro`: zonas protegidas, con propiedad `nombre`. Pueden ser `Point`, `LineString` o `Polygon` (una escuela como punto, un arroyo como línea); la distancia se calcula igual en cualquier caso.

## `reglas.csv` (uno solo, en la raíz de `data/insumos/`)

Reúne las reglas de distancia de todas las jurisdicciones. Es opcional: una jurisdicción sin filas usa el respaldo descripto abajo.

Columnas: `provincia, jurisdiccion, tipo_zona, tipo_aplicacion, banda_toxicologica, distancia_min_m, permitido, condiciones, norma, articulo, observaciones`.

**A qué jurisdicción pertenece una fila:**

| Norma de… | `provincia` | `jurisdiccion` |
|---|---|---|
| un municipio o comuna | carpeta de su provincia (`santa-fe`) | carpeta de la localidad (`el-trebol`) |
| una provincia | vacía | carpeta de la provincia (`santa-fe`) |
| la Nación | vacía | `ARGENTINA` o `NACIONAL` |

Se aceptan mayúsculas o minúsculas y `_` por `-` (`SANTA_FE` = `santa-fe`).

**`permitido`: `N` o `S`.**

- **`N` (prohibición):** dentro de `distancia_min_m` de una zona `tipo_zona` no se puede hacer una aplicación `tipo_aplicacion` con productos de esas bandas. Es lo único que usan el dictamen y el agendado: bloquea directamente.
- **`S` (regla condicional):** a partir de `distancia_min_m` se puede aplicar si se cumplen las `condiciones`. Nunca bloquea ni ablanda una `N`; sirve para consultas ("¿puedo aplicar a 1.000 m bajo alguna condición?": el sistema ofrece las `S` cuya distancia mínima ya se respeta, con sus condiciones). Suele describir una excepción: la `N` fija el radio general y la `S` dice desde qué distancia y bajo qué condiciones se puede aplicar dentro de él. Una `S` cuya norma no fija distancia mínima lleva `0` y lo aclara en `observaciones`.

Resto de las columnas:

- `tipo_zona`: los valores de `tipo` del GeoJSON, salvo `limite`.
- `tipo_aplicacion`: `terrestre | aerea | todas`.
- `banda_toxicologica`: `todas` o una o más bandas separadas por `;` (`Ia;Ib;II`).
- `condiciones`: el requisito legal de una fila `S` (ordenanza, terreno que impida equipos terrestres…). Vacío en las `N`.
- `norma`: nombre de un PDF (o, sin fuente oficial, un `.md`) de la carpeta de esa jurisdicción, sin extensión (`ordenanza-914-2018`, `fallo-sastre-2020`). Una norma citada desde otra jurisdicción no se encuentra.
- `articulo`: número. Vacío si la regla no cita uno.
- `observaciones`: aviso que el modelo no cubre (aviso previo, horarios, viento). El dictamen lo muestra como advertencia, no como bloqueo.

**Sin filas para una jurisdicción, la fuente es el PDF.** Al cargar (`loader_reglas`) las distancias de esa carpeta se leen del texto de sus artículos, de forma **determinista** (un parser, sin LLM) y solo si son prohibiciones firmes con una única distancia, zona y clases explícitas; excepciones, condiciones, rangos y redacciones ambiguas se descartan. Se guardan como `N` con `fuente='pdf_extraido'` y la respuesta avisa que se leyeron del texto de la norma y que hay que verificarlas. Con al menos una fila en `reglas.csv`, el CSV es la única fuente de esa jurisdicción y es la vía para cargar lo que el parser no toma (excepciones como filas `S`, distancias en tablas). **La normativa nacional nunca se lee del PDF:** está para consultas, así que sin filas nacionales no aporta reglas al dictamen.

**Cómo armar las filas de una carpeta.** El CSV revisado por una persona es la fuente confiable; la lectura del PDF queda como respaldo. Para no empezar de cero: `uv run python -m fitosanitarios.insumos.borrador_reglas --data data/insumos` escribe en cada carpeta un `reglas.borrador.csv` (filas que el extractor tomó, con `provincia` y `jurisdiccion` ya completas y la columna `oracion` para auditarlas) y un `reglas.borrador-pendientes.txt` (oraciones con distancia que descartó: excepciones, condiciones, rangos, tablas). Si el `reglas.csv` ya tiene filas de esa carpeta, imprime además qué difiere. Se copian las filas que sirvan al `reglas.csv`, se completan a mano y se recarga con `loader_reglas`. Las filas de una jurisdicción reemplazan por completo lo que leería el PDF: tienen que incluir todas las reglas, también las que el extractor sí toma. Los borradores están en `.gitignore`.

Cada zona protegida pertenece a la localidad de su carpeta, pero la búsqueda de distancias considera también zonas de localidades vecinas dentro de `RADIO_BUSQUEDA_ZONAS_M`.

## Validaciones

Implementadas en `src/fitosanitarios/insumos/validador.py` (Fase 3). Dos niveles: **falla** (bloquea la carga de esa localidad/norma) y **avisa** (registra advertencia, no bloquea).

### Falla (bloquea)

| # | Condición |
|---|---|
| F1 | A una carpeta de localidad, o a la carpeta de una provincia, le falta al menos una norma (PDF o `.md`). |
| F2 | El GeoJSON no tiene exactamente un feature `limite`. |
| F3 | El GeoJSON trae un `tipo` de feature desconocido (fuera de `limite`, `escuela`, `curso_agua`, `zona_urbana`, `otro`). |
| F4 | Una geometría es inválida (self-intersecting, coordenadas fuera de rango) o cae fuera del bounding box de Argentina. |
| F5 | Una fila de `reglas.csv` cita en `norma` una norma que no está en la carpeta de su jurisdicción. |
| F6 | Un nombre de archivo o de carpeta no respeta la convención (`<tipo>-<numero>-<anio>.pdf` o `.md`, carpeta en minúsculas/sin tildes/con guiones). |
| F7 | La `provincia` del `limite` de una localidad no coincide con la carpeta de la provincia donde está. |
| F8 | Una fila de `reglas.csv` no respeta el formato (`permitido`, `tipo_aplicacion` o banda desconocidos, distancia no numérica, columna faltante). |
| F9 | Una fila de `reglas.csv` es de una jurisdicción que no tiene carpeta. |

### Avisa (no bloquea)

| # | Condición |
|---|---|
| A2 | Una zona protegida queda a más de `RADIO_BUSQUEDA_ZONAS_M` del límite de su propia localidad. |
| A3 | Un PDF no tiene texto extraíble (escaneado): se marca `requiere_revision=true` en `territorio.articulo` y sigue por OCR (Fase 3). |
| A4 | Una provincia o localidad no tiene filas en `reglas.csv`: sus distancias se leerán del texto de los PDF (fuente `pdf_extraido`). No aplica a la nacional. |
| A5 | Una carpeta de localidad no tiene `localidad.geojson` (22/09/2026): se carga sin límite ni zonas protegidas. |

## Datos sintéticos para desarrollo y tests

`tests/fixtures/insumos/`: 2-3 localidades sintéticas completas (GeoJSON + PDF de prueba) y un `reglas.csv` único, con la misma estructura que los datos reales. El desarrollo y los tests de las Fases 3, 5 y 6 corren 100 % contra estas fixtures; los datos reales del equipo son un insumo que se carga aparte, no una dependencia del código para poder avanzar (ver `plandefases.md`, Fase 3).

## Mínimo para arrancar vs. mínimo para cerrar

- **Para arrancar la Fase 3** (carga real, en paralelo con la Fase 2): 2 localidades completas + las leyes provinciales correspondientes.
- **Para cerrar la Fase 5**: las 10 localidades del caso de estudio tienen que estar cargadas.

Esto es responsabilidad del equipo que provee los insumos, no una tarea de código de este plan (ver `plandefases.md`, sección 6 / decisión abierta #7).
