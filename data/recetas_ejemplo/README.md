# Recetas de ejemplo

Imágenes **sintéticas** (generadas con `scripts/generar_recetas_ejemplo_el_trebol.py`, con productos y dosis reales del catálogo de SENASA) para probar la lectura de recetas desde `notebooks/chat.ipynb`, en local o en Colab. Las recetas no dicen la localidad: después de mandar la foto, decile al bot "en El Trébol".

| Archivo | Qué es | Resultado esperado |
|---|---|---|
| `02_apta_aerea_banda_ii.jpg` | Reg. SENASA 41881, banda II, aplicación aérea, 170 cm3/ha | APTA, con distancia mínima de 3.000 m a zona urbana (Ordenanza 841/2010 de El Trébol, art. 7) |
| `03_observada_dosis_fuera_de_rango.jpg` | Reg. SENASA 41759, banda III, 150 g/ha (registrada: 70 g/ha) | OBSERVADA por dosis |

Fotos propias: se pueden dejar en esta carpeta, pero no se versionan (`.gitignore`), porque una receta real puede traer datos de un productor o de un ingeniero agrónomo. Las recetas que usan los tests automáticos están en `tests/fixtures/recetas/`.
