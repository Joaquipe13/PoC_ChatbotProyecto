-- Se ejecuta automáticamente al crear el contenedor (docker-entrypoint-initdb.d).
-- También puede correrse a mano para verificar una base ya existente:
--   docker compose exec db psql -U postgres -d fitosanitarios -f scripts/smoke_db.sql

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Smoke test: falla si las extensiones no quedaron disponibles.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') THEN
        RAISE EXCEPTION 'La extension vector no esta instalada';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm') THEN
        RAISE EXCEPTION 'La extension pg_trgm no esta instalada';
    END IF;
END $$;
