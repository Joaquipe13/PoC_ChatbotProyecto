-- Localidades sin `localidad.geojson` y normas sin PDF oficial (22/09/2026,
-- ver DECISIONES.md, "Localidades y normas sin fuente oficial: Sastre y San
-- Jorge"). El dictamen ya no compara la ubicación del lote contra geometría
-- (Fase 12), así que una localidad puede tener reglas de distancia sin tener
-- límite ni zonas protegidas cargados.

ALTER TABLE territorio.localidad ALTER COLUMN limite DROP NOT NULL;
ALTER TABLE territorio.localidad ALTER COLUMN bbox_min_lon DROP NOT NULL;
ALTER TABLE territorio.localidad ALTER COLUMN bbox_min_lat DROP NOT NULL;
ALTER TABLE territorio.localidad ALTER COLUMN bbox_max_lon DROP NOT NULL;
ALTER TABLE territorio.localidad ALTER COLUMN bbox_max_lat DROP NOT NULL;

-- 'fallo': una norma sin PDF -- un fallo judicial o una norma citada solo por
-- fuente secundaria (prensa) -- que se carga desde un `.md` de referencia en
-- vez de un PDF (ver loader_normativa.py). Sin capa de texto oficial: no se
-- chunkea en artículos, solo sirve para que `reglas.csv` la cite.
ALTER TABLE territorio.norma DROP CONSTRAINT IF EXISTS norma_tipo_check;
ALTER TABLE territorio.norma ADD CONSTRAINT norma_tipo_check
    CHECK (tipo IN ('ordenanza', 'decreto', 'resolucion', 'ley', 'fallo'));
