-- +goose Up
ALTER TABLE tickets ADD CONSTRAINT tickets_id_source_unique UNIQUE (id, source_id);

CREATE TABLE ticket_log_attachments (
    id BIGSERIAL PRIMARY KEY,
    source_id BIGINT NOT NULL,
    ticket_id BIGINT NOT NULL,
    filename TEXT NOT NULL,
    storage_key TEXT NOT NULL UNIQUE,
    size_bytes BIGINT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ticket_log_attachments_ticket_source_fk
        FOREIGN KEY (ticket_id, source_id) REFERENCES tickets(id, source_id) ON DELETE CASCADE,
    CONSTRAINT ticket_log_attachments_id_scope_unique UNIQUE (id, source_id, ticket_id)
);

CREATE INDEX ticket_log_attachments_scope_idx
    ON ticket_log_attachments (source_id, ticket_id, id DESC);

CREATE TABLE ticket_log_chunks (
    id BIGSERIAL PRIMARY KEY,
    attachment_id BIGINT NOT NULL,
    source_id BIGINT NOT NULL,
    ticket_id BIGINT NOT NULL,
    path TEXT NOT NULL,
    start_line INT NOT NULL,
    end_line INT NOT NULL,
    event_timestamp TEXT,
    content TEXT NOT NULL,
    search_vector TSVECTOR GENERATED ALWAYS AS (to_tsvector('simple', content)) STORED,
    embedding VECTOR,
    metadata_json JSONB NOT NULL DEFAULT '{}',
    CONSTRAINT ticket_log_chunks_attachment_scope_fk
        FOREIGN KEY (attachment_id, source_id, ticket_id)
        REFERENCES ticket_log_attachments(id, source_id, ticket_id) ON DELETE CASCADE
);

CREATE INDEX ticket_log_chunks_scope_idx
    ON ticket_log_chunks (source_id, ticket_id, attachment_id);
CREATE INDEX ticket_log_chunks_search_vector_idx
    ON ticket_log_chunks USING GIN (search_vector);

-- +goose Down
DROP TABLE ticket_log_chunks;
DROP TABLE ticket_log_attachments;
ALTER TABLE tickets DROP CONSTRAINT tickets_id_source_unique;
