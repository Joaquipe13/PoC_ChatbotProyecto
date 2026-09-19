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
    adversidad TEXT,
    superficie_ha NUMERIC,
    tipo_aplicacion TEXT CHECK (tipo_aplicacion IN ('terrestre', 'aerea')),
    fecha_prevista DATE,
    hora_prevista TIME, -- horario agendado de la aplicación (agendar_aplicacion)
    estado TEXT NOT NULL DEFAULT 'borrador'
        CHECK (estado IN ('borrador', 'confirmada', 'evaluada', 'cancelada')),
    datos_extraidos JSONB NOT NULL DEFAULT '{}'::jsonb, -- campos + confianza de leer_receta
    ubicacion JSONB, -- {"lat": ..., "lon": ...}
    creado_en TIMESTAMPTZ NOT NULL DEFAULT now(),
    actualizado_en TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Bases creadas antes de agendar_aplicacion: CREATE TABLE IF NOT EXISTS no agrega la columna.
ALTER TABLE operacion.receta ADD COLUMN IF NOT EXISTS hora_prevista TIME;
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

-- Deduplicación de mensajes de WhatsApp por message.id (Fase 8: Meta
-- reintenta entregas). Persistida en Postgres (no en memoria de proceso)
-- porque un reintento puede llegar después de un reinicio del proceso del
-- webhook; ver DECISIONES.md.
CREATE TABLE IF NOT EXISTS operacion.mensaje_whatsapp (
    message_id TEXT PRIMARY KEY,
    procesado_en TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Eventos de aplicación real (Fase 9, RF7 registrar_evento): inicio y fin
-- de una aplicación en el campo, asociada a receta, vehículo y lote.
-- Distinto del dictamen (que evalúa si es viable ANTES de aplicar): esto
-- registra que efectivamente se aplicó.
CREATE TABLE IF NOT EXISTS operacion.evento_aplicacion (
    id BIGSERIAL PRIMARY KEY,
    thread_id TEXT NOT NULL, -- número de WhatsApp normalizado, dueño del evento
    receta_id BIGINT REFERENCES operacion.receta (id),
    vehiculo_id BIGINT REFERENCES catalogo.vehiculo (id),
    lote TEXT,
    fecha_inicio TIMESTAMPTZ NOT NULL DEFAULT now(),
    fecha_fin TIMESTAMPTZ,
    estado TEXT NOT NULL DEFAULT 'en_curso'
        CHECK (estado IN ('en_curso', 'finalizado', 'cancelado')),
    creado_en TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_evento_aplicacion_thread ON operacion.evento_aplicacion (thread_id);
CREATE INDEX IF NOT EXISTS ix_evento_aplicacion_receta ON operacion.evento_aplicacion (receta_id);
