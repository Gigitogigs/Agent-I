SET search_path TO rag, public;

-- Help center / policy documents
CREATE TABLE IF NOT EXISTS rag.documents (
    id         BIGSERIAL PRIMARY KEY,
    doc_id     TEXT NOT NULL UNIQUE,        -- source URL or file path
    title      TEXT,
    content    TEXT NOT NULL,               -- original chunk text
    metadata   JSONB DEFAULT '{}',          -- product, category, date, etc.
    embedding  VECTOR(1024),                -- adjust dimension to your model
    fts        TSVECTOR GENERATED ALWAYS AS (to_tsvector('english', content)) STORED,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- HNSW index for fast ANN search (pgvector >= 0.5)
CREATE INDEX IF NOT EXISTS documents_embedding_hnsw
    ON rag.documents USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Full-text search index (for hybrid search)
CREATE INDEX IF NOT EXISTS documents_fts_idx
    ON rag.documents USING gin (fts);

-- Metadata filter index
CREATE INDEX IF NOT EXISTS documents_metadata_idx
    ON rag.documents USING gin (metadata);


-- Past resolved tickets (retrieval-augmented troubleshooting)
CREATE TABLE IF NOT EXISTS rag.resolved_tickets (
    id         BIGSERIAL PRIMARY KEY,
    ticket_id  TEXT NOT NULL UNIQUE,
    summary    TEXT NOT NULL,
    resolution TEXT NOT NULL,
    metadata   JSONB DEFAULT '{}',
    embedding  VECTOR(1024),
    fts        TSVECTOR GENERATED ALWAYS AS (to_tsvector('english', summary || ' ' || resolution)) STORED,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS resolved_tickets_embedding_hnsw
    ON rag.resolved_tickets USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

CREATE INDEX IF NOT EXISTS resolved_tickets_fts_idx
    ON rag.resolved_tickets USING gin (fts);