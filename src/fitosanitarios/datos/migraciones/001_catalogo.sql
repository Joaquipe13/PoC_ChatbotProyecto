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
    nombre TEXT NOT NULL,
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
    nombre_comun TEXT NOT NULL,
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
