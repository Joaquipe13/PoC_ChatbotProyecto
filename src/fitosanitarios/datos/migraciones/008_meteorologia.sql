-- Pronóstico del tiempo al agendar una aplicación (26/09/2026, ver DECISIONES.md,
-- "Pronóstico del tiempo al agendar"). Es información para el operario: no controla ni
-- restringe nada (no cambia el dictamen ni impide agendar).
--
-- 1. El centro de cada localidad (lat/lon), para pedirle el pronóstico a la API. No es la
--    ubicación del lote ni un polígono: un punto por localidad, cargado desde
--    `data/insumos/localidades.csv`.
-- 2. `territorio.regla_viento`: las normas que se refieren al viento ("prohíbese pulverizar
--    con vientos de más de 8 km/h que puedan producir derivas hacia la planta urbana"),
--    cargadas desde `data/insumos/reglas_viento.csv`. Se mencionan como referencia junto
--    al pronóstico cuando el viento pronosticado supera su umbral.
-- 3. `operacion.receta.pronostico`: el pronóstico que se mostró al agendar, para que quede
--    registrado qué se sabía en ese momento.

ALTER TABLE territorio.localidad ADD COLUMN IF NOT EXISTS centro_lat NUMERIC;
ALTER TABLE territorio.localidad ADD COLUMN IF NOT EXISTS centro_lon NUMERIC;

CREATE TABLE IF NOT EXISTS territorio.regla_viento (
    id BIGSERIAL PRIMARY KEY,
    norma_id BIGINT NOT NULL REFERENCES territorio.norma (id) ON DELETE CASCADE,
    articulo_id BIGINT REFERENCES territorio.articulo (id) ON DELETE CASCADE,
    viento_max_kmh NUMERIC NOT NULL, -- por encima de esto la norma se refiere al viento
    descripcion TEXT NOT NULL -- qué dice, en una frase
);
CREATE INDEX IF NOT EXISTS ix_regla_viento_norma ON territorio.regla_viento (norma_id);

ALTER TABLE operacion.receta ADD COLUMN IF NOT EXISTS pronostico JSONB;
