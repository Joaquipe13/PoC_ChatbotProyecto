-- RAG de marbetes de SENASA (23/09/2026, ver DECISIONES.md, "RAG de marbetes"). El texto
-- de cada marbete (la etiqueta aprobada del producto, en PDF) partido en fragmentos con el
-- `RecursiveCharacterTextSplitter` de la cursada, por página, para responder lo que el
-- registro estructurado no trae: carencia, precauciones, compatibilidad, reingreso.
--
-- Cada fragmento cuelga de su documento (`catalogo.documento`, tipo 'marbete') y de su
-- producto: la búsqueda filtra primero por el producto y después ordena por similitud.

CREATE TABLE IF NOT EXISTS catalogo.fragmento_marbete (
    id BIGSERIAL PRIMARY KEY,
    documento_id BIGINT NOT NULL REFERENCES catalogo.documento (id) ON DELETE CASCADE,
    producto_id BIGINT NOT NULL REFERENCES catalogo.producto (id) ON DELETE CASCADE,
    pagina INT NOT NULL,
    orden INT NOT NULL, -- posición del fragmento dentro de su página
    texto TEXT NOT NULL,
    embedding vector(768) NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_fragmento_marbete_producto
    ON catalogo.fragmento_marbete (producto_id);
CREATE INDEX IF NOT EXISTS ix_fragmento_marbete_documento
    ON catalogo.fragmento_marbete (documento_id);
CREATE INDEX IF NOT EXISTS ix_fragmento_marbete_embedding_hnsw
    ON catalogo.fragmento_marbete USING hnsw (embedding vector_cosine_ops);
