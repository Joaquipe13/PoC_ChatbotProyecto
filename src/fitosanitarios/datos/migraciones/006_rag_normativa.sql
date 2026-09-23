-- RAG de normativa con búsqueda vectorial (23/09/2026, ver DECISIONES.md, "RAG de
-- limitaciones"). Dos índices vectoriales nuevos, cada uno en su entidad:
--
-- 1. `territorio.fragmento_norma`: el texto de cada norma partido en fragmentos
--    (`RecursiveCharacterTextSplitter`, 800 caracteres con 120 de solapamiento, como en
--    la cursada). Un artículo corto es un solo fragmento; uno largo, varios (antes se
--    embebían solo sus primeros 2000 caracteres). Las normas sin PDF oficial (fallos y
--    ordenanzas citadas por prensa, `.md`) no tienen artículos pero sí fragmentos, con
--    `articulo_id` en NULL: así entran en la búsqueda.
-- 2. `territorio.regla_distancia.texto` + `embedding`: cada regla de `reglas.csv`
--    escrita como una oración ("Sastre · aplicación aérea · todas las bandas: prohibido
--    a menos de 3000 m de la zona urbana"), para recuperar por similitud qué reglas
--    corresponden a una pregunta. Qué se permite lo sigue decidiendo el código.

CREATE TABLE IF NOT EXISTS territorio.fragmento_norma (
    id BIGSERIAL PRIMARY KEY,
    norma_id BIGINT NOT NULL REFERENCES territorio.norma (id) ON DELETE CASCADE,
    articulo_id BIGINT REFERENCES territorio.articulo (id) ON DELETE CASCADE,
    orden INT NOT NULL, -- posición del fragmento dentro de su artículo (o de la norma)
    texto TEXT NOT NULL,
    embedding vector(768) NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_fragmento_norma_norma ON territorio.fragmento_norma (norma_id);
CREATE INDEX IF NOT EXISTS ix_fragmento_norma_articulo
    ON territorio.fragmento_norma (articulo_id);
CREATE INDEX IF NOT EXISTS ix_fragmento_norma_embedding_hnsw
    ON territorio.fragmento_norma USING hnsw (embedding vector_cosine_ops);

ALTER TABLE territorio.regla_distancia ADD COLUMN IF NOT EXISTS texto TEXT;
ALTER TABLE territorio.regla_distancia ADD COLUMN IF NOT EXISTS embedding vector(768);
CREATE INDEX IF NOT EXISTS ix_regla_distancia_embedding_hnsw
    ON territorio.regla_distancia USING hnsw (embedding vector_cosine_ops);
