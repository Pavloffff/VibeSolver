-- +goose Up
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE model_provider_connections (
    id BIGSERIAL PRIMARY KEY,
    provider_type TEXT NOT NULL,
    name TEXT NOT NULL,
    base_url TEXT NOT NULL,
    credential_ciphertext BYTEA,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE workspace_models (
    id BIGSERIAL PRIMARY KEY,
    provider_connection_id BIGINT NOT NULL REFERENCES model_provider_connections(id) ON DELETE CASCADE,
    provider_model_id TEXT NOT NULL,
    display_name TEXT NOT NULL,
    capabilities JSONB NOT NULL DEFAULT '[]',
    status TEXT NOT NULL,
    progress INT,
    metadata_json JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (provider_connection_id, provider_model_id)
);

CREATE TABLE project_model_assignments (
    source_id BIGINT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    model_id BIGINT NOT NULL REFERENCES workspace_models(id) ON DELETE CASCADE,
    PRIMARY KEY (source_id, role)
);

-- +goose Down
DROP TABLE project_model_assignments;
DROP TABLE workspace_models;
DROP TABLE model_provider_connections;
