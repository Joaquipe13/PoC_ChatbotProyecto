-- Schema operacion: recetas en curso/evaluadas, sus ítems, el dictamen y el log
-- de turnos de conversación. Ver docs/modelo-datos.md.
--
-- Depende de catalogo (001) y territorio (002) por las FK de receta_item.producto_id
-- y receta.localidad_id: correr las migraciones en orden 001, 002, 003.
--
-- Las tablas propias del checkpointer de LangGraph (Fase 7) no se crean acá:
-- las gestiona la librería del checkpointer sobre este mismo DATABASE_URL.

CREATE SCHEMA IF NOT EXISTS operacion;

CREATE TABLE IF NOT EXISTS operacion.receta (
    id BIGSERIAL PRIMARY KEY,
    thread_id TEXT NOT NULL, -- número de WhatsApp normalizado
    localidad_id BIGINT REFERENCES territorio.localidad (id),
    numero TEXT,
    cultivo TEXT,
    lote TEXT,
    superficie_ha NUMERIC,
    tipo_aplicacion TEXT CHECK (tipo_aplicacion IN ('terrestre', 'aerea')),
    fecha_prevista DATE,
    estado TEXT NOT NULL DEFAULT 'borrador'
        CHECK (estado IN ('borrador', 'confirmada', 'evaluada', 'cancelada')),
    datos_extraidos JSONB NOT NULL DEFAULT '{}'::jsonb, -- campos + confianza de leer_receta
    ubicacion JSONB, -- {"lat": ..., "lon": ...}
    creado_en TIMESTAMPTZ NOT NULL DEFAULT now(),
    actualizado_en TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_receta_thread ON operacion.receta (thread_id);
CREATE INDEX IF NOT EXISTS ix_receta_localidad ON operacion.receta (localidad_id);
CREATE INDEX IF NOT EXISTS ix_receta_datos_extraidos_gin
    ON operacion.receta USING gin (datos_extraidos);

CREATE TABLE IF NOT EXISTS operacion.receta_item (
    id BIGSERIAL PRIMARY KEY,
    receta_id BIGINT NOT NULL REFERENCES operacion.receta (id) ON DELETE CASCADE,
    producto_id BIGINT REFERENCES catalogo.producto (id), -- null hasta resolverlo
    producto_nombre_declarado TEXT NOT NULL,
    adversidad TEXT,
    dosis_declarada JSONB NOT NULL DEFAULT '{}'::jsonb -- texto, valor, unidad
);
CREATE INDEX IF NOT EXISTS ix_receta_item_receta ON operacion.receta_item (receta_id);
CREATE INDEX IF NOT EXISTS ix_receta_item_producto ON operacion.receta_item (producto_id);

CREATE TABLE IF NOT EXISTS operacion.dictamen (
    id BIGSERIAL PRIMARY KEY,
    receta_id BIGINT NOT NULL REFERENCES operacion.receta (id) ON DELETE CASCADE,
    resultado TEXT NOT NULL CHECK (resultado IN ('APTA', 'OBSERVADA', 'NO_EVALUABLE')),
    chequeos JSONB NOT NULL DEFAULT '{}'::jsonb,
    citas JSONB NOT NULL DEFAULT '[]'::jsonb,
    creado_en TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_dictamen_receta ON operacion.dictamen (receta_id);
CREATE INDEX IF NOT EXISTS ix_dictamen_chequeos_gin ON operacion.dictamen USING gin (chequeos);

CREATE TABLE IF NOT EXISTS operacion.turno (
    id BIGSERIAL PRIMARY KEY,
    thread_id TEXT NOT NULL,
    entrada JSONB NOT NULL,
    tool_calls JSONB NOT NULL DEFAULT '[]'::jsonb,
    salida JSONB NOT NULL,
    creado_en TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_turno_thread ON operacion.turno (thread_id);
