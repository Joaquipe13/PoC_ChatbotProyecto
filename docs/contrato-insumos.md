# Contrato de insumos manuales

Formato de los datos que carga el equipo a mano (capas SIG y normativa). Transcrito y **congelado** desde la skill `agente-fitosanitarios` al cerrar la Fase 1: cualquier cambio a partir de acá va documentado en `DECISIONES.md`, no se cambia en silencio.

## Estructura de carpetas

```
data/insumos/
├── <provincia>/                      p. ej. santa-fe
│   ├── ley-NNNNN-AAAA.pdf            normativa provincial (una o más)
│   ├── reglas.csv                    opcional (reglas de la normativa provincial)
│   └── <jurisdiccion_id>/            municipio de esa provincia, p. ej. san-carlos-centro
│       ├── localidad.geojson         límite + zonas protegidas, EPSG:4326
│       ├── ordenanza-914-2018.pdf    <tipo>-<numero>-<anio>.pdf
│       └── reglas.csv
└── normativa-general/
    └── nacional/
        ├── ley-NNNNN-AAAA.pdf
        └── reglas.csv                opcional
```

**Cambio (19/09/2026, ver `DECISIONES.md`):** antes las localidades estaban en `localidades/` y la normativa provincial en `normativa-general/provincial/<provincia>/`. Ahora cada municipio vive dentro de la carpeta de su provincia, junto a la normativa provincial. `normativa-general/` queda solo para la nacional.

- `provincia` y `jurisdiccion_id` (nombres de carpeta): minúsculas, sin tildes, palabras separadas por guion. Son la clave que une geometría, normativa y reglas entre sí y con la base (`territorio.localidad.jurisdiccion_id`, `territorio.provincia.nombre`).
- PDFs: `<tipo>-<numero>-<anio>.pdf`, con `tipo` ∈ `ordenanza | decreto | resolucion | ley`. De ahí sale la cita ("Ordenanza 914/2018") y el ámbito (municipal/provincial/nacional) sale de la carpeta que lo contiene. Solo normas vigentes; si una fue modificada, va también la modificatoria o el texto ordenado completo.

## `localidad.geojson`

`FeatureCollection` en EPSG:4326 (lat/lon). Cada feature lleva la propiedad `tipo`:

- `limite`: **exactamente una**, `Polygon` o `MultiPolygon`, con propiedades `nombre` y `provincia` (igual al nombre de la carpeta de la provincia que la contiene).
- `escuela`, `curso_agua`, `zona_urbana` u `otro`: zonas protegidas, con propiedad `nombre`. Pueden ser `Point`, `LineString` o `Polygon` (una escuela como punto, un arroyo como línea); la distancia se calcula igual en cualquier caso.

## `reglas.csv`

Columnas: `tipo_zona, tipo_aplicacion, bandas, distancia_min_m, norma, articulo, observaciones`.

Una fila significa: **dentro de `distancia_min_m` de una zona `tipo_zona` no se puede hacer una aplicación `tipo_aplicacion` con productos de las bandas indicadas.**

- `tipo_zona`: los valores de `tipo` del GeoJSON, salvo `limite`.
- `tipo_aplicacion`: `terrestre | aerea | todas`.
- `bandas`: `todas` o lista con `;` (`Ia;Ib;II`).
- `norma`: nombre de un PDF de la misma carpeta, sin extensión (`ordenanza-914-2018`).
- `articulo`: número.
- `observaciones`: condiciones que el modelo no cubre (aviso previo, horarios, viento). El dictamen las muestra como advertencia, no como bloqueo.

Cada zona protegida pertenece a la localidad de su carpeta, pero la búsqueda de distancias considera también zonas de localidades vecinas dentro de `RADIO_BUSQUEDA_ZONAS_M`.

## Validaciones

Implementadas en `src/fitosanitarios/insumos/validador.py` (Fase 3). Dos niveles: **falla** (bloquea la carga de esa localidad/norma) y **avisa** (registra advertencia, no bloquea).

### Falla (bloquea)

| # | Condición |
|---|---|
| F1 | A una carpeta de localidad le falta `localidad.geojson`, al menos un PDF, o `reglas.csv`; o a la carpeta de una provincia le falta al menos un PDF de normativa provincial. |
| F2 | El GeoJSON no tiene exactamente un feature `limite`. |
| F3 | El GeoJSON trae un `tipo` de feature desconocido (fuera de `limite`, `escuela`, `curso_agua`, `zona_urbana`, `otro`). |
| F4 | Una geometría es inválida (self-intersecting, coordenadas fuera de rango) o cae fuera del bounding box de Argentina. |
| F5 | Una fila de `reglas.csv` cita en `norma` un PDF que no está en la misma carpeta. |
| F6 | Un nombre de archivo o de carpeta no respeta la convención (`<tipo>-<numero>-<anio>.pdf`, carpeta en minúsculas/sin tildes/con guiones). |
| F7 | La `provincia` del `limite` de una localidad no coincide con la carpeta de la provincia donde está. |

### Avisa (no bloquea)

| # | Condición |
|---|---|
| A2 | Una zona protegida queda a más de `RADIO_BUSQUEDA_ZONAS_M` del límite de su propia localidad. |
| A3 | Un PDF no tiene texto extraíble (escaneado): se marca `requiere_revision=true` en `territorio.articulo` y sigue por OCR (Fase 3). |

## Datos sintéticos para desarrollo y tests

`tests/fixtures/insumos/`: 2-3 localidades sintéticas completas (GeoJSON + PDF de prueba + `reglas.csv`), con la misma estructura que los datos reales. El desarrollo y los tests de las Fases 3, 5 y 6 corren 100 % contra estas fixtures; los datos reales del equipo son un insumo que se carga aparte, no una dependencia del código para poder avanzar (ver `plandefases.md`, Fase 3).

## Mínimo para arrancar vs. mínimo para cerrar

- **Para arrancar la Fase 3** (carga real, en paralelo con la Fase 2): 2 localidades completas + las leyes provinciales correspondientes.
- **Para cerrar la Fase 5**: las 10 localidades del caso de estudio tienen que estar cargadas.

Esto es responsabilidad del equipo que provee los insumos, no una tarea de código de este plan (ver `plandefases.md`, sección 6 / decisión abierta #7).
