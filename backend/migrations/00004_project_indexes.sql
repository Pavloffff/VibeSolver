-- +goose Up
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE project_indexes (
    id BIGSERIAL PRIMARY KEY,
    source_id BIGINT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    index_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'not_started',
    active_run_id BIGINT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source_id, index_type)
);

CREATE TABLE index_runs (
    id BIGSERIAL PRIMARY KEY,
    project_index_id BIGINT NOT NULL REFERENCES project_indexes(id) ON DELETE CASCADE,
    snapshot_id BIGINT NOT NULL REFERENCES source_snapshots(id) ON DELETE CASCADE,
    status TEXT NOT NULL,
    progress INT NOT NULL DEFAULT 0,
    parser_version TEXT NOT NULL,
    chunker_version TEXT NOT NULL,
    embedding_model_id BIGINT REFERENCES workspace_models(id) ON DELETE SET NULL,
    embedding_model_revision TEXT,
    embedding_dimensions INT,
    files_total INT NOT NULL DEFAULT 0,
    chunks_total INT NOT NULL DEFAULT 0,
    error TEXT,
    diagnostics JSONB NOT NULL DEFAULT '[]',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ
);

ALTER TABLE project_indexes
    ADD CONSTRAINT fk_project_indexes_active_run
    FOREIGN KEY (active_run_id) REFERENCES index_runs(id) ON DELETE SET NULL;

CREATE INDEX idx_index_runs_project_created
    ON index_runs (project_index_id, created_at DESC, id DESC);

CREATE TABLE index_chunks (
    id BIGSERIAL PRIMARY KEY,
    run_id BIGINT NOT NULL REFERENCES index_runs(id) ON DELETE CASCADE,
    snapshot_file_id BIGINT REFERENCES source_snapshot_files(id) ON DELETE CASCADE,
    content_hash TEXT NOT NULL,
    path TEXT NOT NULL,
    branch TEXT NOT NULL DEFAULT '',
    start_line INT,
    end_line INT,
    symbol TEXT,
    content TEXT NOT NULL,
    search_vector TSVECTOR GENERATED ALWAYS AS (to_tsvector('simple', content)) STORED,
    embedding VECTOR,
    metadata_json JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX idx_index_chunks_run_path ON index_chunks (run_id, path);
CREATE INDEX idx_index_chunks_search_vector ON index_chunks USING GIN (search_vector);

-- +goose Down
DROP TABLE index_chunks;
DROP TABLE index_runs;
DROP TABLE project_indexes;
