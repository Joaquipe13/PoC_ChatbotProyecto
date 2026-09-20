# Recetas de ejemplo para probar `leer_receta`

Carpeta para subir fotos reales (o escaneos) de recetas fitosanitarias y probarlas a mano contra el canal web (`http://localhost:8001/`, con `USE_FIXTURES=false`) o contra WhatsApp.

- Formatos: JPG/PNG, como los acepta `leer_receta` (ver skill, "Canal WhatsApp: gotchas": hasta 5 MB).
- Nunca se versionan (`.gitignore`): pueden traer datos reales de un productor o ingeniero agrónico, aunque el proyecto no los use.
- No confundir con `tests/fixtures/recetas/`: esas son sintéticas y sí están versionadas, porque las usan los tests automáticos (`pytest`) y no pueden tener datos reales.
