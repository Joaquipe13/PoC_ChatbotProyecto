-- Schema catalogo: vademécum SENASA normalizado (firma, producto, principio activo,
-- cultivo, adversidad, uso registrado, documento). Ver docs/modelo-datos.md.
--
-- Idempotente a propósito (IF NOT EXISTS / CREATE OR REPLACE en todo lo que lo admite):
-- se puede correr más de una vez sin romper una base ya migrada. Ver DECISIONES.md
-- ("migraciones: SQL plano idempotente en vez de alembic").
--
-- Dimensión de los embeddings: 768, correspondiente a
-- sentence-transformers/paraphrase-multilingual-mpnet-base-v2 (ver DECISIONES.md).
-- Si se cambia EMBEDDINGS_MODEL por uno de otra dimensión, esta migración y los
-- índices HNSW deben actualizarse.

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE SCHEMA IF NOT EXISTS catalogo;

CREATE TABLE IF NOT EXISTS catalogo.firma (
    id BIGSERIAL PRIMARY KEY,
    nombre TEXT NOT NULL UNIQUE,
    datos JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS catalogo.producto (
    id BIGSERIAL PRIMARY KEY,
    firma_id BIGINT NOT NULL REFERENCES catalogo.firma (id),
    numero_inscripcion TEXT NOT NULL UNIQUE,
    marca TEXT NOT NULL,
    clase_toxicologica TEXT,
    banda_toxicologica TEXT, -- normalizada: Ia | Ib | II | III | IV
    estado_producto TEXT,
    toxicidad JSONB NOT NULL DEFAULT '{}'::jsonb, -- abejas, peces, aves...
    crudo_api JSONB NOT NULL DEFAULT '{}'::jsonb, -- detalle SENASA, sin los PDF en base64
    embedding vector(768) -- marca + principios activos + concentración
);
CREATE INDEX IF NOT EXISTS ix_producto_firma ON catalogo.producto (firma_id);
CREATE INDEX IF NOT EXISTS ix_producto_marca_trgm
    ON catalogo.producto USING gin (marca gin_trgm_ops);
CREATE INDEX IF NOT EXISTS ix_producto_embedding_hnsw
    ON catalogo.producto USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS ix_producto_crudo_api_gin
    ON catalogo.producto USING gin (crudo_api);
CREATE INDEX IF NOT EXISTS ix_producto_toxicidad_gin
    ON catalogo.producto USING gin (toxicidad);

CREATE TABLE IF NOT EXISTS catalogo.principio_activo (
    id BIGSERIAL PRIMARY KEY,
    nombre TEXT NOT NULL UNIQUE,
    embedding vector(768)
);
CREATE INDEX IF NOT EXISTS ix_principio_activo_nombre_trgm
    ON catalogo.principio_activo USING gin (nombre gin_trgm_ops);
CREATE INDEX IF NOT EXISTS ix_principio_activo_embedding_hnsw
    ON catalogo.principio_activo USING hnsw (embedding vector_cosine_ops);

CREATE TABLE IF NOT EXISTS catalogo.producto_principio_activo (
    producto_id BIGINT NOT NULL REFERENCES catalogo.producto (id) ON DELETE CASCADE,
    principio_activo_id BIGINT NOT NULL REFERENCES catalogo.principio_activo (id),
    concentracion NUMERIC,
    unidad TEXT,
    PRIMARY KEY (producto_id, principio_activo_id)
);

CREATE TABLE IF NOT EXISTS catalogo.cultivo (
    id BIGSERIAL PRIMARY KEY,
    nombre TEXT NOT NULL UNIQUE,
    sinonimos JSONB NOT NULL DEFAULT '[]'::jsonb,
    embedding vector(768)
);
CREATE INDEX IF NOT EXISTS ix_cultivo_nombre_trgm
    ON catalogo.cultivo USING gin (nombre gin_trgm_ops);
CREATE INDEX IF NOT EXISTS ix_cultivo_embedding_hnsw
    ON catalogo.cultivo USING hnsw (embedding vector_cosine_ops);

CREATE TABLE IF NOT EXISTS catalogo.adversidad (
    id BIGSERIAL PRIMARY KEY,
    nombre_comun TEXT NOT NULL UNIQUE,
    nombre_cientifico TEXT,
    sinonimos JSONB NOT NULL DEFAULT '[]'::jsonb,
    embedding vector(768) -- nombre común + científico, ej. "yuyo colorado" -> Amaranthus
);
CREATE INDEX IF NOT EXISTS ix_adversidad_nombre_trgm
    ON catalogo.adversidad USING gin (nombre_comun gin_trgm_ops);
CREATE INDEX IF NOT EXISTS ix_adversidad_embedding_hnsw
    ON catalogo.adversidad USING hnsw (embedding vector_cosine_ops);

CREATE TABLE IF NOT EXISTS catalogo.documento (
    id BIGSERIAL PRIMARY KEY,
    producto_id BIGINT NOT NULL REFERENCES catalogo.producto (id) ON DELETE CASCADE,
    tipo TEXT NOT NULL, -- 'marbete', etc.
    ruta_archivo TEXT,
    extraccion JSONB NOT NULL DEFAULT '{}'::jsonb -- salida del LLM + confianza
);
CREATE INDEX IF NOT EXISTS ix_documento_producto ON catalogo.documento (producto_id);

CREATE TABLE IF NOT EXISTS catalogo.uso_registrado (
    id BIGSERIAL PRIMARY KEY,
    producto_id BIGINT NOT NULL REFERENCES catalogo.producto (id) ON DELETE CASCADE,
    cultivo_id BIGINT NOT NULL REFERENCES catalogo.cultivo (id),
    adversidad_id BIGINT REFERENCES catalogo.adversidad (id),
    documento_id BIGINT REFERENCES catalogo.documento (id),
    fuente TEXT NOT NULL CHECK (fuente IN ('senasa_estructurado', 'marbete_extraido')),
    confianza NUMERIC,
    dosis JSONB NOT NULL DEFAULT '{}'::jsonb, -- texto, min, max, unidad, base
    condiciones JSONB NOT NULL DEFAULT '{}'::jsonb -- momento, volumen, carencia
);
CREATE INDEX IF NOT EXISTS ix_uso_registrado_producto ON catalogo.uso_registrado (producto_id);
CREATE INDEX IF NOT EXISTS ix_uso_registrado_cultivo ON catalogo.uso_registrado (cultivo_id);
CREATE INDEX IF NOT EXISTS ix_uso_registrado_adversidad
    ON catalogo.uso_registrado (adversidad_id);
CREATE INDEX IF NOT EXISTS ix_uso_registrado_dosis_gin
    ON catalogo.uso_registrado USING gin (dosis);

-- Vehículos/equipos de aplicación (Fase 9, RF6 resolver_vehiculo; columnas
-- matricula/caracteristicas/embedding agregadas en sesión post-Fase 11, ver
-- DECISIONES.md "RAG de equipos"). Sigue siendo un catálogo chico, pero deja
-- de ser solo categorías genéricas: cada equipo puede ser una entidad
-- puntual (matrícula + características propias), y el matching ahora
-- combina pg_trgm con similitud de embedding (mismo patrón que
-- catalogo.producto), no solo sinónimo/substring -- necesario para
-- distinguir entre varios equipos del mismo tipo_aplicacion por una
-- descripción libre ("la avioneta grande" vs "la dromader").
CREATE TABLE IF NOT EXISTS catalogo.vehiculo (
    id BIGSERIAL PRIMARY KEY,
    nombre TEXT NOT NULL UNIQUE,
    tipo_aplicacion TEXT NOT NULL CHECK (tipo_aplicacion IN ('terrestre', 'aerea')),
    sinonimos JSONB NOT NULL DEFAULT '[]'::jsonb,
    matricula TEXT,
    caracteristicas JSONB NOT NULL DEFAULT '{}'::jsonb,
    embedding vector(768)
);
-- Bases creadas antes del RAG de equipos: CREATE TABLE IF NOT EXISTS no agrega las
-- columnas nuevas. Después de esto, correr scripts/cargar_vehiculos.py (embeddings).
ALTER TABLE catalogo.vehiculo ADD COLUMN IF NOT EXISTS matricula TEXT;
ALTER TABLE catalogo.vehiculo
    ADD COLUMN IF NOT EXISTS caracteristicas JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE catalogo.vehiculo ADD COLUMN IF NOT EXISTS embedding vector(768);
CREATE INDEX IF NOT EXISTS ix_vehiculo_nombre_trgm
    ON catalogo.vehiculo USING gin (nombre gin_trgm_ops);
CREATE INDEX IF NOT EXISTS ix_vehiculo_embedding_hnsw
    ON catalogo.vehiculo USING hnsw (embedding vector_cosine_ops);

INSERT INTO catalogo.vehiculo (nombre, tipo_aplicacion, sinonimos) VALUES
    ('pulverizador autopropulsado', 'terrestre',
     '["mosquito", "autopropulsada", "autopropulsado"]'::jsonb),
    ('pulverizador de arrastre', 'terrestre',
     '["arrastre", "de arrastre", "pulverizadora de arrastre"]'::jsonb),
    ('mochila', 'terrestre', '["mochila", "manual", "mochila de espalda"]'::jsonb),
    ('avión fumigador', 'aerea', '["avión", "avion", "avioneta", "fumigador"]'::jsonb),
    ('dron', 'aerea', '["dron", "drone"]'::jsonb)
ON CONFLICT (nombre) DO NOTHING;

-- Dos aviones puntuales de ejemplo (matrícula ficticia -- "LV-EJEMPLO1/2" a
-- propósito, no sigue el formato real LV-XXX de 3 letras, para que no se
-- confunda con una matrícula real). El embedding se calcula aparte con
-- `scripts/cargar_vehiculos.py` (necesita sentence-transformers, no se puede
-- hacer en SQL plano).
INSERT INTO catalogo.vehiculo (nombre, tipo_aplicacion, sinonimos, matricula, caracteristicas) VALUES
    ('Air Tractor AT-502B', 'aerea',
     '["air tractor", "at-502", "at502", "avioneta grande", "turbo"]'::jsonb,
     'LV-EJEMPLO1',
     '{"modelo": "Air Tractor AT-502B", "motor": "turbohélice", "capacidad_l": 3028, "ancho_faja_m": 18}'::jsonb),
    ('PZL M18 Dromader', 'aerea',
     '["dromader", "pzl", "m18", "pzl m18"]'::jsonb,
     'LV-EJEMPLO2',
     '{"modelo": "PZL M18 Dromader", "motor": "radial", "capacidad_l": 2500, "ancho_faja_m": 16}'::jsonb)
ON CONFLICT (nombre) DO NOTHING;
