# Ordenanza municipal — Sastre y Ortiz (Santa Fe)

## Datos de la norma

| Campo | Detalle |
|---|---|
| Localidad | Sastre y Ortiz, Departamento San Martín, Santa Fe |
| Norma | Ordenanza municipal que regula el uso de agroquímicos (número y carátula formal sin confirmar; se cita como N° 1174/19 por la fecha de sanción) |
| Sanción | 23 de septiembre de 2019 |
| Relación con el Fallo Sastre (2020) | Anterior al fallo judicial que impuso 1.000 m para aplicación terrestre (ver `fallo-sastre-2020.md`); no encontré ninguna fuente que indique que una norma haya derogado formalmente a la otra |

⚠️ **Fuente:** nota de prensa (Infosastre), no el texto oficial de la ordenanza. No se pudo verificar número de artículo, texto exacto de las excepciones, ni la equivalencia precisa entre "ligeramente peligroso"/"moderadamente peligroso" y las bandas toxicológicas oficiales (Ia/Ib/II/III/IV). La nota indica que esta ordenanza deroga normas anteriores sobre el tema, pero no cita cuáles.

## Esquema de distancias (terrestre, por tramos)

| Tramo | Terrestre | Aérea |
|---|---|---|
| 0–200 m | Prohibición total | — |
| 200–1.200 m | Solo productos "ligeramente peligrosos" | — |
| > 1.200 m | Productos "moderadamente peligrosos" también autorizados | — |
| 0–3.000 m | — | Prohibición total |

**Mapeo de categorías usado en `reglas.csv`** (inferido, no confirmado contra el texto original):
- "Ligeramente peligroso" → banda III (azul), tramo 1.000–1.200 m (los primeros 1.000 m ya están cubiertos por el Fallo Sastre, más estricto).
- "Moderadamente peligroso" → banda II (amarilla), autorizada más allá de los 1.200 m; banda III también permitida en ese tramo.
- Banda roja (Ia/Ib, alta toxicidad): prohibida en todo el distrito, sin límite de distancia.
- Banda IV (verde) no fue mencionada en la fuente consultada: no se incluyó una fila para no inventar el dato.

## Otras disposiciones (no cargadas en `reglas.csv`, sin distancia asociada)

- Buffer adicional de 200 m desde la escuela rural N° 693 "Bernardino Rivadavia" (Estación km 465) — sí cargado como regla de tipo `escuela`.
- Horarios permitidos: noviembre-abril 5 a 22 h, mayo-octubre 8 a 19 h.
- Prohibida la fumigación nocturna.

## Dónde conseguir el texto oficial

- **Boletín Oficial de la Municipalidad de Sastre y Ortiz**: [sastreciudad.gob.ar/boletin-oficial](https://sastreciudad.gob.ar/boletin-oficial/) — buscar N° 1174/19.
- **Concejo Deliberante de Sastre**: `hcmsastre@hotmail.com` / (03406) 480090 · 480110.

## Fuente

- [Aprueban nueva Ordenanza que regula el uso de agroquímicos — Infosastre](https://www.infosastre.com.ar/noticias/sastre/24553-aprueban-nueva-ordenanza-que-regula-el-uso-de-agroqu%C3%ADmicos.html)
