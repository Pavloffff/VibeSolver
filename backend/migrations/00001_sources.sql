-- +goose Up
CREATE TABLE sources (
    id BIGSERIAL PRIMARY KEY,
    type TEXT NOT NULL,
    name TEXT NOT NULL,
    config JSONB NOT NULL DEFAULT '{}',
    enabled BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE imports (
    id BIGSERIAL PRIMARY KEY,
    source_id BIGINT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    status TEXT NOT NULL,
    progress INT NOT NULL DEFAULT 0,
    error TEXT,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ
);

CREATE INDEX idx_imports_source_id ON imports (source_id);

CREATE TABLE imported_files (
    id BIGSERIAL PRIMARY KEY,
    source_id BIGINT NOT NULL REFERENCES sources(id),
    branch TEXT NOT NULL DEFAULT '',
    path TEXT NOT NULL,
    size_bytes BIGINT,
    storage_key TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    imported_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source_id, branch, path)
);

-- +goose Down
DROP TABLE imported_files;
DROP TABLE imports;
DROP TABLE sources;
