-- Schema territorio: provincias, localidades, zonas protegidas, normativa (por
-- artículo) y reglas de distancia. Ver docs/modelo-datos.md y
-- docs/contrato-insumos.md (formato de los insumos que cargan estas tablas).
--
-- Sin PostGIS: las geometrías se guardan como GeoJSON en JSONB (EPSG:4326) y se
-- prefiltran por bounding box en columnas numéricas; el punto-en-polígono y las
-- distancias exactas se calculan en Python (geopandas/shapely/pyproj), ver
-- servicios/geo.py (Fase 5).

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE SCHEMA IF NOT EXISTS territorio;

CREATE TABLE IF NOT EXISTS territorio.provincia (
    id BIGSERIAL PRIMARY KEY,
    nombre TEXT NOT NULL UNIQUE -- ej. "santa-fe": igual al nombre de carpeta en provincial/
);

CREATE TABLE IF NOT EXISTS territorio.localidad (
    id BIGSERIAL PRIMARY KEY,
    jurisdiccion_id TEXT NOT NULL UNIQUE, -- ej. "san-carlos-centro"
    nombre TEXT NOT NULL,
    provincia_id BIGINT NOT NULL REFERENCES territorio.provincia (id),
    limite JSONB NOT NULL, -- GeoJSON Polygon/MultiPolygon, EPSG:4326
    bbox_min_lon NUMERIC NOT NULL,
    bbox_min_lat NUMERIC NOT NULL,
    bbox_max_lon NUMERIC NOT NULL,
    bbox_max_lat NUMERIC NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_localidad_provincia ON territorio.localidad (provincia_id);
CREATE INDEX IF NOT EXISTS ix_localidad_bbox
    ON territorio.localidad (bbox_min_lon, bbox_min_lat, bbox_max_lon, bbox_max_lat);

CREATE TABLE IF NOT EXISTS territorio.zona_protegida (
    id BIGSERIAL PRIMARY KEY,
    localidad_id BIGINT NOT NULL REFERENCES territorio.localidad (id) ON DELETE CASCADE,
    tipo TEXT NOT NULL CHECK (tipo IN ('escuela', 'curso_agua', 'zona_urbana', 'otro')),
    nombre TEXT NOT NULL,
    geometria JSONB NOT NULL, -- GeoJSON Point/LineString/Polygon, EPSG:4326
    propiedades JSONB NOT NULL DEFAULT '{}'::jsonb,
    bbox_min_lon NUMERIC NOT NULL,
    bbox_min_lat NUMERIC NOT NULL,
    bbox_max_lon NUMERIC NOT NULL,
    bbox_max_lat NUMERIC NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_zona_protegida_localidad
    ON territorio.zona_protegida (localidad_id);
CREATE INDEX IF NOT EXISTS ix_zona_protegida_bbox
    ON territorio.zona_protegida (bbox_min_lon, bbox_min_lat, bbox_max_lon, bbox_max_lat);
CREATE INDEX IF NOT EXISTS ix_zona_protegida_tipo ON territorio.zona_protegida (tipo);

-- ambito determina cuál de localidad_id / provincia_id está poblado (ninguno = nacional).
CREATE TABLE IF NOT EXISTS territorio.norma (
    id BIGSERIAL PRIMARY KEY,
    ambito TEXT NOT NULL CHECK (ambito IN ('municipal', 'provincial', 'nacional')),
    localidad_id BIGINT REFERENCES territorio.localidad (id),
    provincia_id BIGINT REFERENCES territorio.provincia (id),
    tipo TEXT NOT NULL CHECK (tipo IN ('ordenanza', 'decreto', 'resolucion', 'ley')),
    numero TEXT NOT NULL,
    anio INT NOT NULL,
    archivo TEXT NOT NULL, -- nombre del PDF sin extensión, ej. "ordenanza-914-2018"
    metadatos JSONB NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT norma_ambito_referencia CHECK (
        (ambito = 'municipal' AND localidad_id IS NOT NULL AND provincia_id IS NULL)
        OR (ambito = 'provincial' AND provincia_id IS NOT NULL AND localidad_id IS NULL)
        OR (ambito = 'nacional' AND localidad_id IS NULL AND provincia_id IS NULL)
    )
);
CREATE INDEX IF NOT EXISTS ix_norma_localidad ON territorio.norma (localidad_id);
CREATE INDEX IF NOT EXISTS ix_norma_provincia ON territorio.norma (provincia_id);
CREATE INDEX IF NOT EXISTS ix_norma_archivo ON territorio.norma (archivo);

CREATE TABLE IF NOT EXISTS territorio.articulo (
    id BIGSERIAL PRIMARY KEY,
    norma_id BIGINT NOT NULL REFERENCES territorio.norma (id) ON DELETE CASCADE,
    numero TEXT NOT NULL,
    texto TEXT NOT NULL,
    pagina INT,
    requiere_revision BOOLEAN NOT NULL DEFAULT false, -- true si el texto vino de OCR
    metadatos JSONB NOT NULL DEFAULT '{}'::jsonb, -- capítulo, etc.
    embedding vector(768)
);
CREATE INDEX IF NOT EXISTS ix_articulo_norma ON territorio.articulo (norma_id);
CREATE INDEX IF NOT EXISTS ix_articulo_embedding_hnsw
    ON territorio.articulo USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS ix_articulo_texto_fts
    ON territorio.articulo USING gin (to_tsvector('spanish', texto));

CREATE TABLE IF NOT EXISTS territorio.regla_distancia (
    id BIGSERIAL PRIMARY KEY,
    norma_id BIGINT NOT NULL REFERENCES territorio.norma (id) ON DELETE CASCADE,
    articulo_id BIGINT REFERENCES territorio.articulo (id),
    tipo_zona TEXT NOT NULL, -- valores de zona_protegida.tipo (nunca 'limite')
    tipo_aplicacion TEXT NOT NULL CHECK (tipo_aplicacion IN ('terrestre', 'aerea', 'todas')),
    bandas TEXT[] NOT NULL, -- {'todas'} o subconjunto de {Ia,Ib,II,III,IV}
    distancia_min_m NUMERIC NOT NULL,
    observaciones TEXT,
    -- 'csv': viene de reglas.csv (revisada por una persona). 'pdf_extraido': la
    -- leyó el extractor del texto de los artículos porque la jurisdicción no tenía
    -- filas en reglas.csv; la respuesta avisa que hay que verificarla con la norma.
    fuente TEXT NOT NULL DEFAULT 'csv' CHECK (fuente IN ('csv', 'pdf_extraido')),
    -- false (N): prohibición, dentro de distancia_min_m no se puede; es lo único que
    -- usan el dictamen y el agendado. true (S): regla condicional, a partir de
    -- distancia_min_m se puede si se cumplen `condiciones`; solo para consultas.
    permitido BOOLEAN NOT NULL DEFAULT false,
    condiciones TEXT
);
-- Bases creadas antes de la extracción desde PDF: CREATE TABLE IF NOT EXISTS no agrega la columna.
ALTER TABLE territorio.regla_distancia
    ADD COLUMN IF NOT EXISTS fuente TEXT NOT NULL DEFAULT 'csv';
ALTER TABLE territorio.regla_distancia
    ADD COLUMN IF NOT EXISTS permitido BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE territorio.regla_distancia
    ADD COLUMN IF NOT EXISTS condiciones TEXT;
CREATE INDEX IF NOT EXISTS ix_regla_distancia_norma ON territorio.regla_distancia (norma_id);
CREATE INDEX IF NOT EXISTS ix_regla_distancia_tipo_zona
    ON territorio.regla_distancia (tipo_zona);
