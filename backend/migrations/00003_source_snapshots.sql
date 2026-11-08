-- +goose Up
CREATE TABLE source_snapshots (
    id BIGSERIAL PRIMARY KEY,
    source_id BIGINT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    import_id BIGINT UNIQUE REFERENCES imports(id) ON DELETE CASCADE,
    content_hash TEXT NOT NULL,
    source_revision JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_source_snapshots_source_created
    ON source_snapshots (source_id, created_at DESC, id DESC);

CREATE TABLE source_snapshot_files (
    id BIGSERIAL PRIMARY KEY,
    snapshot_id BIGINT NOT NULL REFERENCES source_snapshots(id) ON DELETE CASCADE,
    branch TEXT NOT NULL DEFAULT '',
    path TEXT NOT NULL,
    size_bytes BIGINT NOT NULL,
    storage_key TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    metadata_json JSONB NOT NULL DEFAULT '{}',
    UNIQUE (snapshot_id, branch, path)
);

CREATE INDEX idx_source_snapshot_files_snapshot_path
    ON source_snapshot_files (snapshot_id, path);

-- +goose Down
DROP TABLE source_snapshot_files;
DROP TABLE source_snapshots;
