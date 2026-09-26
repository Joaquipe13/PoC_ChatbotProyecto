# Validación de insumos — primera carga

> **Registro histórico (26/09/2026).** Las fixtures sintéticas que usa este reporte (San Carlos Centro, Colonia Vecina, Ley 13740/2017, Ley 27302/2016 y sus ordenanzas, todas inventadas) se borraron. Desde esa fecha `tests/fixtures/insumos/` es una copia congelada de los insumos reales (El Trébol, Sastre, San Jorge, Ley 11.273 y su decreto), ver `DECISIONES.md`. Lo de abajo describe la primera corrida tal como fue.

> Estructura de carpetas actualizada el 19/09/2026 (municipios dentro de la carpeta de su provincia, ver `docs/contrato-insumos.md`). Los resultados de carga de abajo son de la primera corrida y siguen valiendo: solo cambiaron las rutas.

Reporte de la primera carga real del pipeline de insumos (Fase 3). **No hay insumos reales del equipo todavía** (capas SIG y normativa de las 10 localidades del caso de estudio, ver `plandefases.md` sección 6) — este reporte corre el pipeline completo contra las **fixtures sintéticas** de `tests/fixtures/insumos/`, que tienen la misma estructura y pasan las mismas validaciones que exigirán los datos reales. Cuando el equipo suba las localidades reales, se corre este mismo proceso sobre `data/insumos/` y se actualiza este documento con el resultado real.

## Insumos usados (sintéticos)

- `santa-fe/san-carlos-centro/`: límite, 3 zonas protegidas (escuela, curso de agua, zona urbana), `ordenanza-914-2018.pdf` (3 artículos), 3 filas en `reglas.csv`. Mismos nombres que usan los ejemplos de referencia de la skill (Ordenanza 914/2018, art. 8, escuela a distancia mínima de 100 m) para tener continuidad con esos casos en fases futuras.
- `santa-fe/colonia-vecina/`: límite, 1 zona protegida (escuela), `ordenanza-45-2019.pdf` (1 artículo), 1 fila en `reglas.csv`. Localidad limítrofe, para tener un segundo caso y poder probar más adelante (Fase 5) el filtro por jurisdicción y las zonas de localidades vecinas.
- `santa-fe/` (normativa provincial, en la carpeta de la provincia): `ley-13740-2017.pdf` (3 artículos), 2 filas en `reglas.csv` (una prohibición N de zona urbana y una condicional S, sin localidad asociada).
- `normativa-general/nacional/`: `ley-27302-2016.pdf` (2 artículos), sin filas en `reglas.csv` — a propósito: la normativa nacional es solo para consultas y no aporta reglas al dictamen.
- `reglas.csv` (raíz de `data/insumos/`, uno solo para todas las jurisdicciones): 6 filas, 5 prohibiciones (N) y 1 condicional (S). Ver `docs/contrato-insumos.md`.

Todo el contenido de estos PDFs es ficticio (generado para esta fixture), no transcribe normativa real.

## Validación (`validador.py`)

```
uv run python -c "
from pathlib import Path
from fitosanitarios.insumos.validador import validar_insumos
for clave, r in validar_insumos(Path('tests/fixtures/insumos')).items():
    print(clave, 'válido' if r.es_valido else 'con errores', r.errores, r.advertencias)
"
```

Resultado: las 4 carpetas (`santa-fe/san-carlos-centro`, `santa-fe/colonia-vecina`, `santa-fe`, `normativa-general/nacional`) validan sin errores ni advertencias.

## Carga (`loader_geo.py` → `loader_normativa.py` → `loader_reglas.py`, en ese orden)

```
docker compose up -d db
uv run python -m fitosanitarios.insumos.loader_geo --data tests/fixtures/insumos
uv run python -m fitosanitarios.insumos.loader_normativa --data tests/fixtures/insumos
uv run python -m fitosanitarios.insumos.loader_reglas --data tests/fixtures/insumos
```

Resultado real (12/09/2026, Postgres local vía Docker):

| Paso | Resultado |
|---|---|
| `loader_geo` | 2 localidades (`san-carlos-centro` id 2, `colonia-vecina` id 1) |
| `loader_normativa` | 4 normas, 9 artículos, 0 con `requiere_revision` (todos los PDF sintéticos tienen capa de texto) |
| `loader_reglas` | 5 reglas de distancia |

Verificación cruzada (join `regla_distancia → norma → articulo → localidad`):

| Localidad | Tipo de zona | Aplicación | Distancia mín. | Norma | Artículo |
|---|---|---|---|---|---|
| san-carlos-centro | escuela | terrestre | 100 m | ordenanza-914-2018 | 8 |
| san-carlos-centro | escuela | aérea | 200 m | ordenanza-914-2018 | 9 |
| san-carlos-centro | curso_agua | todas | 50 m | ordenanza-914-2018 | 10 |
| colonia-vecina | escuela | terrestre | 150 m | ordenanza-45-2019 | 5 |
| (provincial, sin localidad) | zona_urbana | todas | 300 m | ley-13740-2017 | 2 |

El filtro por jurisdicción excluye correctamente artículos de otra localidad: los artículos de `san-carlos-centro` (8, 9, 10) no incluyen el artículo 5 de `colonia-vecina`, verificado en `tests/insumos/test_loaders_integracion.py::test_filtro_por_jurisdiccion_excluye_articulos_de_otra_localidad`.

## Pendiente

- Cargar las localidades reales apenas el equipo las suba a `data/insumos/<provincia>/` (mínimo 2 completas + provinciales para poder empezar a probar la Fase 5 con datos reales; las 10 antes de cerrar esa fase, ver `plandefases.md`).
- Probar el camino de OCR con un PDF escaneado real: Tesseract no está instalado en la máquina de desarrollo de esta sesión, así que `extraer_texto_o_ocr` nunca ejecutó el branch de OCR de verdad (ver DIFICULTADES.md). El código maneja la ausencia de Tesseract sin romper (marca `requiere_revision=True` y sigue), pero el resultado real del OCR no está validado.
- Actualizar este documento con los números reales una vez cargada la normativa real.
